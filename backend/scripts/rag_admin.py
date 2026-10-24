"""Operator CLI only; never exposed through ordinary learner HTTP."""
import argparse
import json
from uuid import uuid4
from app.core.config import settings
from app.db.database import init_db
from app.learner.factory import create_learner_engine
from app.rag.embeddings import SentenceTransformerEmbeddingService
from app.rag.qdrant_store import QdrantVectorStore
from app.rag.factory import create_rag_service
from app.core.identifiers import canonical_learner_id


def main():
    parser = argparse.ArgumentParser(description='Inspect RAG index identity or queue resumable owned reindex jobs.')
    parser.add_argument('operation', choices=['initialize', 'health', 'rebuild', 'reset-embeddings'])
    parser.add_argument('--learner-id')
    parser.add_argument('--apply', action='store_true', help='Apply the operation (reset-embeddings deletes the configured vector index); otherwise report counts.')
    parser.add_argument('--run-id', help='Reuse this UUID to make an operator rebuild idempotent; rebuild only.')
    args = parser.parse_args()
    if args.operation == 'reset-embeddings' and (args.run_id or args.learner_id):
        parser.error('reset-embeddings resets the whole configured index and always starts a fresh rebuild run')
    args.run_id = args.run_id or str(uuid4())
    init_db()
    embedding = SentenceTransformerEmbeddingService(settings)
    vector = QdrantVectorStore(settings, embedding)
    service = create_rag_service(create_learner_engine(), embedding, vector)
    try:
        if args.operation == 'initialize':
            # Creates only a missing collection/indexes; incompatible existing
            # dimensions/model identity fail closed without deleting anything.
            vector.initialize_chunk_indexes()
            print(json.dumps(dict(status='initialized', index=vector.collection_name)))
            return
        if args.operation == 'reset-embeddings':
            # Run with API and all ingestion/assessment workers stopped. No source
            # tables or files are deleted; PostgreSQL remains canonical.
            from sqlalchemy import select
            from app.rag.repositories.tables import documents
            with service.repository.sessions() as session:
                owners = list(session.scalars(select(documents.c.learner_id).distinct()))
            if not args.apply:
                print(json.dumps(dict(dry_run=True, index=vector.collection_name, learners=len(owners),
                    rebuilds=[service.repository.queue_rebuild(owner, args.run_id, service.config(),
                        reset_embeddings=True) for owner in owners])))
                return
            vector.reset_collection()
            for owner in owners:
                print(json.dumps(service.repository.queue_rebuild(owner, canonical_learner_id(args.run_id),
                    service.config(), dry_run=False, reset_embeddings=True)))
            print(json.dumps(dict(status='reset', index=vector.collection_name, learners=len(owners))))
            return
        if args.operation == 'health':
            vector.validate_collection()
            health = service.repository.index_health(canonical_learner_id(args.learner_id) if args.learner_id else None)
            checked = health.pop('active_generations')
            mismatches = []
            for generation in checked:
                count = vector.count_chunks(str(generation['learner_id']), generation['id'])
                if count != generation['chunk_count'] or generation['config'] != service.config():
                    mismatches.append(dict(generation_id=generation['id'], expected=generation['chunk_count'], indexed=count,
                        matching_configuration=generation['config'] == service.config()))
            print(json.dumps(dict(status='degraded' if mismatches else 'ok', index=vector.collection_name,
                configuration=service.config(), **health, checked_generations=len(checked), coverage_mismatches=mismatches)))
            return
        if not args.learner_id:
            parser.error('rebuild requires an explicit learner-id; no unscoped corpus rebuild')
        owner = canonical_learner_id(args.learner_id)
        print(json.dumps(service.repository.queue_rebuild(owner, canonical_learner_id(args.run_id), service.config(), dry_run=not args.apply)))
    finally:
        service.close()
        service.files.close()
        vector.close()


if __name__ == '__main__':
    main()
