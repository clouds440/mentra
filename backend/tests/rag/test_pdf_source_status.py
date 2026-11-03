"""Source visibility and scanned-PDF ingestion, without hosted model calls."""
import io
import os
import unittest
from unittest.mock import patch
from app.rag.errors import ExtractionError
from tests.rag import test_workflows as workflow_fixtures


@unittest.skipUnless(os.environ.get('TEST_DATABASE_URL'), 'Requires disposable PostgreSQL')
class PDFSourceStatusTests(unittest.TestCase):
    setUp = workflow_fixtures.WorkflowTests.setUp
    upload = workflow_fixtures.WorkflowTests.upload
    ready = workflow_fixtures.WorkflowTests.ready
    search = workflow_fixtures.WorkflowTests.search

    def version(self, document):
        return self.repo.list_versions(self.owner,document)['items'][0]

    def test_pending_version_reports_processing(self):
        accepted=self.upload()
        version=self.version(accepted['document_id'])
        self.assertEqual(version.get('extraction_state'),'processing')
        self.assertIsNone(version['generation_id'])

    def test_ocr_failure_reports_error_on_unpublished_version(self):
        accepted=self.upload()
        with patch.object(self.service.parser,'parse',side_effect=ExtractionError('This PDF needs OCR. The server OCR tools are unavailable.')):
            self.worker.run_once()
        version=self.version(accepted['document_id'])
        self.assertEqual(version.get('extraction_state'),'failed')
        self.assertIn('OCR tools are unavailable',version['extraction_error'])
        self.assertEqual(self.repo.get_document(self.owner,accepted['document_id'])['versions'][0]['extraction_state'],'failed')
        self.assertIsNone(self.repo.get_document(self.owner,accepted['document_id'])['active_generation_id'])

    def test_image_only_pdf_is_ocr_read_persisted_and_retrievable(self):
        from PIL import Image,ImageDraw,ImageFont
        from pypdf import PdfReader
        image=Image.new('RGB',(1600,320),'white')
        ImageDraw.Draw(image).text((35,85),'Python decorators wrap functions to add reusable behavior.',font=ImageFont.load_default(size=36),fill='black')
        output=io.BytesIO(); image.save(output,'PDF',resolution=150)
        data=output.getvalue()
        self.assertFalse(PdfReader(io.BytesIO(data)).pages[0].extract_text().strip())
        stored=self.files.upload(self.owner,io.BytesIO(data),'scanned.pdf','library','scanned-source')
        accepted=self.service.accept_upload(self.owner,stored['id'],'Scanned PDF',[self.context.context_id],'scanned-source')
        self.assertTrue(self.worker.run_once())
        job=self.repo.get_job(self.owner,accepted['job_id'])
        self.assertEqual(job['state'],'SUCCEEDED',job['error'])
        version=self.version(accepted['document_id'])
        passages=self.service.source_chunks(self.owner,accepted['document_id'],version['id'])
        self.assertTrue(passages)
        self.assertIn('decorators',' '.join(p['content'] for p in passages).lower())
        self.assertTrue(all(span['method']=='ocr' for p in passages for span in p['spans']))
        self.assertTrue(any('OCR' in warning for warning in version['warnings']))
        result=self.search(document_ids=[accepted['document_id']])
        self.assertTrue(result.chunks)
        self.assertEqual(result.chunks[0].source.document_id,accepted['document_id'])
        self.assertEqual(self.files.read(self.owner,stored['id']),data)

    def test_blank_pdf_is_failed_not_empty_ready(self):
        from pypdf import PdfWriter
        writer=PdfWriter(); writer.add_blank_page(width=612,height=792)
        output=io.BytesIO(); writer.write(output)
        stored=self.files.upload(self.owner,io.BytesIO(output.getvalue()),'blank.pdf','library','blank-source')
        accepted=self.service.accept_upload(self.owner,stored['id'],'Blank PDF',[self.context.context_id],'blank-source')
        self.worker.run_once()
        job=self.repo.get_job(self.owner,accepted['job_id'])
        self.assertEqual(job['state'],'FAILED')
        self.assertIn('No usable text',job['error'])
        self.assertIsNone(self.repo.get_document(self.owner,accepted['document_id'])['active_generation_id'])

    def test_failed_reindex_keeps_published_passages_and_exposes_latest_error(self):
        from uuid import uuid4
        from app.rag.schemas import RevisionRequest
        accepted=self.ready()
        document=self.repo.get_document(self.owner,accepted['document_id'])
        original=self.version(accepted['document_id'])['generation_id']
        self.repo.reindex(self.owner,document['id'],RevisionRequest(expected_revision=document['revision'],idempotency_key=str(uuid4())),self.service.config())
        with patch.object(self.service.parser,'parse',side_effect=ExtractionError('OCR needs repair.')):
            self.worker.run_once()
        version=self.version(document['id'])
        self.assertEqual(version['generation_id'],original)
        self.assertEqual(version['extraction_state'],'ready')
        self.assertEqual(version['extraction_error'],'OCR needs repair.')
        self.assertTrue(self.service.source_chunks(self.owner,document['id'],version['id'],generation_id=original))

    def test_older_failed_version_retains_its_own_status_and_error(self):
        accepted=self.upload()
        with patch.object(self.service.parser,'parse',side_effect=ExtractionError('First source needs OCR.')):
            self.worker.run_once()
        document=self.repo.get_document(self.owner,accepted['document_id'])
        first=self.version(document['id'])['id']
        self.upload(b'Updated source',key='replacement-status',document_id=document['id'],expected_revision=document['revision'])
        with patch.object(self.service.parser,'parse',side_effect=ExtractionError('Second source needs OCR.')):
            self.worker.run_once()
        versions=self.repo.list_versions(self.owner,document['id'])['items']
        self.assertEqual(len(versions),2)
        original=next(version for version in versions if version['id']==first)
        self.assertEqual(original['extraction_state'],'failed')
        self.assertEqual(original['extraction_error'],'First source needs OCR.')
        from app.core.exceptions import AppError
        with self.assertRaises(AppError): self.repo.list_versions(self.other,document['id'])
