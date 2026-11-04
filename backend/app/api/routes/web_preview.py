from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field

from app.student_profile.dependencies import require_onboarded_identity
from app.web_search.preview import PreviewResult, check_preview

router = APIRouter(prefix='/web', tags=['web sources'])


class PreviewRequest(BaseModel):
    url: str = Field(max_length=2048)


@router.post('/preview', response_model=PreviewResult)
async def preview(body: PreviewRequest, response: Response, _identity=Depends(require_onboarded_identity)):
    response.headers['Cache-Control'] = 'no-store'
    return await check_preview(body.url)
