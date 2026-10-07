from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.langchain.model_factory import ModelConfigurationError, ModelFactory
from app.rag.embeddings import EmbeddingModelError, EmbeddingService
from app.rag.vector_store import VectorStore, VectorStoreError

router = APIRouter(tags=["health"])


@router.get("/health", summary="Health check")
async def health_check() -> dict[str, str]:
    return {"status": "ok", "service": "mentra-api"}


@router.get("/health/ready", summary="Readiness diagnostics")
def readiness_check(request: Request) -> JSONResponse:
    checks: dict[str, dict[str, object]] = {}
    is_ready = True

    configured_model_factory = getattr(request.app.state, "model_factory", None)
    if configured_model_factory is None:
        checks["ai"] = {"status": "error", "message": "Model factory is not initialized."}
        is_ready = False
    else:
        model_factory: ModelFactory = configured_model_factory
        try:
            model_factory.validate_configuration()
            checks["ai"] = {"status": "ok"}
        except ModelConfigurationError as exc:
            checks["ai"] = {"status": "error", "message": str(exc)}
            is_ready = False

    configured_embedding_service = getattr(
        request.app.state, "embedding_service", None
    )
    if configured_embedding_service is None:
        checks["embedding"] = {
            "status": "error",
            "message": "Embedding service is not initialized.",
        }
        is_ready = False
    else:
        embedding_service: EmbeddingService = configured_embedding_service
        try:
            checks["embedding"] = {
                "status": "ok",
                "loaded": True,
                "model_name": embedding_service.model_name,
                "model_version": embedding_service.model_version,
                "dimension": embedding_service.dimension,
            }
        except EmbeddingModelError as exc:
            checks["embedding"] = {"status": "error", "message": str(exc)}
            is_ready = False

    configured_vector_store = getattr(request.app.state, "vector_store", None)
    if configured_vector_store is None:
        checks["qdrant"] = {
            "status": "error",
            "message": "Vector store is not initialized.",
        }
        is_ready = False
    else:
        vector_store: VectorStore = configured_vector_store
        try:
            vector_store.ensure_collection()
            checks["qdrant"] = {
                "status": "ok",
                "collection": vector_store.collection_name,
            }
        except VectorStoreError as exc:
            checks["qdrant"] = {"status": "error", "message": str(exc)}
            is_ready = False

    return JSONResponse(
        status_code=200 if is_ready else 503,
        content={
            "status": "ready" if is_ready else "not_ready",
            "service": "mentra-api",
            "checks": checks,
        },
    )
