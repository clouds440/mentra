from fastapi import Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.auth.errors import AuthenticationError
from app.auth.models import AuthenticatedIdentity
from app.auth.cookies import COOKIE_NAME, require_cookie_origin

bearer = HTTPBearer(auto_error=False)


def get_auth_service(request: Request):
    return request.app.state.auth_service


def get_session_token(request: Request,
                      credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> str | None:
    if credentials is not None:
        return credentials.credentials
    token = request.cookies.get(COOKIE_NAME)
    if token and request.method not in {'GET', 'HEAD', 'OPTIONS'}:
        require_cookie_origin(request)
    return token


def require_identity(token: str | None = Depends(get_session_token),
                     service=Depends(get_auth_service)) -> AuthenticatedIdentity:
    if token is None:
        raise AuthenticationError()
    return service.authenticate(token)
