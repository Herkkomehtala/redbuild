FROM debian:bullseye-slim

RUN apt-get update && apt-get install -y mingw-w64 && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

COPY app/job_runner.py .
COPY app/generators/compiler/ ./generators/compiler/

ENV PYTHONPATH=/workspace
