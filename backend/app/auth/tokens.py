"""Verify external assertions against server-configured trust only."""

from datetime import datetime, timezone

import jwt

from app.auth.errors import AuthenticationError
from app.auth.models import VerifiedExternalIdentity


class ExternalTokenVerifier:
    def __init__(self, providers, *, clock=lambda: datetime.now(timezone.utc)):
        self.providers = providers
        self.clock = clock

    def verify(self, provider, token):
        config = self.providers.get(provider)
        if config is None:
            raise AuthenticationError()
        try:
            header = jwt.get_unverified_header(token)
            if header.get('alg') != config.algorithm or header.get('crit'):
                raise AuthenticationError()
            # No URL, jku, embedded JWK, or token-selected algorithm is trusted.
            kid = header.get('kid')
            if kid is None and len(config.public_keys) == 1:
                key = next(iter(config.public_keys.values()))
            else:
                key = config.public_keys.get(kid) if isinstance(kid, str) else None
            if key is None:
                raise AuthenticationError()
            claims = jwt.decode(token, key, algorithms=[config.algorithm],
                issuer=config.issuer, audience=config.audience, leeway=config.clock_skew_seconds,
                options={'require': ['iss', 'aud', 'iat', 'exp', config.subject_claim],
                         'verify_sub': False})
            issued, expires = claims['iat'], claims['exp']
            if type(issued) not in (int, float) or type(expires) not in (int, float):
                raise AuthenticationError()
            now = self.clock().timestamp()
            skew = config.clock_skew_seconds
            if not (0 < expires - issued <= config.max_token_lifetime_seconds and
                    now - config.max_token_lifetime_seconds - skew <= issued <= now + skew and
                    expires > now):
                raise AuthenticationError()
            subject = claims[config.subject_claim]
            if type(subject) not in (str, int) or not str(subject).strip() or len(str(subject)) > 300:
                raise AuthenticationError()
            if str(subject) != str(subject).strip():
                raise AuthenticationError()
            return VerifiedExternalIdentity(provider, str(subject), datetime.fromtimestamp(expires, timezone.utc))
        except (jwt.PyJWTError, ValueError, TypeError, OverflowError) as exc:
            raise AuthenticationError() from exc
