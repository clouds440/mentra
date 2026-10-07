from fastapi import Request, Depends
from app.auth.dependencies import require_identity
from app.core.exceptions import AppError


def get_student_profile_service(request: Request):
    return request.app.state.student_profile_service


def require_onboarded_identity(identity=Depends(require_identity), service=Depends(get_student_profile_service)):
    if service.get(identity.learner_id).onboarding_phase != 'complete':
        raise AppError('ONBOARDING_REQUIRED', 'Complete your profile onboarding before entering Mentra.', 409)
    return identity
