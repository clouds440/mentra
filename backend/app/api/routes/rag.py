"""Authenticated material APIs. Synchronous workflows run off the event loop."""
import json
from typing import Annotated
from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool
from app.student_profile.dependencies import require_onboarded_identity
from app.learner.schemas import ResolveLearningContextRequest, ContextTransitionRequest, ActivateLearningContextRequest
from app.rag.schemas import DocumentUpdate, RevisionRequest, SearchRequest, RetrievalResult
from app.core.exceptions import AppError

router = APIRouter(tags=['materials'])


def rag(request: Request):
    return request.app.state.rag_service


class ContextCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1, max_length=200)
    activate: bool = False


class ContextTransition(BaseModel):
    model_config = ConfigDict(extra='forbid')
    status: str = Field(pattern='^(ACTIVE|RELATED|DORMANT|ARCHIVED)$')


class ConceptTags(BaseModel):
    model_config = ConfigDict(extra='forbid')
    labels: list[Annotated[str, Field(min_length=1, max_length=200)]] = Field(max_length=20)
    expected_revision: int = Field(ge=1)


@router.get('/learning-contexts')
def list_contexts(offset: int = Query(default=0, ge=0), limit: int = Query(default=100, ge=1, le=100),
                  status: str | None = Query(default=None, pattern='^(ACTIVE|RELATED|DORMANT|ARCHIVED)$'),
                  service=Depends(rag), identity=Depends(require_onboarded_identity)):
    contexts = sorted(service.context_summaries(identity.learner_id), key=lambda context: context.context_id)
    if status:
        contexts = [context for context in contexts if context.status == status]
    return contexts[offset:offset + limit]


@router.post('/learning-contexts')
def create_context(body: ContextCreate, service=Depends(rag), identity=Depends(require_onboarded_identity)):
    return service.learner.resolve_learning_context(ResolveLearningContextRequest(
        learner_id=identity.learner_id, name=body.name, activate=body.activate))


@router.patch('/learning-contexts/{context_id}')
def transition_context(context_id: str, body: ContextTransition, service=Depends(rag), identity=Depends(require_onboarded_identity)):
    service.context_summaries(identity.learner_id, [context_id])
    if body.status == 'ACTIVE':
        return service.learner.activate_learning_context(ActivateLearningContextRequest(
            learner_id=identity.learner_id, context_id=context_id, exclusive=True))
    return service.learner.transition_context_state(ContextTransitionRequest(
        learner_id=identity.learner_id, context_id=context_id, status=body.status, reason='explicit_library_action'))


@router.get('/rag/capabilities')
def get_capabilities(service=Depends(rag), identity=Depends(require_onboarded_identity)):
    return service.capabilities()


@router.get('/documents')
def list_documents(offset: int = Query(default=0, ge=0), limit: int = Query(default=25, ge=1, le=100),
                   archived: bool | None = None, context_id: str | None = None,
                   service=Depends(rag), identity=Depends(require_onboarded_identity)):
    if context_id is not None:
        service.context_summaries(identity.learner_id, [context_id])
    return service.repository.list_documents(identity.learner_id, offset, limit, archived, context_id)


async def accept(file, title, contexts, key, identity, service, document_id=None, expected_revision=None):
    try:
        ids = json.loads(contexts)
        if not isinstance(ids, list) or not all(isinstance(v, str) for v in ids):
            raise ValueError()
    except (ValueError, TypeError):
        raise AppError('RAG_INVALID_CONTEXTS', 'Context IDs must be a JSON string array.', 422)
    try:
        return await run_in_threadpool(service.accept_upload, identity.learner_id, file.file, file.filename or 'material',
            title, ids, key, document_id, expected_revision)
    finally:
        await file.close()


@router.post('/documents', status_code=202)
async def upload_document(file: Annotated[UploadFile, File()], context_ids: Annotated[str, Form()],
    idempotency_key: Annotated[str, Form()], title: Annotated[str, Form()] = '',
    service=Depends(rag), identity=Depends(require_onboarded_identity)):
    return await accept(file, title, context_ids, idempotency_key, identity, service)


@router.post('/documents/{document_id}/versions', status_code=202)
async def replace_document(document_id: str, file: Annotated[UploadFile, File()],
    expected_revision: Annotated[int, Form(ge=1)], idempotency_key: Annotated[str, Form()],
    service=Depends(rag), identity=Depends(require_onboarded_identity)):
    doc = await run_in_threadpool(service.get_document, identity.learner_id, document_id)
    return await accept(file, doc['title'], json.dumps(doc['context_ids']), idempotency_key, identity, service,
                        document_id, expected_revision)


@router.get('/documents/{document_id}')
def get_document(document_id: str, service=Depends(rag), identity=Depends(require_onboarded_identity)):
    return service.get_document(identity.learner_id, document_id)


@router.get('/documents/{document_id}/versions')
def list_versions(document_id: str, offset: int = Query(default=0, ge=0), limit: int = Query(default=25, ge=1, le=100),
                  service=Depends(rag), identity=Depends(require_onboarded_identity)):
    return service.repository.list_versions(identity.learner_id, document_id, offset, limit)


@router.patch('/documents/{document_id}')
def update_document(document_id: str, body: DocumentUpdate, service=Depends(rag), identity=Depends(require_onboarded_identity)):
    return service.update_document(identity.learner_id, document_id, body)


@router.delete('/documents/{document_id}', status_code=202)
def delete_document(document_id: str, service=Depends(rag), identity=Depends(require_onboarded_identity)):
    return service.repository.request_delete(identity.learner_id, document_id)


@router.post('/documents/{document_id}/concepts')
def tag_document(document_id: str, body: ConceptTags, service=Depends(rag), identity=Depends(require_onboarded_identity)):
    return service.tag_document(identity.learner_id, document_id, body.labels, body.expected_revision)


@router.post('/documents/{document_id}/reindex', status_code=202)
def reindex_document(document_id: str, body: RevisionRequest, service=Depends(rag), identity=Depends(require_onboarded_identity)):
    return service.repository.reindex(identity.learner_id, document_id, body, service.config())


@router.get('/rag/jobs/{job_id}')
def get_job(job_id: str, service=Depends(rag), identity=Depends(require_onboarded_identity)):
    return service.repository.get_job(identity.learner_id, job_id)


@router.post('/rag/jobs/{job_id}/retry', status_code=202)
def retry_job(job_id: str, service=Depends(rag), identity=Depends(require_onboarded_identity)):
    return service.repository.retry(identity.learner_id, job_id)


@router.post('/rag/search', response_model=RetrievalResult)
def search(body: SearchRequest, service=Depends(rag), identity=Depends(require_onboarded_identity)):
    return service.search(identity.learner_id, body)


@router.get('/rag/chunks/{chunk_id}')
def get_chunk(chunk_id: str, include_archived: bool = False, service=Depends(rag), identity=Depends(require_onboarded_identity)):
    return service.get_chunk(identity.learner_id, chunk_id, include_archived)


@router.get('/documents/{document_id}/versions/{version_id}/source')
def source(document_id: str, version_id: str, include_archived: bool = False,
           service=Depends(rag), identity=Depends(require_onboarded_identity)):
    path, version = service.source(identity.learner_id, document_id, version_id, include_archived)
    return FileResponse(path, media_type=version['media_type'], filename=version['filename'],
                        headers={'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff'})


@router.get('/documents/{document_id}/versions/{version_id}/chunks')
def source_chunks(document_id: str, version_id: str, include_archived: bool = False, offset: int = Query(default=0, ge=0),
                  generation_id: str | None = None, service=Depends(rag), identity=Depends(require_onboarded_identity)):
    return service.source_chunks(identity.learner_id, document_id, version_id, include_archived, offset, generation_id)
