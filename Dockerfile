FROM nvidia/cuda:12.4.1-devel-ubuntu22.04 AS builder

RUN apt-get update && apt-get install -y \
    cmake ninja-build git build-essential libcurl4-openssl-dev \
    && rm -rf /var/lib/apt/lists/*

RUN git clone --depth 1 https://github.com/TheTom/llama-cpp-turboquant /llama.cpp

RUN cd /llama.cpp && \
    cmake -B build \
      -DGGML_CUDA=ON \
      -DCMAKE_BUILD_TYPE=Release \
      -DLLAMA_CURL=ON \
      -GNinja && \
    cmake --build build --target llama-server -j$(nproc)

FROM nvidia/cuda:12.4.1-runtime-ubuntu22.04

RUN apt-get update && apt-get install -y \
    python3 python3-pip libgomp1 libcurl4 \
    && pip3 install --no-cache-dir --break-system-packages runpod requests \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

COPY --from=builder /llama.cpp/build/bin/llama-server /app/llama-server
COPY --from=builder /llama.cpp/build/ggml/src/libggml*.so* /app/ 2>/dev/null || true
COPY --from=builder /llama.cpp/build/src/libllama.so* /app/ 2>/dev/null || true

ENV LD_LIBRARY_PATH=/app:$LD_LIBRARY_PATH

COPY handler.py /handler.py

ENTRYPOINT []
CMD ["python3", "-u", "/handler.py"]
