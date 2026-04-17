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
        "--reasoning",
        "--reasoning-format", "deepseek",
        "-ngl", "99",
    ]
    # mmproj が存在する場合のみ vision を有効化
    if os.path.exists(MMPROJ_PATH):
        cmd += ["--mmproj", MMPROJ_PATH]

    print(f"Starting llama-server: {' '.join(cmd)}", flush=True)
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

    # 起動待ち（最大180秒）
    for _ in range(180):
        try:
            r = requests.get(f"{LLAMA_URL}/health", timeout=2)
            if r.status_code == 200:
                print("llama-server ready", flush=True)
                return proc
        except Exception:
            pass
        time.sleep(1)

    raise RuntimeError("llama-server failed to start within 180 seconds")


import glob as _glob
import json as _json

def _find_model_files():
    """モデルファイルが見つからない場合、ボリューム内のファイルリストを返す"""
    if not os.path.exists(MODEL_PATH):
        files = _glob.glob("/runpod-volume/**", recursive=True)
        return _json.dumps({"error": f"MODEL_PATH not found: {MODEL_PATH}", "files": sorted(files)[:50]})
    return None

_model_error = _find_model_files()

# ワーカー起動時に一度だけ実行
_server_proc = None if _model_error else start_llama_server()


def handler(job):
    if _model_error:
        return _json.loads(_model_error)

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
