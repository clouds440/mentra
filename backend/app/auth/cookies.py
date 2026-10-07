"""HTTP-only session transport. Cookie requests require a trusted browser origin."""
from datetime import datetime, timezone

from fastapi import Request, Response

from app.core.config import settings
from app.core.exceptions import AppError
from app.auth.schemas import TokenResponse, IdentityResponse

COOKIE_NAME = 'mentra_session'
COOKIE_PATH = '/api/v1'
COOKIE_MAX_AGE = 400 * 24 * 60 * 60


def wants_cookie_session(request: Request) -> bool:
    return request.headers.get('X-Mentra-Session') == 'cookie'


def require_cookie_origin(request: Request):
    origin = request.headers.get('origin')
    allowed = {value.rstrip('/') for value in [*settings.allowed_origins, settings.frontend_origin]}
    if origin not in allowed:
        raise AppError('REQUEST_NOT_ALLOWED', 'This request is not allowed from this origin.', 403)


def secure_cookie():
    return settings.auth_cookie_secure or settings.app_env.lower() not in {'development', 'dev', 'test'}


def set_session_cookie(response: Response, token: str, expires_at=None):
    secure = secure_cookie()
    if settings.auth_cookie_same_site == 'none' and not secure:
        raise RuntimeError('SameSite=None requires AUTH_COOKIE_SECURE=true and HTTPS')
    max_age = COOKIE_MAX_AGE if expires_at is None else max(1, min(COOKIE_MAX_AGE,
        int((expires_at - datetime.now(timezone.utc)).total_seconds())))
    response.set_cookie(COOKIE_NAME, token, max_age=max_age, path=COOKIE_PATH,
                        httponly=True, secure=secure, samesite=settings.auth_cookie_same_site)
    response.headers['Cache-Control'] = 'no-store'


def clear_session_cookie(response: Response):
    response.delete_cookie(COOKIE_NAME, path=COOKIE_PATH, httponly=True,
                           secure=secure_cookie(), samesite=settings.auth_cookie_same_site)
    response.headers['Cache-Control'] = 'no-store'


def session_response(result: TokenResponse, response: Response, cookie: bool):
    response.headers['Cache-Control'] = 'no-store'
    if cookie:
        set_session_cookie(response, result.access_token, result.expires_at)
        return IdentityResponse(learner_id=result.learner_id, user_id=result.user_id,
                                provider=result.provider, username=result.username)
    return result
