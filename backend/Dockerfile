FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    BACKEND_HOST=0.0.0.0 \
    BACKEND_PORT=8000 \
    EMBEDDING_CACHE_DIR=/opt/mentra/models/embedding \
    HF_HOME=/opt/mentra/huggingface

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch==2.6.0
RUN pip install --no-cache-dir -r requirements.txt

ARG EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
ENV EMBEDDING_MODEL=${EMBEDDING_MODEL}
COPY bake_embedding_model.py ./
RUN python bake_embedding_model.py

ENV HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1

COPY app ./app
COPY alembic.ini ./
COPY alembic ./alembic

EXPOSE 8000

CMD ["sh", "-c", "python -m app.db.migrate && exec uvicorn app.main:app --host \"$BACKEND_HOST\" --port \"$BACKEND_PORT\""]
