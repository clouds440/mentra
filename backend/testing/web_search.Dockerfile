# Disposable verification image. Production uses backend/Dockerfile.
FROM mentra-backend
RUN pip install --no-cache-dir mcp==2.3.0 sse-starlette==3.0.3 uvicorn==0.31.1 markdown-it-py==4.0.0 && pip check
