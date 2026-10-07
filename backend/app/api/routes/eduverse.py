from fastapi import APIRouter, Request, Response, Depends
from app.auth.dependencies import get_auth_service
from app.auth.cookies import wants_cookie_session, require_cookie_origin, session_response
from app.student_profile.dependencies import get_student_profile_service
from app.integrations.eduverse import EduVerseStudentRequest, EduVerseStudentResponse, EduVerseStudentTokenResponse, provision_eduverse_student

router = APIRouter(prefix='/integrations/eduverse', tags=['EduVerse integration contract'])


@router.post('/students', response_model=EduVerseStudentTokenResponse | EduVerseStudentResponse)
def provision_student(body: EduVerseStudentRequest, request: Request, response: Response,
                      auth=Depends(get_auth_service), profiles=Depends(get_student_profile_service)):
    cookie = wants_cookie_session(request)
    if cookie:
        require_cookie_origin(request)
    token, profile, initialized = provision_eduverse_student(body, auth, profiles)
    identity = session_response(token, response, cookie)
    response.status_code = 201 if initialized else 200
    contract = EduVerseStudentResponse if cookie else EduVerseStudentTokenResponse
    return contract(**identity.model_dump(), student_id=body.student_id, profile=profile, profile_initialized=initialized)
