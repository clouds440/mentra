from uuid import uuid4
from app.core.exceptions import AppError
from app.assessments.schemas import GeneratedAssessment, GradedAssessment
from app.learner.schemas import ConceptResolutionRequest, StudyRecommendationsRequest, VerificationCandidatesRequest, EvidenceSubmissionRequest
from app.rag.schemas import AssessmentGroundingRequest
from .prompts import PromptSource


class AssessmentWorkflows:
    def __init__(self, llm, learner, rag=None): self.llm, self.learner, self.rag = llm, learner, rag

    async def generate(self, owner, request):
        from starlette.concurrency import run_in_threadpool
        await run_in_threadpool(self.learner.get_context_summaries, owner, [request.context_id])
        concepts = []
        for label in request.concept_names:
            resolution = await run_in_threadpool(self.learner.resolve_concept, ConceptResolutionRequest(label=label, learner_id=owner, context_id=request.context_id))
            if resolution.status == 'resolved': concepts.append(resolution.concept_id)
            elif request.confirm_new_concepts and resolution.status == 'candidate':
                concept = await run_in_threadpool(self.learner.register_concept, label)
                concepts.append(concept.id)
            else: raise AppError('CONCEPT_REVIEW_REQUIRED', 'Confirm new concept names or select established concepts before generating.', 409)
        recommendations = await run_in_threadpool(self.learner.get_study_recommendations, StudyRecommendationsRequest(learner_id=owner, context_ids=[request.context_id], limit=5))
        verification = await run_in_threadpool(self.learner.get_verification_candidates, VerificationCandidatesRequest(learner_id=owner, context_ids=[request.context_id], limit=5))
        if not concepts: concepts = list(dict.fromkeys(item.concept_id for item in [*recommendations, *verification]))[:10]
        if not concepts: raise AppError('ASSESSMENT_TARGETS_REQUIRED', 'Enter and confirm the concept names you want to practice.', 422)
        targets = [dict(id=identifier, name=(await run_in_threadpool(self.learner.get_concept, identifier)).canonical_name) for identifier in concepts]
        sources = []
        if request.grounded and self.rag:
            if not request.document_ids: raise AppError('ASSESSMENT_SOURCES_REQUIRED', 'Select study documents to ground this assessment.', 422)
            retrieved = await run_in_threadpool(self.rag.search_assessment, owner, AssessmentGroundingRequest(query=request.topic, context_ids=[request.context_id], approved_document_ids=request.document_ids, limit=5))
            sources = [chunk.source.model_dump(mode='json') for chunk in retrieved.chunks]
            if not sources: raise AppError('ASSESSMENT_SOURCES_REQUIRED', 'No ready study sources matched this topic.', 409)
        generated = await self.llm.ainvoke(PromptSource.ASSESSMENT_GENERATION,
            dict(topic=request.topic, count=request.count, purpose=request.purpose, targets=targets,
                recommendations=[item.model_dump(mode='json') for item in recommendations],
                verification=[item.model_dump(mode='json') for item in verification], sources=sources), output_schema=GeneratedAssessment)
        allowed, tokens = set(concepts), {source['token'] for source in sources}
        if len(generated.questions) != request.count or any(set(question.concept_ids)-allowed or set(question.source_tokens)-tokens for question in generated.questions):
            raise AppError('ASSESSMENT_INVALID_GENERATION', 'The generated assessment did not match its approved targets. Try again.', 502)
        return generated, sources

    async def grade(self, job):
        assessment, attempt = job['assessment'], job['attempt']
        result = await self.llm.ainvoke(PromptSource.ASSESSMENT_GRADING,
            dict(questions=assessment['questions'], answers=attempt['answers'],
                transcription_confirmed=attempt['extraction'] is not None), output_schema=GradedAssessment)
        expected = {question['id']: question for question in assessment['questions']}
        if len(result.questions) != len(expected) or {question.question_id for question in result.questions} != set(expected):
            raise AppError('ASSESSMENT_INVALID_GRADE', 'The grading result was incomplete.', 502)
        for grade in result.questions:
            question = expected[grade.question_id]
            if grade.score > question['marks'] or set(grade.concept_grades) != set(question['concept_ids']) or any(value.max_score != question['marks'] for value in grade.concept_grades.values()):
                raise AppError('ASSESSMENT_INVALID_GRADE', 'The grading result changed the approved question schema.', 502)
        return result

    def evidence(self, job, grades, unit_of_work):
        assessment, attempt = job['assessment'], job['attempt']
        questions = {question['id']:question for question in assessment['questions']}
        requests = []
        previous = {(receipt.get('question_id'),receipt['concept_id']):receipt['evidence_id'] for receipt in (attempt.get('evidence_receipt') or []) if receipt['accepted']}
        for grade in grades.questions:
            question = questions[grade.question_id]
            for concept, value in grade.concept_grades.items():
                requests.append(EvidenceSubmissionRequest(learner_id=job['owner'], concept_id=concept, context_id=assessment['context_id'],
                    source_type='HANDWRITTEN_ASSESSMENT' if attempt['extraction'] else 'CALIBRATION' if assessment['purpose']=='calibration' else 'QUIZ',
                    source_id=f"assessment:{job['id']}:{attempt['grade_revision']}:{grade.question_id}:{concept}", item_id=f"{assessment['id']}:{grade.question_id}",
                    session_id=job['id'], item_revision=attempt['grade_revision'], attempt_number=attempt['attempt_number'],
                    supersedes_evidence_id=previous.get((grade.question_id,concept)) if attempt['grade_revision']>1 else None,
                    result='CORRECT' if value.score==value.max_score else 'INCORRECT' if value.score==0 else 'PARTIAL',
                    score=value.score, max_score=value.max_score, difficulty=question['difficulty'], independence=1, hint_count=0,
                    evidence_confidence=min(grade.confidence,value.confidence), occurred_at=attempt['submitted_at'],
                    metadata=dict(assessment_id=assessment['id'], attempt_id=job['id'], question_id=grade.question_id, grading_revision='assessment-grading-v1',
                        misconceptions=grade.misconceptions, transcription_confirmed=bool(attempt['extraction']))))
        results = self.learner.submit_evidence_batch_in_transaction(requests, unit_of_work,
            transcription_confirmation=f"assessment-transcription:{job['id']}" if attempt['extraction'] else None)
        return [dict(result.model_dump(mode='json'),question_id=request.metadata['question_id']) for request,result in zip(requests,results)]
