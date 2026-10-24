"""Exercise populated storage migration refusal in unique disposable schemas."""
import io
import json
import os
from urllib.parse import urlsplit
from uuid import uuid4
from alembic import command
from sqlalchemy import text
from app.db.migrate import migration_config, upgrade
from testing.postgres import PostgresSandbox
from testing.files import create_test_files
from testing.identities import learner_id, TEST_LEARNERS


def revision(database, target):
    with database.engine.connect() as connection:
        command.downgrade(migration_config(connection), target)
        connection.commit()


def main():
    parsed = urlsplit(os.environ['TEST_DATABASE_URL'])
    if parsed.hostname != 'mentra-launchgate-postgres' or parsed.path != '/mentra_launchgate':
        raise RuntimeError('Migration drill requires the disposable launch-gate database')
    with PostgresSandbox() as database:
        owner = learner_id(TEST_LEARNERS[0])
        revision(database, '20261017_0027')
        document, version = str(uuid4()), str(uuid4())
        with database.engine.begin() as connection:
            connection.execute(text("INSERT INTO rag_document(id,learner_id,title,filename,context_ids,archived,revision,created_at,updated_at) VALUES (:document,:owner,'Synthetic','fixture.txt','[\"synthetic\"]',false,1,now(),now())"), dict(document=document,owner=owner))
            connection.execute(text("INSERT INTO rag_document_version(id,learner_id,document_id,file_hash,media_type,size_bytes,filename,created_at,storage_key) VALUES (:version,:owner,:document,'synthetic','text/plain',1,'fixture.txt',now(),'synthetic-only-original')"), dict(version=version,document=document,owner=owner))
        try:
            upgrade(database.engine)
        except RuntimeError as error:
            assert 'Legacy file data exists' in str(error)
        else:
            raise RuntimeError('Populated legacy originals were not protected')
        with database.engine.connect() as connection:
            assert connection.scalar(text('SELECT storage_key FROM rag_document_version')) == 'synthetic-only-original'
            assert connection.scalar(text('SELECT version_num FROM alembic_version')) == '20261017_0027'
    with PostgresSandbox() as database:
        files = create_test_files(database.sessions)
        uploaded = files.upload(learner_id(TEST_LEARNERS[0]), io.BytesIO(b'Synthetic original'), 'fixture.txt', 'library', str(uuid4()))
        revision(database, '20261020_0028')
        try:
            revision(database, '20261017_0027')
        except RuntimeError as error:
            assert 'Original bytes cannot be reconstructed' in str(error)
        else:
            raise RuntimeError('Populated registry downgrade was not protected')
        with database.engine.connect() as connection:
            assert str(connection.scalar(text('SELECT id FROM file_asset'))) == uploaded['id']
            assert connection.scalar(text('SELECT version_num FROM alembic_version')) == '20261020_0028'
        files.close()
    print(json.dumps(dict(legacy_upgrade='refused; provenance preserved', populated_downgrade='refused; registry preserved', schemas='removed')))


if __name__ == '__main__':
    main()
