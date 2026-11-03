"""Offline real OCR/E5 source-publication check in a disposable test schema."""
import io
import json
from PIL import Image, ImageDraw, ImageFont
from pypdf import PdfReader
from qdrant_client import QdrantClient
from app.core.config import Settings
from app.learner.engine import LearnerEngine
from app.learner.schemas import ResolveLearningContextRequest
from app.rag.embeddings import SentenceTransformerEmbeddingService
from app.rag.qdrant_store import QdrantVectorStore
from app.rag.repositories.postgres import RAGRepository
from app.rag.schemas import SearchRequest
from app.rag.service import RAGService
from app.rag.worker import IngestionWorker
from testing.files import create_test_files
from testing.identities import learner_id
from testing.postgres import PostgresSandbox


def main():
    config=Settings(embedding_device='cpu',local_inference_device='cpu',qdrant_url='http://test',
        qdrant_api_key='test',qdrant_collection='scanned_pdf',rag_hybrid_enabled=False,rag_reranker_path='')
    embedding=SentenceTransformerEmbeddingService(config)
    image=Image.new('RGB',(1600,320),'white')
    ImageDraw.Draw(image).text((35,85),'Saturn is a planet with bright rings.',font=ImageFont.load_default(size=40),fill='black')
    output=io.BytesIO(); image.save(output,'PDF',resolution=150); data=output.getvalue()
    native_chars=len(PdfReader(io.BytesIO(data)).pages[0].extract_text().strip())
    assert native_chars==0
    with PostgresSandbox() as db:
        owner=learner_id('alice'); learner=LearnerEngine(db.repository)
        context=learner.resolve_learning_context(ResolveLearningContextRequest(learner_id=owner,name='Astronomy',activate=True))
        files=create_test_files(db.sessions,config)
        vector=QdrantVectorStore(config,embedding,QdrantClient(':memory:'))
        service=RAGService(RAGRepository(db.sessions,files),learner,embedding,vector,files,config)
        try:
            stored=files.upload(owner,io.BytesIO(data),'scan.pdf','library','scan-e5')
            accepted=service.accept_upload(owner,stored['id'],'Scanned astronomy',[context.context_id],'scan-e5')
            IngestionWorker(service).run_once()
            job=service.repository.get_job(owner,accepted['job_id'])
            assert job['state']=='SUCCEEDED',job['error']
            version=service.repository.list_versions(owner,accepted['document_id'])['items'][0]
            passages=service.source_chunks(owner,accepted['document_id'],version['id'])
            assert passages and all(span['method']=='ocr' for row in passages for span in row['spans'])
            assert 'saturn' in ' '.join(row['content'] for row in passages).casefold()
            indexed=vector.count_chunks(owner,version['generation_id']); assert indexed==len(passages)
            result=service.search(owner,SearchRequest(query='Which planet has bright rings?',document_ids=[accepted['document_id']]))
            assert result.chunks and result.chunks[0].source.document_id==accepted['document_id']
            assert result.chunks[0].source.warnings and files.read(owner,stored['id'])==data
            print(json.dumps(dict(native_characters=native_chars,job_state=job['state'],
                extraction_state=version['extraction_state'],saved_passages=len(passages),indexed_vectors=indexed,
                embedding_model=embedding.model_name,embedding_revision=embedding.model_version,
                embedding_dimension=embedding.dimension,vector_backend='Qdrant local',retrieval='dense only',
                returned_sources=len(result.chunks),ocr_provenance=True,warnings_preserved=True,
                original_bytes_preserved=True,hosted_model_calls=0),indent=2))
        finally:
            service.close(); vector.close(); files.close()


if __name__=='__main__': main()
