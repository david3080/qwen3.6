#!/usr/bin/env python3
import os
import subprocess
import time
import requests
import runpod

print("=== handler.py starting ===", flush=True)
import shutil
print(f"llama-server binary: {shutil.which('llama-server')}", flush=True)
print(f"GPU check: {os.popen('nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>&1').read().strip()}", flush=True)

MODEL_PATH = os.environ.get("MODEL_PATH", "/tmp/model.gguf")
MODEL_URL = os.environ.get("MODEL_URL", "https://huggingface.co/bartowski/Qwen_Qwen3.6-35B-A3B-GGUF/resolve/main/Qwen_Qwen3.6-35B-A3B-Q4_K_M.gguf")
MMPROJ_PATH = os.environ.get("MMPROJ_PATH", "")
CTX_SIZE = os.environ.get("CTX_SIZE", "8192")
LLAMA_PORT = 8080
LLAMA_URL = f"http://127.0.0.1:{LLAMA_PORT}"


def ensure_model():
    if os.path.exists(MODEL_PATH):
        print(f"Model found at {MODEL_PATH}", flush=True)
        return
    os.makedirs(os.path.dirname(MODEL_PATH) or "/tmp", exist_ok=True)
    print(f"Downloading model from {MODEL_URL} ...", flush=True)
    with requests.get(MODEL_URL, stream=True, timeout=30) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        downloaded = 0
        with open(MODEL_PATH, "wb") as f:
            for chunk in r.iter_content(chunk_size=8 * 1024 * 1024):
                f.write(chunk)
                downloaded += len(chunk)
                if total and downloaded % (1024 * 1024 * 1024) < 8 * 1024 * 1024:
                    print(f"Download: {downloaded * 100 // total}% ({downloaded // 1024 // 1024}MB / {total // 1024 // 1024}MB)", flush=True)
    print("Model download complete", flush=True)


def start_llama_server():
    ensure_model()
    cmd = [
        "/app/llama-server",
        "--model", MODEL_PATH,
        "--ctx-size", CTX_SIZE,
        "--port", str(LLAMA_PORT),
        "--host", "127.0.0.1",
        "--parallel", "1",
        "--cache-type-k", "turbo4",
        "--cache-type-v", "turbo4",
        "-ngl", "99",
    ]
    if MMPROJ_PATH and os.path.exists(MMPROJ_PATH):
        cmd += ["--mmproj", MMPROJ_PATH]

    print(f"Starting llama-server: {' '.join(cmd)}", flush=True)
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

    for i in range(600):
        if proc.stdout:
            import select
            if select.select([proc.stdout], [], [], 0)[0]:
                line = proc.stdout.readline()
                if line:
                    print(f"[llama] {line.rstrip()}", flush=True)

        if proc.poll() is not None:
            remaining = proc.stdout.read() if proc.stdout else ""
            print(f"[llama] exited with code {proc.returncode}:\n{remaining}", flush=True)
            raise RuntimeError(f"llama-server exited with code {proc.returncode}")

        try:
            r = requests.get(f"{LLAMA_URL}/health", timeout=2)
            if r.status_code == 200:
                print("llama-server ready", flush=True)
                return proc
        except Exception:
            pass
        if i % 30 == 0:
            print(f"Waiting for llama-server... {i}s", flush=True)
        time.sleep(1)

    raise RuntimeError("llama-server failed to start within 600 seconds")


_server_proc = start_llama_server()


def handler(job):
    job_input = job.get("input", {})
    stream = job_input.get("stream", False)
    try:
        resp = requests.post(
            f"{LLAMA_URL}/v1/chat/completions",
            json=job_input,
            stream=stream,
            timeout=300,
        )
        resp.raise_for_status()
    except Exception as e:
        return {"error": str(e)}

    if not stream:
        return resp.json()

    def generate():
        for line in resp.iter_lines():
            if line:
                decoded = line.decode("utf-8")
                if decoded.startswith("data: "):
                    yield decoded[6:]

    return generate()


runpod.serverless.start({
    "handler": handler,
    "return_aggregate_stream": True,
})
