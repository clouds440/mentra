"""Persistence ports used internally by Learner Engine services."""

from app.learner.repositories.protocols import (
    ConceptRepository,
    EvidenceRepository,
    LearnerRepository,
    LearnerStateRepository,
    LearningContextRepository,
)

__all__ = [
    "ConceptRepository",
    "EvidenceRepository",
    "LearnerRepository",
    "LearnerStateRepository",
    "LearningContextRepository",
    "PostgresLearnerRepository",
]


def __getattr__(name: str):
    if name == 'PostgresLearnerRepository':
        from app.learner.repositories.postgres import PostgresLearnerRepository
        return PostgresLearnerRepository
    raise AttributeError(name)
