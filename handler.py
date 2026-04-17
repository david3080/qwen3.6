#!/usr/bin/env python3
"""
RunPod Serverless handler for llama-server (OpenAI-compatible).
- 起動時に llama-server を subprocess で起動
- RunPod の input をそのまま llama-server の /v1/chat/completions に転送
- streaming 対応（generator で逐次返却）
"""
import os
import subprocess
import time
import requests
import runpod

MODEL_PATH = os.environ.get("MODEL_PATH", "/runpod-volume/model.gguf")
MMPROJ_PATH = os.environ.get("MMPROJ_PATH", "/runpod-volume/mmproj.gguf")
CTX_SIZE = os.environ.get("CTX_SIZE", "8192")
LLAMA_PORT = 8080
LLAMA_URL = f"http://127.0.0.1:{LLAMA_PORT}"


def start_llama_server():
    cmd = [
        "llama-server",
        "--model", MODEL_PATH,
        "--ctx-size", CTX_SIZE,
        "--port", str(LLAMA_PORT),
        "--host", "127.0.0.1",
        "--parallel", "1",
        "--cache-type-k", "q4_0",
        "--cache-type-v", "q4_0",
        "-ngl", "99",
    ]
    # mmproj が存在する場合のみ vision を有効化
    if os.path.exists(MMPROJ_PATH):
        cmd += ["--mmproj", MMPROJ_PATH]

    print(f"Starting llama-server: {' '.join(cmd)}", flush=True)
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

    # 起動待ち（最大600秒）
    for i in range(600):
        # 出力をリアルタイムに表示
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


# ワーカー起動時に一度だけ実行
_server_proc = start_llama_server()


def handler(job):
    job_input = job.get("input", {})

    # streaming 判定
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

    # streaming: SSE チャンクを generator で返す
    def generate():
        for line in resp.iter_lines():
            if line:
                decoded = line.decode("utf-8")
                if decoded.startswith("data: "):
                    yield decoded[6:]  # "data: " を除去

    return generate()


runpod.serverless.start({
    "handler": handler,
    "return_aggregate_stream": True,
})
