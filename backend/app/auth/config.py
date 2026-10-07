from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from cryptography.hazmat.primitives.asymmetric import rsa, ec


class ExternalProviderSettings(BaseModel):
    model_config = ConfigDict(extra='forbid')
    issuer: str = Field(min_length=1)
    audience: str = Field(min_length=1)
    public_keys: dict[str, str] = Field(min_length=1)
    algorithm: Literal['RS256', 'ES256'] = 'RS256'
    subject_claim: str = Field(default='sub', min_length=1)
    max_token_lifetime_seconds: int = Field(default=300, ge=1, le=900)
    clock_skew_seconds: int = Field(default=10, ge=0, le=30)

    @model_validator(mode='after')
    def validate_keys(self):
        if self.subject_claim in {'iss', 'aud', 'exp', 'iat', 'nbf'}:
            raise ValueError('subject_claim must identify the external account')
        for key in self.public_keys.values():
            public = load_pem_public_key(key.encode())
            if self.algorithm == 'RS256' and not (isinstance(public, rsa.RSAPublicKey) and public.key_size >= 2048):
                raise ValueError('RS256 requires an RSA public key of at least 2048 bits')
            if self.algorithm == 'ES256' and not (isinstance(public, ec.EllipticCurvePublicKey) and isinstance(public.curve, ec.SECP256R1)):
                raise ValueError('ES256 requires a P-256 public key')
        return self
