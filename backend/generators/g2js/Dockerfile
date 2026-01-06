# Stage 1: Build C# Components using Mono
FROM mono:6.8 AS builder
WORKDIR /src

# We expect the build context to be 'backend', so we copy from app/generators/g2js/csharp_src
# structure in context: app/generators/g2js/csharp_src/...
COPY app/generators/g2js/csharp_src/ .

# Build the project and the assemblies in Release mode
# Note: The paths in .csproj files might need adjustment if they refer to relative paths.
# Assuming standard structure, we run xbuild.
RUN xbuild GadgetToJScript/GadgetToJScript.csproj /t:Build /p:Configuration=Release && \
    xbuild TestAssembly/TestAssembly.csproj /t:Build /p:Configuration=Release && \
    xbuild ShellcodeLoader/ShellcodeLoader.csproj /t:Build /p:Configuration=Release

# Stage 2: Runtime Environment (Wine + Python)
FROM debian:bullseye-slim

# Set environment variables for Wine
ENV WINEPREFIX=/root/.wine64 \
    WINEARCH=win64 \
    WINEDEBUG=-all \
    WINEDLLOVERRIDES="mshtml=" \
    PYTHONUNBUFFERED=1

# Install Wine, winetricks, and dependencies + Initialize Wine + Install .NET 4.8 + Cleanup
RUN dpkg --add-architecture i386 && \
    sed -i "s/main/main contrib/g" /etc/apt/sources.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        wine \
        wine32 \
        wine64 \
        libwine \
        winetricks \
        xvfb \
        xauth \
        cabextract \
        wget \
        ca-certificates \
        procps \
        python3 \
        python3-pip \
    && rm -rf /var/lib/apt/lists/* && \
    ln -s /usr/bin/python3 /usr/bin/python && \
    \
    wineboot --init && \
    while pgrep wineserver > /dev/null; do sleep 1; done && \
    \
    xvfb-run winetricks -q --force dotnet48 && \
    while pgrep wineserver > /dev/null; do sleep 1; done && \
    \
    rm -rf /root/.cache/winetricks /tmp/*

WORKDIR /app

# Install python dependencies? 
# The generic job runner depends on: 'kubernetes', 'flask' (maybe?), 'jinja2'.
# Let's see what requirements.txt has.
# We'll copy requirements.txt from context.
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy Compiled Binaries from Builder
RUN mkdir -p /app/bin
COPY --from=builder /src/GadgetToJScript/bin/Release/GadgetToJScript.exe /app/bin/
COPY --from=builder /src/GadgetToJScript/bin/Release/GadgetToJScript.exe.config /app/bin/
COPY --from=builder /src/GadgetToJScript/bin/Release/NDesk.Options.dll /app/bin/
COPY --from=builder /src/ShellcodeLoader/bin/Release/ShellcodeLoader.dll /app/bin/
COPY --from=builder /src/TestAssembly/bin/Release/TestAssembly.dll /app/bin/

# Copy Resources
COPY app/generators/g2js/resources/Microsoft.PowerShell.Editor.dll /app/bin/
COPY app/generators/g2js/resources/msgbox.bin /app/bin/

# Setup App Structure
# We need to recreate the package structure expected by importlib: app.generators.g2js
RUN mkdir -p app/generators/g2js

RUN touch app/__init__.py
RUN touch app/generators/__init__.py

# Copy Generic Job Runner
COPY app/job_runner.py ./app/
COPY app/k8s_client.py ./app/
# (k8s_client might be imported by job_runner? job_runner imports 'argparse, importlib...')
# It does NOT import k8s_client. But let's check dependencies of 'app'.

# Copy G2JS Generator Code
COPY app/generators/g2js/ ./app/generators/g2js/

# Set Environment for Wine to ignore mono
ENV WINEDLLOVERRIDES="mscoree=n;mshtml="

# Entrypoint
ENTRYPOINT ["python3", "-m", "app.job_runner"]