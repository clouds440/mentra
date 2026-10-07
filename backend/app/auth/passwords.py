"""Argon2id password handling. Plaintext is never passed to repositories."""

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, InvalidHashError


class Passwords:
    def __init__(self):
        self.hasher = PasswordHasher()
        # A missing account takes the same expensive verification path.
        self.dummy_hash = self.hasher.hash('unused dummy password for timing protection')

    def hash(self, password):
        return self.hasher.hash(password)

    def verify(self, password, password_hash=None):
        try:
            verified = self.hasher.verify(password_hash or self.dummy_hash, password)
            return verified and password_hash is not None
        except (VerificationError, InvalidHashError):
            return False

    def needs_rehash(self, password_hash):
        return self.hasher.check_needs_rehash(password_hash)
