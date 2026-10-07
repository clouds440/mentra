"""Domain exceptions raised by Learner Engine services."""


class LearnerError(Exception):
    """Base class for expected Learner Engine failures."""


class ConceptNotFoundError(LearnerError):
    """Raised when a requested canonical concept does not exist."""


class LearningContextNotFoundError(LearnerError):
    """Raised when a requested learning context does not exist."""


class InvalidEvidenceError(LearnerError):
    """Raised when evidence cannot be accepted under learner policy."""
