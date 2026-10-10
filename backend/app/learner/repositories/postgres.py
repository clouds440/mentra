"""Small composed SQLAlchemy 2.x PostgreSQL adapter."""

from .postgres_parts.concepts import ConceptsStore
from .postgres_parts.contexts import ContextsStore
from .postgres_parts.evidence import EvidenceStore
from .postgres_parts.states import StatesStore
from .postgres_parts.decisions import DecisionStore
from .postgres_parts.retrieval import RetrievalStore
from .postgres_parts.lifecycle import LifecycleStore


from app.core.logging import workflow_logger

@workflow_logger.connect_module(include_inherited=True, default_outcome='success', policies={'transaction': {'kind':'contextmanager'}, 'bound_transaction': {'kind':'scope'}})
class PostgresLearnerRepository(ConceptsStore, ContextsStore, EvidenceStore, StatesStore,
                                DecisionStore, RetrievalStore, LifecycleStore):
    """Stores share one transaction/session; only domain objects leave the adapter."""
