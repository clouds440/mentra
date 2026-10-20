from typing import Literal
from uuid import UUID
from fastapi import APIRouter, Depends, File, Form, UploadFile, Request
from starlette.concurrency import run_in_threadpool
from app.auth.dependencies import require_identity
from app.student_profile.dependencies import require_onboarded_identity
from app.files.delivery import deliver

router = APIRouter(prefix="/files", tags=["files"])


@router.post("/uploads")
async def upload(
    request: Request,
    file: UploadFile = File(...),
    purpose: Literal["chat", "library", "assessment", "speech"] = Form(...),
    operation_key: str = Form(min_length=1, max_length=120),
    identity=Depends(require_identity),
):
    try:
        if purpose != "speech":
            await run_in_threadpool(
                require_onboarded_identity,
                identity,
                request.app.state.student_profile_service,
            )
        from app.db.admission import request_capacity

        async with request_capacity(
            request, identity.learner_id, "upload", capacity=4, seconds=300
        ):
            return await run_in_threadpool(
                request.app.state.files_service.upload,
                identity.learner_id,
                file.file,
                file.filename,
                purpose,
                operation_key,
            )
    finally:
        await file.close()


@router.get("/uploads/{operation_key}")
async def receipt(
    operation_key: str, request: Request, identity=Depends(require_identity)
):
    return await run_in_threadpool(
        request.app.state.files_service.receipt, identity.learner_id, operation_key
    )


@router.delete("/uploads/{file_id}", status_code=204)
async def cancel(file_id: UUID, request: Request, identity=Depends(require_identity)):
    await run_in_threadpool(
        request.app.state.files_service.cancel, identity.learner_id, str(file_id)
    )


@router.get("/{file_id}")
async def metadata(file_id: UUID, request: Request, identity=Depends(require_identity)):
    files = request.app.state.files_service
    return files.public(
        await run_in_threadpool(files.metadata, identity.learner_id, str(file_id))
    )


@router.api_route("/{file_id}/content", methods=["GET", "HEAD"])
async def content(
    file_id: UUID,
    request: Request,
    binding_id: UUID,
    disposition: Literal["inline", "attachment"] = "attachment",
    include_archived: bool = False,
    identity=Depends(require_identity),
):
    return await deliver(
        request,
        identity.learner_id,
        str(file_id),
        str(binding_id),
        disposition,
        include_archived,
    )
