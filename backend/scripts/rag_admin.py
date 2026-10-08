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
    parser.add_argument('operation', choices=['health', 'rebuild'])
    parser.add_argument('--learner-id')
    parser.add_argument('--apply', action='store_true', help='Queue rebuild jobs; without this flag only report counts.')
    parser.add_argument('--run-id', default=str(uuid4()), help='Reuse this UUID to make an operator rebuild idempotent.')
    args = parser.parse_args()
    init_db()
    embedding = SentenceTransformerEmbeddingService(settings)
    vector = QdrantVectorStore(settings, embedding)
    service = create_rag_service(create_learner_engine(), embedding, vector)
    try:
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
        vector.close()


if __name__ == '__main__':
    main()
