FROM nvidia/cuda:12.4.1-devel-ubuntu22.04

RUN apt-get update && apt-get install -y \
    python3 python3-pip cmake ninja-build git \
    build-essential libcurl4-openssl-dev libgomp1 \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install --no-cache-dir runpod requests

RUN mkdir -p /app && \
    ln -s /usr/local/cuda/lib64/stubs/libcuda.so /usr/local/cuda/lib64/stubs/libcuda.so.1 && \
    git clone --depth 1 https://github.com/TheTom/llama-cpp-turboquant /llama.cpp && \
    cd /llama.cpp && \
    cmake -B build -DGGML_CUDA=ON -DCMAKE_BUILD_TYPE=Release -DLLAMA_CURL=ON -GNinja \
        -DCMAKE_EXE_LINKER_FLAGS="-L/usr/local/cuda/lib64/stubs" \
        -DCMAKE_SHARED_LINKER_FLAGS="-L/usr/local/cuda/lib64/stubs" && \
    cmake --build build --target llama-server -j$(nproc) && \
    cp build/bin/llama-server /app/llama-server && \
    rm -rf /llama.cpp

COPY handler.py /handler.py

ENTRYPOINT []
CMD ["python3", "-u", "/handler.py"]
