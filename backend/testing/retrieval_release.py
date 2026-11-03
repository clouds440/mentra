"""Packaged local canary and same-model rollback exercise; synthetic data only."""
import argparse
import io
import json
import hashlib
import os
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4
from types import SimpleNamespace
from fastapi import FastAPI
from fastapi.testclient import TestClient

from qdrant_client import QdrantClient
from sqlalchemy import update
from app.core.config import Settings
from app.learner.engine import LearnerEngine
from app.learner.schemas import ResolveLearningContextRequest
from app.rag.embedding_process import ProcessEmbeddingService
from app.rag.embeddings import EmbeddingModelError
from app.rag.qdrant_store import QdrantVectorStore
from app.rag.repositories.postgres import RAGRepository, now
from app.rag.repositories.tables import documents, generations, jobs
from app.rag.schemas import SearchRequest
from app.rag.service import RAGService
from app.rag.worker import IngestionWorker
from model_assets import verify_manifest
from testing.files import create_test_files
from testing.identities import learner_id, TEST_LEARNERS
from testing.postgres import PostgresSandbox


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--output',type=Path,required=True); args=parser.parse_args()
    if args.output.exists(): raise RuntimeError('Use a fresh report filename.')
    settings=Settings(_env_file=None,qdrant_url=os.environ['TEST_QDRANT_URL'],qdrant_api_key='test-only',
        qdrant_collection='mentra_canary_'+uuid4().hex,rag_reranker_path='/opt/mentra/models/reranker',
        rag_reranker_warm_on_startup=True)
    report={'packaged_source':str(Path(__import__('app').__file__).resolve()),'steps':[]}
    if os.environ.get('TEST_SOURCE_MANIFEST'):
        expected=json.loads(Path(os.environ['TEST_SOURCE_MANIFEST']).read_text())
        assert all(hashlib.sha256((Path('/app')/name).read_bytes()).hexdigest()==digest
            for name,digest in expected['files'].items())
        report['source_tree_sha256']=expected['tree_sha256']
        report['verified_source_files']=len(expected['files'])
    for role in ('embedding','reranker'):
        assert verify_manifest('/opt/mentra/models/'+role)
        report[role+'_manifest']=json.loads(Path('/opt/mentra/models/'+role+'/model-artifacts.json').read_text())
    engine=ProcessEmbeddingService(settings); client=QdrantClient(url=settings.qdrant_url)
    vector=QdrantVectorStore(settings,engine,client)
    try:
        with PostgresSandbox() as db:
            owner=learner_id(TEST_LEARNERS[0]); learner=LearnerEngine(db.repository)
            context=learner.resolve_learning_context(ResolveLearningContextRequest(learner_id=owner,name='Canary',activate=True))
            files=create_test_files(db.sessions,settings); repo=RAGRepository(db.sessions,files)
            service=RAGService(repo,learner,engine,vector,files,settings); worker=IngestionWorker(service)
            def upload(content,key,**kwargs):
                file=files.upload(owner,io.BytesIO(content.encode()),key+'.txt','library',key)
                return service.accept_upload(owner,file['id'],key,[context.context_id],key,**kwargs)
            first=upload('SQLSTATE 23505 means a unique constraint violation. Original evidence.','canary-original')
            worker.run_once(); assert repo.get_job(owner,first['job_id'])['state']=='SUCCEEDED'
            def search(): return service.search(owner,SearchRequest(query='Explain SQLSTATE 23505',document_ids=[first['document_id']],mode='SOURCE_SPECIFIC'))
            initial=search(); assert initial.chunks and initial.diagnostics.reranking=='ok'
            report['steps'].append('original ingestion and warmed retrieval passed')
            from app.api.routes.rag import router
            from app.core.exception_handlers import register_exception_handlers
            from app.student_profile.dependencies import require_onboarded_identity
            app=FastAPI(); app.state.rag_service=service
            register_exception_handlers(app); app.include_router(router,prefix='/api/v1')
            app.dependency_overrides[require_onboarded_identity]=lambda:SimpleNamespace(learner_id=owner)
            with TestClient(app) as http:
                response=http.post('/api/v1/rag/search',json=dict(query='Explain SQLSTATE 23505',
                    mode='SOURCE_SPECIFIC',document_ids=[first['document_id']]))
                assert response.status_code==200,response.text
                body=response.json(); assert body['pipeline_version']=='dense-lexical-rrf-v3'
                assert len(body['chunks'][0]['reranker_span'])==2
                chunk_url='/api/v1/rag/chunks/'+body['chunks'][0]['source']['chunk_id']
                assert http.get(chunk_url).status_code==200
                app.dependency_overrides[require_onboarded_identity]=lambda:SimpleNamespace(learner_id=learner_id(TEST_LEARNERS[1]))
                assert http.get(chunk_url).status_code==404
            report['steps'].append('HTTP result serialization, scored-window provenance and owner isolation passed with fixture identities')
            metadata=repo.get_document(owner,first['document_id'])
            replacement=upload('SQLSTATE 23505 means a duplicate unique key. Revised evidence.','canary-replacement',
                document_id=first['document_id'],expected_revision=metadata['revision'])
            with patch.object(engine,'embed_documents',side_effect=EmbeddingModelError('synthetic failure')):
                worker.run_once()
            assert search().chunks[0].source.generation_id==first['generation_id']
            report['steps'].append('failed replacement retained original active generation')
            with db.sessions.begin() as session:
                session.execute(update(jobs).where(jobs.c.id==replacement['job_id']).values(next_attempt_at=now()))
            worker.run_once(); assert search().chunks[0].source.generation_id==replacement['generation_id']
            assert service.get_chunk(owner,initial.chunks[0].source.chunk_id)['generation_id']==first['generation_id']
            report['steps'].append('replacement recovery and old canonical citation passed')
            # Same-model pointer rollback requires retained old points and canonical
            # generations. Production operators must stop conflicting workers first.
            with db.sessions.begin() as session:
                session.execute(update(generations).where(generations.c.id==first['generation_id']).values(state='READY'))
                session.execute(update(generations).where(generations.c.id==replacement['generation_id']).values(state='SUPERSEDED'))
                session.execute(update(documents).where(documents.c.id==first['document_id']).values(active_generation_id=first['generation_id'],revision=documents.c.revision+1))
            rolled=search(); assert rolled.chunks[0].source.generation_id==first['generation_id']
            assert 'Original evidence' in rolled.chunks[0].content
            report['steps'].append('same-model rollback restored original retrieval and invalidated candidate signature')
            report['identity']=dict(model=engine.model_name,revision=engine.model_version,dimension=engine.dimension)
            service.close(); files.close()
    finally:
        engine.close()
        if client.collection_exists(settings.qdrant_collection): client.delete_collection(settings.qdrant_collection)
        client.close()
    report['passed']=True
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'passed':True,'steps':report['steps']},indent=2))


if __name__=='__main__': main()
