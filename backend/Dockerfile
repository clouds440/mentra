FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    BACKEND_HOST=0.0.0.0 \
    BACKEND_PORT=8000 \
    EMBEDDING_CACHE_DIR=/opt/mentra/models/embedding \
    HF_HOME=/opt/mentra/huggingface

WORKDIR /app

# Local OCR and scanned-PDF rasterization; no document content leaves the worker.
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng poppler-utils && rm -rf /var/lib/apt/lists/*

RUN python -m pip install --no-cache-dir pip==26.2.2
RUN pip install --no-cache-dir --no-deps --index-url https://download.pytorch.org/whl/cpu torch==2.14.1
COPY requirements.txt requirements.lock ./
RUN pip install --no-cache-dir -r requirements.txt -c requirements.lock
RUN python -m pip check

ARG EMBEDDING_MODEL=intfloat/multilingual-e5-small
ENV EMBEDDING_MODEL=${EMBEDDING_MODEL}
COPY bake_embedding_model.py ./
RUN python bake_embedding_model.py

ARG RAG_RERANKER_MODEL=
ENV RAG_RERANKER_MODEL=${RAG_RERANKER_MODEL}
COPY bake_reranker_model.py ./
RUN python bake_reranker_model.py

ARG SPEECH_MODEL=base
ENV SPEECH_MODEL=${SPEECH_MODEL} SPEECH_MODEL_PATH=/opt/mentra/models/speech
COPY bake_speech_model.py ./
RUN python bake_speech_model.py

# Token budgeting stays offline during requests; bake the verified vocabulary.
ENV TIKTOKEN_CACHE_DIR=/opt/mentra/tokenizers
RUN python -c "import tiktoken; tiktoken.get_encoding('cl100k_base')"

ENV HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1

COPY app ./app
COPY scripts ./scripts
COPY alembic.ini ./
COPY alembic ./alembic

RUN groupadd --gid 10001 mentra \
    && useradd --uid 10001 --gid mentra --create-home --shell /usr/sbin/nologin mentra \
    && mkdir -p /var/log/mentra /app/logs/backend \
    && chown -R mentra:mentra /var/log/mentra /app/logs /home/mentra /opt/mentra/huggingface

ENV HOME=/home/mentra
USER 10001:10001

EXPOSE 8000

CMD ["sh", "-c", "python -m app.db.migrate && exec uvicorn app.main:app --no-access-log --host \"$BACKEND_HOST\" --port \"$BACKEND_PORT\""]
