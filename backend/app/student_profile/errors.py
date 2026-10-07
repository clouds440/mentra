from app.core.exceptions import AppError


def conflict(message='Your profile changed elsewhere. Refresh and try again.'):
    return AppError('PROFILE_CONFLICT', message, 409)


def information_required():
    return AppError('PROFILE_INFORMATION_REQUIRED', 'Complete your profile information first.', 409)


class EvaluationUnavailable(RuntimeError):
    """Provider, parsing, or validation failed; persisted evidence remains retryable."""
