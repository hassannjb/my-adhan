FROM python:3.11-slim

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Ollama
RUN curl -fsSL https://ollama.com/install.sh | sh

WORKDIR /app

# Install Python deps first (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download the sentence-transformers model
ENV SENTENCE_TRANSFORMERS_HOME=/app/st_cache
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

# Copy source
COPY . .

# Download audio files (excluded from git due to HF binary file restrictions)
RUN mkdir -p lib && \
    curl -fsSL "https://raw.githubusercontent.com/hassannjb/my-adhan/main/lib/makkah_adhan.mp3" -o lib/makkah_adhan.mp3 && \
    curl -fsSL "https://raw.githubusercontent.com/hassannjb/my-adhan/main/lib/fajr.mp3" -o lib/fajr.mp3

# Build RAG index (no API key needed — runs locally)
RUN python rag/ingest.py

# Download Ollama model at build time so the container starts instantly
ENV OLLAMA_MODELS=/app/ollama_models
RUN ollama serve & sleep 6 && ollama pull llama3.2:3b && pkill ollama || true

EXPOSE 7860

COPY start.sh /start.sh
RUN chmod +x /start.sh
CMD ["/start.sh"]
