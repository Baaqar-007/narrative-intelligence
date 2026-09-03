FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY graph/ ./graph/
COPY temporal/ ./temporal/
COPY embedding/ ./embedding/
COPY retrieval/ ./retrieval/
COPY api/ ./api/

# Pull pre-built pipeline artifacts + model cache from the Dataset repo
# during HF's own build (same-infrastructure, more reliable than an
# external network dependency). Replaces the old COPY data/ / COPY
# model_cache/ lines - those files are gitignored and never reach HF
# via git push, so they must be fetched here instead.
RUN hf download Xav007/nie-pipeline-artifacts \
    --repo-type dataset --local-dir /app

# IMPORTANT: these offline-mode flags must come AFTER the download step
# above, not before - if set earlier, they'd block the download itself
# from reaching the network during build.
ENV HF_HUB_OFFLINE=1
ENV TRANSFORMERS_OFFLINE=1
ENV SENTENCE_TRANSFORMERS_HOME=/app/model_cache
ENV EMBEDDING_MODEL_PATH=/app/model_cache/all-MiniLM-L6-v2

EXPOSE 7860

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "7860"]