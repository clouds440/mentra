from uuid import UUID
from fastapi import APIRouter, Depends, Response
from app.auth.dependencies import require_identity
from app.student_profile.dependencies import get_student_profile_service
from app.student_profile.schemas import StudentProfile, ProfileUpdate, VersionRequest, AnswerRequest, CalibrationCompletionRequest, CalibrationView, CalibrationResult

router = APIRouter(prefix='/student-profile', tags=['student profile'])


@router.get('', response_model=StudentProfile)
def get_profile(response: Response, identity=Depends(require_identity), service=Depends(get_student_profile_service)):
    response.headers['Cache-Control'] = 'no-store'
    return service.get(identity.learner_id)


@router.put('/details', response_model=StudentProfile)
def update_profile(body: ProfileUpdate, identity=Depends(require_identity), service=Depends(get_student_profile_service)):
    return service.update_details(identity.learner_id, body)


@router.get('/calibration', response_model=CalibrationView | None)
def get_calibration(response: Response, identity=Depends(require_identity), service=Depends(get_student_profile_service)):
    response.headers['Cache-Control'] = 'no-store'
    return service.calibration.get(identity.learner_id)


@router.post('/calibration', response_model=CalibrationView)
def start_calibration(identity=Depends(require_identity), service=Depends(get_student_profile_service)):
    return service.calibration.start(identity.learner_id)


@router.post('/calibration/skip', response_model=StudentProfile)
def skip_calibration(body: VersionRequest, identity=Depends(require_identity), service=Depends(get_student_profile_service)):
    return service.calibration.skip(identity.learner_id, body)


@router.post('/calibration/evaluate', response_model=StudentProfile)
async def evaluate_calibration(identity=Depends(require_identity), service=Depends(get_student_profile_service)):
    return await service.calibration.retry_evaluation(identity.learner_id)


@router.patch('/calibration/{attempt_id}/answers', response_model=CalibrationView)
def save_answer(attempt_id: UUID, body: AnswerRequest, identity=Depends(require_identity), service=Depends(get_student_profile_service)):
    return service.calibration.answer(identity.learner_id, str(attempt_id), body)


@router.post('/calibration/{attempt_id}/complete', response_model=CalibrationResult)
async def complete_calibration(attempt_id: UUID, body: CalibrationCompletionRequest, identity=Depends(require_identity), service=Depends(get_student_profile_service)):
    return await service.calibration.complete(identity.learner_id, str(attempt_id), body)
