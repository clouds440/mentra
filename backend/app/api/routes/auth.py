from fastapi import APIRouter, Depends, Response, Request
from app.auth.dependencies import get_auth_service, require_identity, get_session_token
from app.auth.cookies import COOKIE_NAME, wants_cookie_session, require_cookie_origin, set_session_cookie, clear_session_cookie, session_response
from app.auth.errors import AuthenticationError
from app.auth.models import AuthenticatedIdentity
from app.auth.schemas import RegisterRequest, LoginRequest, ExternalLoginRequest, TokenResponse, IdentityResponse

router = APIRouter(prefix='/auth', tags=['authentication'])


@router.post('/register', response_model=TokenResponse | IdentityResponse, status_code=201)
def register(body: RegisterRequest, request: Request, response: Response, service=Depends(get_auth_service)):
    cookie = wants_cookie_session(request)
    if cookie:
        require_cookie_origin(request)
    return session_response(service.register(body, persistent=cookie), response, cookie)


@router.post('/login', response_model=TokenResponse | IdentityResponse)
def login(body: LoginRequest, request: Request, response: Response, service=Depends(get_auth_service)):
    cookie = wants_cookie_session(request)
    if cookie:
        require_cookie_origin(request)
    return session_response(service.login(body, persistent=cookie), response, cookie)


@router.post('/external', response_model=TokenResponse | IdentityResponse)
def external_login(body: ExternalLoginRequest, request: Request, response: Response, service=Depends(get_auth_service)):
    cookie = wants_cookie_session(request)
    if cookie:
        require_cookie_origin(request)
    return session_response(service.external_login(body), response, cookie)


@router.get('/me', response_model=IdentityResponse)
def identity(request: Request, response: Response, principal: AuthenticatedIdentity = Depends(require_identity)):
    response.headers['Cache-Control'] = 'no-store'
    token = request.cookies.get(COOKIE_NAME)
    if token and not request.headers.get('authorization'):
        set_session_cookie(response, token, principal.expires_at)
    return IdentityResponse(learner_id=principal.learner_id, user_id=principal.user_id,
                            provider=principal.provider, username=principal.username)


@router.post('/logout', status_code=204)
def logout(token: str | None = Depends(get_session_token), service=Depends(get_auth_service)):
    if token:
        try:
            service.logout(token)
        except AuthenticationError:
            pass  # Already expired/revoked: still clear this browser's cookie.
    response = Response(status_code=204)
    clear_session_cookie(response)
    return response
