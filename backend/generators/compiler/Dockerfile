FROM python:3.9-slim

WORKDIR /app

RUN apt-get update && \
    apt-get install -y mingw-w64 && \
    rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir Jinja2==3.1.6

RUN mkdir -p app/generators/compiler

RUN touch app/__init__.py
RUN touch app/generators/__init__.py

COPY app/job_runner.py ./app/
COPY app/generators/compiler/ ./app/generators/compiler/
