from pydantic import Field, SecretStr, field_validator
from app.auth.schemas import ExternalLoginRequest, IdentityResponse, TokenResponse
from app.student_profile.schemas import Contract, ProfileDetails, StudentProfile


class EduVerseStudentRequest(Contract):
    student_id: str = Field(min_length=1, max_length=300)
    token: SecretStr = Field(min_length=1, max_length=16000)
    profile: ProfileDetails

    @field_validator('student_id', mode='before')
    @classmethod
    def normalize_subject(cls, value):
        if type(value) not in (str, int) or str(value) != str(value).strip():
            raise ValueError('student_id must be a nonempty string or integer without surrounding whitespace')
        return str(value)


class EduVerseStudentResponse(IdentityResponse):
    student_id: str
    profile: StudentProfile
    profile_initialized: bool


class EduVerseStudentTokenResponse(TokenResponse):
    student_id: str
    profile: StudentProfile
    profile_initialized: bool


from app.core.logging import workflow_logger

@workflow_logger.operation(outcome='success')
def provision_eduverse_student(request: EduVerseStudentRequest, auth_service, profile_service):
    # Verify subject equality before identity/session provisioning. Existing issuer,
    # audience, algorithm, keys and expiry rules are reused, not platform SDKs.
    session = auth_service.external_login(ExternalLoginRequest(provider='eduverse', token=request.token),
                                          expected_subject=request.student_id)
    profile, initialized = profile_service.initialize_external(session.learner_id, request.profile, 'eduverse')
    # The HTTP adapter hands off this session only once initialization is committed.
    # A failure is safely retryable: identity mapping and initialization are idempotent.
    return session, profile, initialized
