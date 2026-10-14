from fastapi import APIRouter, Depends, File, Request, Response, UploadFile
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from app.auth.dependencies import require_identity
from app.core.exceptions import AppError

router = APIRouter(prefix='/speech', tags=['speech'], dependencies=[Depends(require_identity)])
MIME_TYPES = {'audio/webm', 'video/webm', 'audio/ogg', 'application/ogg', 'audio/mp4', 'video/mp4',
              'audio/wav', 'audio/x-wav', 'audio/mpeg', 'audio/aac', 'audio/flac'}


class Transcription(BaseModel):
    text: str
    language: str
    language_probability: float
    duration_seconds: float
    processing_seconds: float


@router.post('/transcriptions', response_model=Transcription)
async def transcribe(request: Request, response: Response, audio: UploadFile = File(...), identity=Depends(require_identity)):
    response.headers['Cache-Control'] = 'no-store'
    try:
        if (audio.content_type or '').split(';')[0].lower() not in MIME_TYPES:
            raise AppError('SPEECH_FORMAT', 'This recording format is unsupported.', 415)
        service = request.app.state.speech_service
        data = await audio.read(service.maximum + 1)
        from app.db.admission import request_capacity
        async with request_capacity(request, identity.learner_id, 'speech', capacity=4, seconds=90):
            return await run_in_threadpool(service.transcribe, data, None)
    finally:
        await audio.close()
