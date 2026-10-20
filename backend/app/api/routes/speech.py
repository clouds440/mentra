from app.files.transient import transcribe_file
from fastapi import APIRouter, Depends, Request, Response
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
