"""Recovery drill for the explicitly named disposable launch-gate database only.

Archive/manifest files contain synthetic state and must be deleted with the
verification container. Never use these plaintext fixtures as production backups.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile
from urllib.parse import urlsplit
from uuid import uuid4

from sqlalchemy import select, text, update
from app.core.config import settings
from app.db.database import get_engine, get_session_factory
from app.files.provider import CloudinaryProvider
from app.files.tables import assets

ROOT = Path('/tmp/launchgate-recovery')


def fence():
    parsed = urlsplit(os.environ['DATABASE_URL'])
    if (parsed.hostname != 'mentra-launchgate-postgres'
            or parsed.path not in {'/mentra_launchgate', '/mentra_launchgate_restore'}
            or not (settings.app_env == 'launchgate20261025' or settings.app_env == 'production' and settings.files_environment == 'launchgate20261025')
            or settings.qdrant_collection != 'mentra_launchgate_20261025'
            or urlsplit(settings.qdrant_url).hostname != 'mentra-launchgate-qdrant'):
        raise RuntimeError('Recovery drill refuses any environment outside its disposable services')


def snapshot():
    with get_engine().connect() as connection:
        names = connection.scalars(text("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")).all()
        counts = {name: connection.scalar(text('SELECT count(*) FROM "' + name + '"')) for name in names}
        head = connection.scalar(text('SELECT version_num FROM alembic_version'))
        assert connection.scalar(text("SELECT count(*) FROM pg_constraint WHERE connamespace='public'::regnamespace AND NOT convalidated")) == 0
    return dict(head=head, table_counts=counts)


def main(operation):
    fence()
    ROOT.mkdir(exist_ok=True)
    provider = CloudinaryProvider(settings)
    try:
        if operation == 'archive':
            manifest = snapshot()
            rows = []
            with get_engine().connect() as connection:
                records = connection.execute(select(assets).where(assets.c.state == 'ACTIVE')).mappings().all()
            assert len(records) == 2
            for record in records:
                row = dict(record)
                with provider.stream(row) as response:
                    data = b''.join(response.iter_bytes(256*1024))
                assert hashlib.sha256(data).hexdigest() == row['sha256']
                (ROOT / row['id']).write_bytes(data)
                rows.append({key: value for key, value in row.items() if key in {'id','public_id','resource_type','environment','sha256','size_bytes'}})
            manifest['originals'] = rows
            (ROOT / 'manifest.json').write_text(json.dumps(manifest))
            print(json.dumps(dict(status='archived', tables=len(manifest['table_counts']), nonempty_tables=sum(bool(count) for count in manifest['table_counts'].values()), originals=len(rows), head=manifest['head'])))
        elif operation in {'validate', 'application'}:
            manifest = json.loads((ROOT / 'manifest.json').read_text())
            actual = snapshot()
            assert actual['head'] == manifest['head']
            if operation == 'validate':
                assert actual['table_counts'] == manifest['table_counts'], 'Restored row counts differ'
            for row in manifest['originals']:
                provider.verify(row)
            # PostgreSQL restores all validated FKs/checks; this checks live public
            # domain reads too, rather than treating pg_restore exit 0 as recovery.
            accounts = json.loads(Path('/tmp/launchgate-accounts.json').read_text())
            from app.auth.repositories.postgres import PostgresIdentityRepository
            from app.auth.service import AuthService
            from app.chat.repositories.postgres import ChatRepository
            auth, chat = AuthService(PostgresIdentityRepository(get_session_factory())), ChatRepository(get_session_factory())
            for account in accounts:
                identity = auth.authenticate(account['identity']['access_token'])
                assert identity.learner_id == account['identity']['learner_id']
                conversations = chat.recent(identity.learner_id, limit=100)['items']
                assert conversations
                assert all(item['learner_id'] == identity.learner_id for item in conversations)
                assert len(chat.history(identity.learner_id, conversations[0]['id'])['items']) >= 2
            print(json.dumps(dict(status='restored', tables=len(actual['table_counts']), head=actual['head'], identities=len(accounts), originals=2, constraints='all validated')))
        elif operation == 'queue-retry':
            from app.rag.repositories.postgres import RAGRepository
            accounts = json.loads(Path('/tmp/launchgate-accounts.json').read_text())
            repository = RAGRepository(get_session_factory())
            for account in accounts[:2]:
                with get_engine().connect() as connection:
                    config = connection.scalar(text('SELECT g.config FROM rag_generation g JOIN rag_document d ON d.active_generation_id=g.id WHERE d.id=:id'), dict(id=account['document']['document_id']))
                repository.queue_rebuild(account['identity']['learner_id'], str(uuid4()), config, dry_run=False)
            print(json.dumps(dict(status='synthetic-rebuilds-queued', jobs=2)))
        elif operation == 'namespace-promotion':
            manifest = json.loads((ROOT / 'manifest.json').read_text())
            row = manifest['originals'][0]
            from app.files.service import FilesService
            from app.core.exceptions import AppError
            # Real provider read, with production cookie/origin policy and a
            # deliberately preserved original storage suffix.
            promoted = settings.model_copy(update=dict(app_env='production', files_environment='launchgate20261025'))
            compatible = CloudinaryProvider(promoted)
            try:
                compatible.verify(row)
                with get_engine().connect() as connection:
                    owner = connection.scalar(select(assets.c.learner_id).where(assets.c.id == row['id']))
                FilesService(get_session_factory(), compatible, promoted).metadata(owner, row['id'])
            finally:
                compatible.close()
            incompatible = CloudinaryProvider(settings.model_copy(update=dict(app_env='production', files_environment='')))
            try:
                try:
                    incompatible._owned(row)
                except AppError as error:
                    assert error.code == 'FILES_NAMESPACE'
                else:
                    raise RuntimeError('Unexpected cross-namespace access')
            finally:
                incompatible.close()
            print(json.dumps(dict(status='production-namespace-preserved', original_checksum='matched', unconfigured_namespace='rejected')))
        elif operation == 'restore-original':
            manifest = json.loads((ROOT / 'manifest.json').read_text())
            row = manifest['originals'][0]
            data = (ROOT / row['id']).read_bytes()
            provider.destroy(row)  # Only the fenced, run-created synthetic original.
            with tempfile.TemporaryDirectory() as folder:
                source = Path(folder) / 'original.txt'
                source.write_bytes(data)
                receipt = provider.upload(source, row)
            provider.verify(row)
            with get_engine().begin() as connection:
                connection.execute(update(assets).where(assets.c.id == row['id']).values(asset_id=receipt['asset_id'], version=receipt['version']))
            print(json.dumps(dict(status='original-restored', checksum='sha256 matched', registry='provider receipt updated', scope='one synthetic asset; provider backup product not used')))
        elif operation == 'rebuild':
            from qdrant_client import QdrantClient
            from app.rag.embeddings import SentenceTransformerEmbeddingService
            from app.rag.qdrant_store import QdrantVectorStore
            from app.rag.factory import create_rag_service
            from app.learner.factory import create_learner_engine
            from app.rag.worker import IngestionWorker
            from app.rag.schemas import SearchRequest
            accounts = json.loads(Path('/tmp/launchgate-accounts.json').read_text())
            client = QdrantClient(url=settings.qdrant_url)
            # Isolated collection only: emulate complete loss of derived state.
            client.delete_collection(settings.qdrant_collection)
            embedding = SentenceTransformerEmbeddingService(settings)
            vector = QdrantVectorStore(settings, embedding)
            service = create_rag_service(create_learner_engine(), embedding, vector)
            try:
                vector.initialize_chunk_indexes()
                for account in accounts[:2]:
                    service.repository.queue_rebuild(account['identity']['learner_id'], str(uuid4()), service.config(), dry_run=False)
                worker = IngestionWorker(service)
                for _ in range(10):
                    if not worker.run_once():
                        break
                for account in accounts[:2]:
                    result = service.search(account['identity']['learner_id'], SearchRequest(query='What do decorators do?', mode='SOURCE_SPECIFIC', document_ids=[account['document']['document_id']]))
                    assert result.chunks
                health = service.repository.index_health()
                print(json.dumps(dict(status='vectors-rebuilt', documents=2, health=health), default=str))
            finally:
                service.close()
                service.files.close()
                vector.close()
                client.close()
        elif operation == 'cleanup-cloud':
            with get_engine().connect() as connection:
                rows = connection.execute(select(assets)).mappings().all()
            for row in rows:
                provider.destroy(dict(row))
            import cloudinary.api
            cloudinary.api.delete_folder(provider.namespace, **provider.options)
            print(json.dumps(dict(status='cloud-cleaned', synthetic_assets=len(rows))))
    finally:
        provider.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['archive','validate','application','namespace-promotion','restore-original','rebuild','queue-retry','cleanup-cloud'])
    main(parser.parse_args().operation)
