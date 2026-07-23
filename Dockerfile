FROM python:3.11-slim

# Install FFmpeg and dev libraries (faster-whisper's 'av' binding needs them at build time)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ffmpeg \
        libavformat-dev \
        libavcodec-dev \
        libavdevice-dev \
        libavutil-dev \
        libavfilter-dev \
        libswscale-dev \
        libswresample-dev \
        pkg-config \
        build-essential \
        curl \
        ca-certificates && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps (uses layer cache when only source changes)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project
COPY transcribe_server.py .
COPY voice2text.html .

# Cache dir for the whisper model (smaller containers don't have pre-installed model)
ENV HF_HOME=/app/.cache
ENV XDG_CACHE_HOME=/app/.cache

EXPOSE 8080

# Run
CMD ["python", "transcribe_server.py"]
