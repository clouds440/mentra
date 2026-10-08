from app.core.exceptions import AppError


def not_found():
    return AppError('RAG_NOT_FOUND', 'Material was not found or is no longer available.', 404)


def conflict():
    return AppError('RAG_CONFLICT', 'This material changed. Refresh it before trying again.', 409)


class ExtractionError(ValueError):
    """Safe, actionable parser error suitable for a job status."""
