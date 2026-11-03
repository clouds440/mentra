"""Cross-image rollback rehearsal, constrained to one synthetic schema/collection."""
import argparse
import io
import json
import os
from pathlib import Path
import re
from uuid import uuid4

from alembic import command
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from qdrant_client import QdrantClient
from sqlalchemy.orm import sessionmaker
from sqlalchemy.schema import DropSchema
from app.core.config import Settings
from app.db.database import build_engine
from app.db.migrate import migration_config, upgrade
from app.db.urls import postgres_url
from app.learner.engine import LearnerEngine
from app.learner.repositories.postgres import PostgresLearnerRepository
from app.learner.schemas import ResolveLearningContextRequest
from app.rag.embedding_process import ProcessEmbeddingService
from app.rag.qdrant_store import QdrantVectorStore
from app.rag.repositories.postgres import RAGRepository
from app.rag.schemas import SearchRequest
from app.rag.service import RAGService
from app.rag.worker import IngestionWorker
from testing.files import create_test_files
from testing.identities import TEST_LEARNERS, learner_id
from testing.postgres import PostgresSandbox


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--phase',choices=('prepare','old','new','cleanup'),required=True)
    parser.add_argument('--report',type=Path,required=True); args=parser.parse_args()
    if args.phase=='prepare':
        if args.report.exists(): raise RuntimeError('Use a fresh rehearsal report.')
        sandbox=PostgresSandbox()
        report=dict(schema=sandbox.schema,collection='mentra_rollback_'+uuid4().hex,steps=[])
        engine=sandbox.engine; sessions=sandbox.sessions
    else:
        report=json.loads(args.report.read_text())
        if not re.fullmatch(r'mentra_test_[0-9a-f]{32}',report['schema']) or not re.fullmatch(r'mentra_rollback_[0-9a-f]{32}',report['collection']):
            raise RuntimeError('Refusing an unrecognized rollback target.')
        url=postgres_url(os.environ['TEST_DATABASE_URL']).update_query_dict({'options':'-csearch_path='+report['schema']})
        engine=build_engine(url.render_as_string(hide_password=False)); sessions=sessionmaker(engine,expire_on_commit=False)
    client=QdrantClient(url=os.environ['TEST_QDRANT_URL'])
    if args.phase=='cleanup':
        if not report.get('old_passed') or not report.get('new_passed'): raise RuntimeError('Rehearsal not complete.')
        if client.collection_exists(report['collection']): client.delete_collection(report['collection'])
        with engine.begin() as connection: connection.execute(DropSchema(report['schema'],cascade=True))
        report['cleaned_up']=True; args.report.write_text(json.dumps(report,indent=2)+'\n')
        client.close(); engine.dispose(); print('Synthetic rollback targets removed.'); return
    if args.phase=='new': upgrade(engine)
    settings=Settings(_env_file=None,qdrant_url=os.environ['TEST_QDRANT_URL'],qdrant_api_key='test-only',
        qdrant_collection=report['collection'],rag_reranker_path='')
    embedding=ProcessEmbeddingService(settings)
    vector=QdrantVectorStore(settings,embedding,client)
    learner=LearnerEngine(PostgresLearnerRepository(sessions)); files=create_test_files(sessions,settings)
    service=RAGService(RAGRepository(sessions,files),learner,embedding,vector,files,settings)
    try:
        if args.phase=='prepare':
            report['owner']=learner_id(TEST_LEARNERS[0])
            context=learner.resolve_learning_context(ResolveLearningContextRequest(learner_id=report['owner'],name='Artifact rollback',activate=True))
            data=b'SQLSTATE 23505 indicates a unique constraint violation. Retained rollback evidence.'
            file=files.upload(report['owner'],io.BytesIO(data),'rollback.txt','library','rollback')
            accepted=service.accept_upload(report['owner'],file['id'],'Rollback',[context.context_id],'rollback')
            IngestionWorker(service).run_once()
            assert service.repository.get_job(report['owner'],accepted['job_id'])['state']=='SUCCEEDED'
            report['document_id']=accepted['document_id']; report['generation_id']=accepted['generation_id']
        result=service.search(report['owner'],SearchRequest(query='Explain SQLSTATE 23505',mode='SOURCE_SPECIFIC',document_ids=[report['document_id']]))
        assert result.chunks and result.chunks[0].source.generation_id==report['generation_id']
        assert 'Retained rollback evidence' in result.chunks[0].content
        with engine.connect() as connection:
            revision=MigrationContext.configure(connection).get_current_revision()
        head=ScriptDirectory.from_config(migration_config()).get_current_head()
        assert revision==head,(revision,head)
        if args.phase=='prepare':
            report['new_head']=head
            with engine.connect() as connection:
                command.downgrade(migration_config(connection),'20261029_0038'); connection.commit()
            report['steps'].append('New artifact ingested canonical source; downgraded only derived lexical index.')
        else:
            report[args.phase+'_passed']=True
            report['steps'].append(dict(phase=args.phase,head=head,pipeline=result.pipeline_version,
                generation_unchanged=True,model=embedding.model_name,revision=embedding.model_version))
        args.report.write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(report,indent=2))
    finally:
        service.close(); files.close(); embedding.close(); client.close(); engine.dispose()
    # The schema/collection intentionally survive until the explicit cleanup phase.


if __name__=='__main__': main()
