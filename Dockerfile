FROM ghcr.io/ggml-org/llama.cpp:server-cuda

RUN apt-get update && apt-get install -y python3 python3-pip && \
    pip3 install --no-cache-dir --break-system-packages runpod requests && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

COPY handler.py /handler.py

ENTRYPOINT []
CMD ["python3", "-u", "/handler.py"]
