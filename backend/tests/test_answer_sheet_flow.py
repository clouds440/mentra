import os
import unittest
from io import BytesIO
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw
from pypdf import PdfReader
from reportlab.pdfgen import canvas

from app.assessments.schemas import StartAttempt, SubmitAnswers
from app.assessments.question_paper import render_question_paper
from app.core.config import settings
from app.core.exceptions import AppError
from app.documents.factory import create_document_reader
from testing.assessment_workers import run_assessment_pipeline
from tests import test_assessments as fixtures, test_chat_assessments as chat_fixtures


def sheet(kind):
    if kind == 'txt': return b'1. A\n2. B'
    buffer = BytesIO()
    if kind == 'pdf':
        page = canvas.Canvas(buffer); page.drawString(60, 780, '1. A'); page.drawString(60, 750, '2. B'); page.save()
    else:
        image = Image.new('RGB', (700, 400), 'white'); ImageDraw.Draw(image).text((30, 30), '1. A\n2. B', fill='black')
        image.save(buffer, 'PNG')
    return buffer.getvalue()


@unittest.skipUnless(os.environ.get('TEST_DATABASE_URL'), 'Requires dedicated PostgreSQL')
class AnswerSheetFlowTests(unittest.IsolatedAsyncioTestCase):
    setUp = fixtures.AssessmentTests.setUp
    conversation = chat_fixtures.ChatAssessmentTests.conversation
    answer_tool = chat_fixtures.ChatAssessmentTests.answer_tool

    async def generated(self):
        request = self.request.model_copy(update={'client_request_id':uuid4(), 'question_format':'mcq', 'count':2})
        return await self.service.generate(self.owner, request)

    async def finish(self, assessment, attempt, answers, confirmed=False):
        self.service.submit(self.owner, str(attempt.id), SubmitAnswers(expected_revision=attempt.revision,
            client_request_id=uuid4(), answers=answers, transcription_confirmed=confirmed))
        await run_assessment_pipeline(self.service)
        result = self.service.repository.attempt(self.owner, str(attempt.id))
        self.assertEqual(result.state, 'graded'); self.assertEqual(result.evidence_status, 'applied')
        return result

    async def test_all_formats_use_interactive_grading_and_owner_scoped_sources(self):
        assessment = await self.generated()
        questions = assessment.questions
        canonical = {str(questions[0].id):questions[0].options[0].id, str(questions[1].id):questions[1].options[1].id}
        typed = self.service.repository.start(self.owner, str(assessment.id), StartAttempt(client_request_id=uuid4()))
        baseline = await self.finish(assessment, typed, canonical)
        self.service.reader = create_document_reader(isolated=False)
        for kind in ('txt', 'pdf', 'png'):
            with self.subTest(kind=kind):
                attempt = self.service.repository.start(self.owner, str(assessment.id), StartAttempt(client_request_id=uuid4()))
                file = self.files.upload(self.owner, BytesIO(sheet(kind)), 'answers.'+kind, 'assessment', str(uuid4()))
                extraction = dict(answers={str(questions[0].id):'A', str(questions[1].id):'B'}, warnings=[], reader_revision='vision-test', handwriting_support='vision_requires_review')
                with patch.object(settings, 'assessment_vision_enabled', kind == 'png'), patch('app.vision.assessment_extractor.AssessmentAnswerExtractor.extract', new=AsyncMock(return_value=extraction)) as vision:
                    reviewed = await self.service.upload_paper_with_vision(self.owner, str(attempt.id), attempt.revision, file['id'])
                    if kind == 'png': vision.assert_awaited_once()
                    else: vision.assert_not_awaited()
                self.assertEqual(reviewed.extraction['answers'], canonical)
                with self.assertRaises(AppError):
                    self.service.submit(self.owner, str(attempt.id), SubmitAnswers(expected_revision=reviewed.revision, client_request_id=uuid4(), answers=canonical))
                result = await self.finish(assessment, reviewed, reviewed.extraction['answers'], True)
                self.assertEqual([grade.score for grade in result.grades], [grade.score for grade in baseline.grades])
                with self.assertRaises(AppError): self.files.read(self.other, file['id'])

    async def test_normal_chat_pdf_and_txt_attachments_prepare_the_same_attempt_pipeline(self):
        from app.chat.repositories.attachments import AttachmentRepository
        assessment = await self.generated()
        self.service.reader = create_document_reader(isolated=False)
        for kind in ('pdf', 'txt'):
            conversation = self.conversation()
            attachments = AttachmentRepository(self.db.sessions, self.files)
            asset = self.files.upload(self.owner, BytesIO(sheet(kind)), 'answers.'+kind, 'chat', str(uuid4()))
            attached = attachments.create(self.owner, 'answers.'+kind, self.files.metadata(self.owner, asset['id']))
            with self.db.sessions.begin() as session: attachments.bind(session, self.owner, [attached['id']], conversation)
            tool, _ = self.answer_tool(conversation, attachment_ids=[attached['id']])
            with patch.object(settings, 'assessment_vision_enabled', False):
                result = await tool.ainvoke(dict(assessment_id=str(assessment.id), attachment_id=attached['id']))
            attempt = self.service.repository.attempt(self.owner, result['attempt_id'])
            self.assertEqual(attempt.state, 'pending_transcription')
            await self.finish(assessment, attempt, attempt.extraction['answers'], True)

    async def test_incomplete_extraction_preserves_saved_draft_and_canonical_option_ids(self):
        from app.assessments.schemas import SaveDraftAnswers
        assessment = await self.generated()
        first, second = assessment.questions
        attempt = self.service.repository.start(self.owner, str(assessment.id), StartAttempt(client_request_id=uuid4()))
        saved = self.service.repository.save_draft_answers(self.owner, str(attempt.id), SaveDraftAnswers(
            expected_revision=attempt.revision, answers={str(first.id):first.options[0].id}))
        file = self.files.upload(self.owner, BytesIO(sheet('txt')), 'answers.txt', 'assessment', str(uuid4()))
        reviewed = self.service.repository.store_extraction(self.owner, str(attempt.id), saved.revision,
            dict(answers={str(first.id):'', str(second.id):'B'}, warnings=[]), file['id'], 'answers.txt')
        self.assertEqual(reviewed.extraction['answers'], {str(first.id):first.options[0].id,str(second.id):second.options[1].id})
        self.assertEqual(reviewed.answers, saved.answers)

    async def test_pdf_download_is_public_numbered_and_does_not_publish_a_draft(self):
        request = self.request.model_copy(update={'client_request_id':uuid4()})
        conversation = self.conversation()
        card = await self.service.generate_chat(self.owner, conversation, request)
        identifier = card['assessment']['id']
        public = self.service.chat.question_paper(self.owner, identifier)
        document = render_question_paper(public)
        text = '\n'.join(page.extract_text() for page in PdfReader(BytesIO(document)).pages)
        for expected in ('Question 1', 'Question 2', 'marks', 'Instructions', 'Upload a PDF'):
            self.assertIn(expected, text)
        self.assertNotIn('model_answer', text); self.assertNotIn('rubric', text)
        self.assertIsNone(self.service.chat.detail(self.owner, card['id'])['assessment_id'])
        with self.assertRaises(AppError): self.service.chat.question_paper(self.other, identifier)
        from app.api.routes.assessments import router
        from app.student_profile.dependencies import require_onboarded_identity
        app = FastAPI(); app.state.assessment_service = self.service
        app.dependency_overrides[require_onboarded_identity] = lambda: SimpleNamespace(learner_id=self.owner)
        app.add_exception_handler(AppError, lambda request, error: JSONResponse({'error':error.code}, status_code=error.status_code))
        app.include_router(router, prefix='/api/v1')
        with TestClient(app) as client:
            response = client.get(f'/api/v1/assessments/{identifier}/paper.pdf')
            self.assertEqual(response.status_code, 200); self.assertEqual(response.headers['content-type'], 'application/pdf')
            self.assertEqual(response.headers['cache-control'], 'no-store')
            self.assertTrue(response.content.startswith(b'%PDF')); self.assertIn('attachment;', response.headers['content-disposition'])
            app.dependency_overrides[require_onboarded_identity] = lambda: SimpleNamespace(learner_id=self.other)
            self.assertEqual(client.get(f'/api/v1/assessments/{identifier}/paper.pdf').status_code, 404)
