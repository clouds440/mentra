from app.core.exceptions import AppError


class AuthenticationError(AppError):
    def __init__(self):
        super().__init__('AUTHENTICATION_FAILED', 'Authentication failed.', 401)


class AccountExistsError(AppError):
    def __init__(self):
        super().__init__('ACCOUNT_EXISTS', 'That username is already registered.', 409)
