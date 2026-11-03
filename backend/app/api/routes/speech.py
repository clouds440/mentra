from app.files.transient import transcribe_file
from fastapi import APIRouter, Depends, Request, Response, UploadFile, File, Form
from uuid import UUID
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool
from app.auth.dependencies import require_identity
from app.files.schemas import FileReference

router = APIRouter(prefix="/speech", tags=["speech"])


class Transcription(BaseModel):
    text: str
    language: str
    language_probability: float
    duration_seconds: float
    processing_seconds: float


@router.post('/transcriptions/direct', response_model=Transcription)
async def direct(request: Request, response: Response, file: UploadFile=File(...),
                 operation_id: UUID=Form(...), identity=Depends(require_identity)):
    from app.speech.transient import transcribe_direct
    from app.db.admission import request_capacity
    response.headers['Cache-Control']='no-store'
    processor=request.app.state.speech_service
    try:
        async with request_capacity(request,identity.learner_id,'speech',capacity=4,seconds=90):
            data=await file.read(processor.maximum+1)
            return await run_in_threadpool(transcribe_direct,request.app.state.files_service,
                processor,identity.learner_id,str(operation_id),data)
    finally:
        await file.close()


@router.post("/transcriptions", response_model=Transcription)
async def transcribe(
    request: Request,
    response: Response,
    body: FileReference,
    identity=Depends(require_identity),
):
    response.headers["Cache-Control"] = "no-store"
    from app.db.admission import request_capacity

    async with request_capacity(
        request, identity.learner_id, "speech", capacity=4, seconds=90
    ):
        return await run_in_threadpool(
            transcribe_file,
            request.app.state.files_service,
            request.app.state.speech_service,
            identity.learner_id,
            str(body.file_id),
        )
