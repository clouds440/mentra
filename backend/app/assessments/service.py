from pathlib import Path
from tempfile import TemporaryDirectory
from starlette.concurrency import run_in_threadpool
from app.core.exceptions import AppError
from app.documents.factory import create_document_reader
from app.documents.errors import DocumentReadError
from app.langchain.graphs.event_confirmation import EventConfirmationGraph


from app.core.logging import workflow_logger

@workflow_logger.connect_module(default_outcome='success', policies={
    'submit': {'request_outcome': True, 'result': lambda value: dict(domain_status=value.state),
               'outcome': lambda value: 'deferred' if value.state in ('submitted','grading') else 'success'},
})
class AssessmentService:
    def __init__(self, repository, workflows, reader=None):
        self.repository, self.workflows = repository, workflows
        self.reader = reader or create_document_reader(isolated=True)
        self.paper_graph = EventConfirmationGraph(repository.sessions.kw['bind'], 'assessment-transcription-v1')
        from .chat import ChatAssessments
        self.chat = ChatAssessments(repository)

    async def generate_chat(self, owner, conversation, request):
        previous = await run_in_threadpool(self.chat.replay, owner, conversation, request)
        if previous: return previous
        claim = await run_in_threadpool(self.repository.claim_generation, owner, request)
        try:
            previous = await run_in_threadpool(self.chat.replay, owner, conversation, request)
            if previous: return previous
            revision = await self._revision_source(owner, request, conversation)
            import asyncio
            from app.langchain.workflow_budget import model_budget
            with model_budget():
                generated, sources = await asyncio.wait_for(self.workflows.generate(owner, request, revision=revision), 150)
            return await run_in_threadpool(self.chat.save, owner, conversation, request, generated, sources, claim)
        finally:
            try: await run_in_threadpool(self.repository.release_generation, owner, request.client_request_id, claim)
            except Exception: workflow_logger.event('assessment.generation_cleanup_deferred', code='CLAIM_CLEANUP_UNAVAILABLE')

    async def generate(self, owner, request):
        previous = await run_in_threadpool(self.repository.replay, owner, request)
        if previous: return previous
        claim = await run_in_threadpool(self.repository.claim_generation, owner, request)
        try:
            # Recheck after acquiring the claim: another request may have saved
            # between the first replay check and claim acquisition.
            previous = await run_in_threadpool(self.repository.replay, owner, request)
            if previous: return previous
            revision = await self._revision_source(owner, request)
            import asyncio
            from app.langchain.workflow_budget import model_budget
            with model_budget():
                generated, sources = await asyncio.wait_for(self.workflows.generate(owner, request, revision=revision), 150)
            return await run_in_threadpool(self.repository.save, owner, request, generated, sources, claim)
        finally:
            try:
                await run_in_threadpool(self.repository.release_generation, owner, request.client_request_id, claim)
            except Exception:
                # The claim expires. Cleanup must not replace an already saved
                # assessment or the original provider/domain error.
                workflow_logger.event('assessment.generation_cleanup_deferred', code='CLAIM_CLEANUP_UNAVAILABLE')

    async def _revision_source(self, owner, request, conversation=None):
        source = None
        if request.revision_draft_id:
            if not conversation:
                raise AppError('ASSESSMENT_TARGET_REQUIRED', 'Chat drafts can only be revised in their conversation.', 422)
            card = await run_in_threadpool(self.chat.detail, owner, str(request.revision_draft_id))
            if card['conversation_id'] != conversation:
                raise AppError('ASSESSMENT_DRAFT_NOT_FOUND', 'This assessment is not in the current chat.', 404)
            source = card['assessment']
        elif request.revision_assessment_id:
            value = await run_in_threadpool(self.repository.detail, owner, str(request.revision_assessment_id))
            source = value.model_dump(mode='json')
        if source and source['context_id'] != request.context_id:
            raise AppError('ASSESSMENT_CONTEXT_MISMATCH', 'Revise within the original learning context.', 422)
        return source

    def submit(self, owner, identifier, body):
        attempt = self.repository.attempt(owner, identifier)
        if attempt.state == 'pending_transcription':
            if not body.transcription_confirmed:
                raise AppError('TRANSCRIPTION_CONFIRMATION_REQUIRED', 'Review and explicitly confirm all extracted answers before grading.', 422)
            self.paper_graph.decide(owner, identifier, 'confirmed')
        return self.repository.submit(owner, identifier, body)

    def upload_paper(self, owner, identifier, expected_revision, source, filename, *, store=True):
        filename = Path((filename or 'answers').replace('\\', '/')).name[:200]
        attempt = self.repository.attempt(owner, identifier)
        assessment = self.repository.detail(owner, str(attempt.assessment_id))
        data = source.read(25*1024*1024+1)
        if not data or len(data)>25*1024*1024: raise AppError('ASSESSMENT_UPLOAD_SIZE', 'Upload a nonempty answer sheet of at most 25 MiB.', 413)
        with TemporaryDirectory(prefix='mentra-assessment-') as directory:
            path = Path(directory)/'source'
            path.write_bytes(data)
            try: document = self.reader.read(path, filename=filename)
            except DocumentReadError as error: raise AppError('ASSESSMENT_UNREADABLE', str(error), 422) from None
        # Numbered segmentation is a suggestion only. Unknown handwriting/mapping
        # confidence always requires a complete reviewed answer map on submission.
        import re
        text = document.text[:80000]
        matches = list(re.finditer(r'(?m)^\s*(?:Q(?:uestion)?\s*)?(\d{1,2})[.):\s]+', text))
        answers = {}
        for index, question in enumerate(assessment.questions, 1):
            match = next((item for item in matches if int(item.group(1)) == index), None)
            if match:
                position = matches.index(match)
                end = matches[position+1].start() if position+1<len(matches) else len(text)
                answers[str(question.id)] = text[match.end():end].strip()[:8000]
            else: answers[str(question.id)] = text[:8000] if len(assessment.questions)==1 else ''
        extracted = dict(answers=answers, text=text, blocks=document.blocks[:200], warnings=document.warnings,
            reader_revision=document.reader_revision, extraction_confidence=None, mapping_confidence=None,
            requires_confirmation=True, handwriting_support='unverified', truncated=len(document.text)>80000)
        if not store:
            return extracted, data, filename
        return self.repository.store_extraction(owner, identifier, expected_revision, extracted, data, filename)

    async def upload_paper_with_vision(self, owner, identifier, expected_revision, source, filename):
        from io import BytesIO
        from app.core.config import settings
        data = await run_in_threadpool(source.read, 25*1024*1024+1)
        if not data or len(data)>25*1024*1024:
            raise AppError('ASSESSMENT_UPLOAD_SIZE', 'Upload a nonempty answer sheet of at most 25 MiB.', 413)
        attempt = await run_in_threadpool(self.repository.attempt, owner, identifier)
        if attempt.revision != expected_revision or attempt.state not in ('draft','pending_transcription'):
            raise AppError('REVISION_CONFLICT', 'This attempt changed. Reload before uploading.', 409)
        safe_filename = Path((filename or 'answers').replace('\\','/')).name[:200]
        is_image = data.startswith((b'%PDF', b'\xff\xd8\xff', b'\x89PNG\r\n\x1a\n'))
        vision_failed = False
        if settings.assessment_vision_enabled and is_image:
            from app.vision.assessment_extractor import AssessmentAnswerExtractor
            assessment = await run_in_threadpool(self.repository.detail, owner, str(attempt.assessment_id))
            try:
                extracted = await AssessmentAnswerExtractor(self.workflows.llm).extract(data, assessment.questions)
            except Exception:
                vision_failed = True
                workflow_logger.event('assessment.vision_fallback', code='VISION_UNAVAILABLE')
            else:
                return await run_in_threadpool(self.repository.store_extraction, owner, identifier,
                    expected_revision, extracted, data, safe_filename)
        try:
            extracted, _, safe_filename = await run_in_threadpool(self.upload_paper, owner, identifier,
                expected_revision, BytesIO(data), filename, store=False)
        except AppError as error:
            if error.code != 'ASSESSMENT_UNREADABLE': raise
            safe_filename = Path((filename or 'answers').replace('\\','/')).name[:200]
            extracted = dict(answers={}, text='', blocks=[], warnings=['Text extraction was unavailable; review every answer.'],
                reader_revision='unavailable', extraction_confidence=None, mapping_confidence=None,
                requires_confirmation=True, handwriting_support='unverified', truncated=False)
        if vision_failed:
            extracted['warnings'].append('Vision extraction was unavailable. Review and correct the OCR text before grading.')
        return await run_in_threadpool(self.repository.store_extraction, owner, identifier, expected_revision, extracted, data, safe_filename)


@workflow_logger.operation(outcome='success')
def create_assessments(sessions, llm, learner, rag=None, profile=None):
    from .repositories.postgres import AssessmentRepository
    from app.langchain.assessment_workflows import AssessmentWorkflows
    return AssessmentService(AssessmentRepository(sessions), AssessmentWorkflows(llm, learner, rag, profile))
