#!/bin/bash
set -e

export OLLAMA_MODELS=/app/ollama_models
export SENTENCE_TRANSFORMERS_HOME=/app/st_cache

# Start Ollama server in background
ollama serve &

# Wait until Ollama is accepting connections
echo "Waiting for Ollama..."
until curl -s http://localhost:11434/api/tags > /dev/null 2>&1; do
    sleep 1
done
echo "Ollama ready."

# Start FastAPI on the port HF Spaces expects
exec uvicorn api.main:app --host 0.0.0.0 --port 7860
