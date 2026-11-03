# Offline source refresh over the clean, pinned build recorded in release-build.txt.
# Verify the base image ID and RootFS layer prefix in image-manifest.json.
FROM mentra-backend:embedding-complete-20261103
USER root
COPY app /app/app
COPY scripts /app/scripts
COPY alembic /app/alembic
COPY model_assets.py bake_embedding_model.py bake_reranker_model.py /app/
RUN python -c "from model_assets import write_manifest; write_manifest('/opt/mentra/models/embedding',role='embedding'); write_manifest('/opt/mentra/models/reranker',role='reranker')"
USER 10001:10001
