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

    async def generate(self, owner, request):
        previous = await run_in_threadpool(self.repository.replay, owner, request)
        if previous: return previous
        generated, sources = await self.workflows.generate(owner, request)
        return await run_in_threadpool(self.repository.save, owner, request, generated, sources)

    def submit(self, owner, identifier, body):
        attempt = self.repository.attempt(owner, identifier)
        if attempt.state == 'pending_transcription':
            if not body.transcription_confirmed:
                raise AppError('TRANSCRIPTION_CONFIRMATION_REQUIRED', 'Review and explicitly confirm all extracted answers before grading.', 422)
            self.paper_graph.decide(owner, identifier, 'confirmed')
        return self.repository.submit(owner, identifier, body)

    def upload_paper(self, owner, identifier, expected_revision, source, filename):
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
        return self.repository.store_extraction(owner, identifier, expected_revision, extracted, data, filename)


@workflow_logger.operation(outcome='success')
def create_assessments(sessions, llm, learner, rag=None):
    from .repositories.postgres import AssessmentRepository
    from app.langchain.assessment_workflows import AssessmentWorkflows
    return AssessmentService(AssessmentRepository(sessions), AssessmentWorkflows(llm, learner, rag))
