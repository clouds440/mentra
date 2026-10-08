"""Real baked embedding, server Qdrant, local OCR and isolated PostgreSQL smoke/evaluation.

Run inside the backend verification image with TEST_DATABASE_URL and
TEST_QDRANT_URL set to dedicated test services. Never uses application DATABASE_URL.
"""
import io
import json
import os
import tempfile
import time
import statistics
from pathlib import Path
from uuid import uuid4
from qdrant_client import QdrantClient
from app.core.config import Settings
from app.learner.engine import LearnerEngine
from app.learner.schemas import ResolveLearningContextRequest
from app.rag.embeddings import SentenceTransformerEmbeddingService
from app.rag.qdrant_store import QdrantVectorStore
from app.rag.repositories.postgres import RAGRepository
from app.rag.service import RAGService
from app.rag.storage import FileStorage
from app.rag.worker import IngestionWorker
from app.rag.schemas import SearchRequest
from app.rag.evaluation import evaluate
from testing.postgres import PostgresSandbox
from testing.identities import learner_id, TEST_LEARNERS


def build_pdf(text):
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, NameObject, DictionaryObject
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')})
    page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): writer._add_object(font)})})
    stream = DecodedStreamObject(); stream.set_data(f'BT /F1 16 Tf 40 700 Td ({text}) Tj ET'.encode('ascii'))
    page[NameObject('/Contents')] = writer._add_object(stream)
    output = io.BytesIO(); writer.write(output); return output.getvalue()


def formats():
    from docx import Document
    from pptx import Presentation
    from PIL import Image, ImageDraw, ImageFont
    doc = Document(); doc.add_heading('Python decorators', level=1); doc.add_paragraph('Python decorators wrap functions to add reusable behavior.')
    doc_buffer = io.BytesIO(); doc.save(doc_buffer)
    presentation = Presentation(); slide = presentation.slides.add_slide(presentation.slide_layouts[1]); slide.shapes.title.text = 'Python decorators'; slide.placeholders[1].text = 'Python decorators wrap functions to add reusable behavior.'
    slides = io.BytesIO(); presentation.save(slides)
    image = Image.new('RGB', (1600, 400), 'white'); draw = ImageDraw.Draw(image)
    font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 36)
    draw.text((30, 100), 'Python decorators wrap functions.', font=font, fill='black')
    png = io.BytesIO(); image.save(png, 'PNG')
    scanned = io.BytesIO(); image.save(scanned, 'PDF', resolution=150)
    jpeg = io.BytesIO(); image.save(jpeg, 'JPEG')
    from pypdf import PdfReader, PdfWriter
    mixed = PdfReader(io.BytesIO(build_pdf('This page contains Python decorator study notes and an image.'))).pages[0]
    mixed.merge_page(PdfReader(io.BytesIO(scanned.getvalue())).pages[0])
    writer = PdfWriter(); writer.add_page(mixed); mixed_buffer = io.BytesIO(); writer.write(mixed_buffer)
    return [('txt', b'Python decorators wrap functions to add reusable behavior.'), ('pdf', build_pdf('Python decorators wrap functions to add reusable behavior.')),
            ('docx', doc_buffer.getvalue()), ('pptx', slides.getvalue()), ('png', png.getvalue()), ('jpg', jpeg.getvalue()),
            ('pdf', scanned.getvalue()), ('pdf', mixed_buffer.getvalue())]


def main():
    import resource
    url = os.environ['TEST_QDRANT_URL']
    collection = 'mentra_test_' + uuid4().hex
    settings = Settings(qdrant_url=url, qdrant_api_key='test-only', qdrant_collection=collection)
    embedding = SentenceTransformerEmbeddingService(settings)
    client = QdrantClient(url=url)
    vector = QdrantVectorStore(settings, embedding, client)
    report = dict(embedding=dict(model=embedding.model_name, revision=embedding.model_version, dimension=embedding.dimension), formats=[])
    with PostgresSandbox() as database, tempfile.TemporaryDirectory() as folder:
        learner = LearnerEngine(database.repository)
        owner = learner_id(TEST_LEARNERS[0])
        context = learner.resolve_learning_context(ResolveLearningContextRequest(learner_id=owner, name='Python', activate=True))
        service = RAGService(RAGRepository(database.sessions), learner, embedding, vector, FileStorage(folder), settings)
        worker = IngestionWorker(service)
        report['parser_revision'] = service.parser.version
        reranker = service.reranker
        if reranker:
            report['reranker'] = json.loads((reranker.path / 'model-metadata.json').read_text())
        service.reranker = None
        try:
            for number, (suffix, data) in enumerate(formats()):
                started = time.monotonic()
                accepted = service.accept_upload(owner, io.BytesIO(data), f'fixture-{number}.{suffix}', f'Fixture {number}', [context.context_id], str(uuid4()))
                worker.run_once()
                job = service.repository.get_job(owner, accepted['job_id'])
                if job['state'] != 'SUCCEEDED':
                    raise RuntimeError(f'{suffix} failed: {job["error"]}')
                result = service.search(owner, SearchRequest(query='What do Python decorators do?', mode='SOURCE_SPECIFIC', document_ids=[accepted['document_id']]))
                assert result.chunks and 'decorator' in result.chunks[0].content.lower()
                record = dict(format=suffix, source=number, chunks=len(result.chunks), methods=[s.method for c in result.chunks for s in c.source.spans], elapsed_ms=round((time.monotonic()-started)*1000, 2))
                if suffix in ('png', 'jpg') or number == 6:
                    expected = 'python decorators wrap functions.'
                    actual = ' '.join(c.content for c in result.chunks).strip().lower()
                    assert actual == expected, (suffix, actual)
                    record['printed_text_character_error_rate'] = 0.0
                if number == 7:
                    assert 'image_ocr' in record['methods'], record
                report['formats'].append(record)
            # Fixed compact corpus with near distractors. Compare using real model,
            # identical source judgments and retrieval budgets.
            corpus = [
                ('python-decorators', 'Python decorators wrap functions to add behavior. A decorator can wrap a function to log calls.'),
                ('python-dictionaries', 'A Python dictionary maps unique keys to values. It provides fast key-based lookup.'),
                ('database-errors', 'SQLSTATE 23505 indicates a unique constraint violation in PostgreSQL.'),
                ('database-tables', 'A database table stores rows with named columns. A primary key uniquely identifies each row.'),
            ]
            ids = {}
            for label, text in corpus:
                accepted = service.accept_upload(owner, io.BytesIO(text.encode()), label + '.txt', label, [context.context_id], label)
                worker.run_once(); ids[label] = accepted['document_id']
            items = json.loads((Path(__file__).with_name('rag_corpus.json')).read_text())
            for label, hybrid, ranker in [('dense',False,None), ('hybrid',True,None)] + ([('reranked',True,reranker)] if reranker else []):
                service.settings = settings.model_copy(update={'rag_hybrid_enabled':hybrid})
                service.reranker = ranker
                timings = []; reranking_states = []
                def search(item):
                    if item['context'] == 'Python':
                        selected = [ids['python-decorators'], ids['python-dictionaries']]
                    elif item['context'] == 'Databases':
                        selected = [ids['database-errors'], ids['database-tables']]
                    else:
                        selected = list(ids.values())
                    result = service.search(owner, SearchRequest(query=item['query'], mode='SOURCE_SPECIFIC', document_ids=selected, limit=3))
                    timings.append(result.diagnostics.timings_ms['total'])
                    reranking_states.append(result.diagnostics.reranking)
                    reverse = {value:key for key, value in ids.items()}
                    return [reverse[c.source.document_id] for c in result.chunks]
                report[label] = evaluate(items, search, k=3)
                report[label]['latency_ms'] = dict(p50=statistics.median(timings), p95=sorted(timings)[-1], samples=len(timings), includes_cold_start=True)
                report[label]['reranking_states'] = reranking_states
                if ranker:
                    assert all(state == 'ok' for state in reranking_states), reranking_states
            service.repository.request_delete(owner, next(iter(ids.values())))
            worker.run_once()
            report['peak_process_rss_mib'] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
            print(json.dumps(report, indent=2))
        finally:
            service.reranker = reranker
            service.close()
            if client.collection_exists(collection):
                client.delete_collection(collection)
            client.close()


if __name__ == '__main__':
    main()
