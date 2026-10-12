"""Application composition; infrastructure imports are deliberately lazy."""


from app.core.logging import workflow_logger

@workflow_logger.operation(outcome='success')
def create_learner_engine(llm=None):
    from app.db.database import get_session_factory
    from app.learner.engine import LearnerEngine
    from app.learner.repositories.postgres import PostgresLearnerRepository

    if llm is not None:
        from app.langchain.concept_identity import ConceptIdentityResolver
        resolver = ConceptIdentityResolver(llm)
    else:
        resolver = None
    return LearnerEngine(PostgresLearnerRepository(get_session_factory()), generated_concept_resolver=resolver)
