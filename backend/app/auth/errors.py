from app.core.exceptions import AppError


class AuthenticationError(AppError):
    def __init__(self):
        super().__init__('AUTHENTICATION_FAILED', 'Authentication failed.', 401)


class AccountExistsError(AppError):
    def __init__(self):
        super().__init__('ACCOUNT_EXISTS', 'That username is already registered.', 409)


class PasswordChangeError(AppError):
    def __init__(self):
        super().__init__('PASSWORD_CHANGE_FAILED', 'Your current password is incorrect.', 400)
