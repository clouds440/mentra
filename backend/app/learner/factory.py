"""Application composition; infrastructure imports are deliberately lazy."""


def create_learner_engine():
    from app.db.database import get_session_factory
    from app.learner.engine import LearnerEngine
    from app.learner.repositories.postgres import PostgresLearnerRepository

    return LearnerEngine(PostgresLearnerRepository(get_session_factory()))
