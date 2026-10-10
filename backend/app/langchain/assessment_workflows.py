from uuid import uuid4
from app.core.exceptions import AppError
from app.assessments.schemas import GeneratedAssessment, GradedAssessment
from app.learner.schemas import ConceptResolutionRequest, StudyRecommendationsRequest, VerificationCandidatesRequest, EvidenceSubmissionRequest
from app.rag.schemas import AssessmentGroundingRequest
from .prompts import PromptSource


from app.core.logging import workflow_logger

@workflow_logger.connect_module(default_outcome='success')
class AssessmentWorkflows:
    def __init__(self, llm, learner, rag=None, profile=None): self.llm, self.learner, self.rag, self.profile = llm, learner, rag, profile

    async def generate(self, owner, request, *, revision=None):
        from starlette.concurrency import run_in_threadpool
        await run_in_threadpool(self.learner.get_context_summaries, owner, [request.context_id])
        concepts = list(dict.fromkeys(identifier for question in revision['questions'] for identifier in question['concept_ids'])) if revision else []
        for label in ([] if revision else request.concept_names):
            resolution = await run_in_threadpool(self.learner.resolve_concept, ConceptResolutionRequest(label=label, learner_id=owner, context_id=request.context_id))
            if resolution.status == 'resolved':
                await run_in_threadpool(self.learner.link_context_concept, owner, request.context_id, resolution.concept_id)
                concepts.append(resolution.concept_id)
            elif request.confirm_new_concepts and resolution.status == 'candidate':
                concept = await run_in_threadpool(self.learner.review_candidate, resolution.candidate_id)
                concepts.append(concept.id)
            else: raise AppError('CONCEPT_REVIEW_REQUIRED', 'Confirm new concept names or select established concepts before generating.', 409)
        ranked = await run_in_threadpool(self.learner.get_study_targets, owner, [request.context_id])
        recommendations, verification = ranked['recommendations'], ranked['verification']
        if not concepts: concepts = list(dict.fromkeys(item.concept_id for item in [*recommendations, *verification]))[:10]
        if not concepts: raise AppError('ASSESSMENT_TARGETS_REQUIRED', 'Enter and confirm the concept names you want to practice.', 422)
        targets = [dict(id=identifier, name=(await run_in_threadpool(self.learner.get_concept, identifier)).canonical_name) for identifier in concepts]
        sources = []
        if request.grounded:
            if self.rag is None:
                raise AppError('ASSESSMENT_SOURCES_REQUIRED', 'Study retrieval is required for a grounded assessment.', 503)
            if not request.document_ids: raise AppError('ASSESSMENT_SOURCES_REQUIRED', 'Select study documents to ground this assessment.', 422)
            retrieved = await run_in_threadpool(self.rag.search_assessment, owner, AssessmentGroundingRequest(query=request.topic, context_ids=[request.context_id], approved_document_ids=request.document_ids, limit=5))
            sources = [chunk.source.model_dump(mode='json') for chunk in retrieved.chunks]
            if not sources: raise AppError('ASSESSMENT_SOURCES_REQUIRED', 'No ready study sources matched this topic.', 409)
        questions = []
        title = None
        profile_context = await run_in_threadpool(self.profile.prompt_context, owner) if self.profile else None
        prompt_sources = [{key:source[key] for key in ('token','title','excerpt')} for source in sources]
        # Bound output per call instead of asking for ten long rubrics at once.
        while len(questions) < request.count:
            batch_count = min(3, request.count-len(questions))
            generated = await self.llm.ainvoke(PromptSource.ASSESSMENT_GENERATION,
            dict(topic=request.topic, count=batch_count, question_offset=len(questions), purpose=request.purpose, targets=targets,
                recommendations=[item.model_dump(mode='json') for item in recommendations if item.concept_id in concepts],
                verification=[item.model_dump(mode='json') for item in verification if item.concept_id in concepts], sources=prompt_sources,
                profile=profile_context.model_dump(mode='json') if profile_context else None,
                previous_prompts=[question.prompt[:250] for question in questions],
                revision_instructions=request.revision_instructions,
                original_overview=[dict(number=index, excerpt=q['prompt'][:160], truncated=len(q['prompt'])>160)
                    for index,q in enumerate(revision['questions'],1)] if revision else None,
                original_questions=[dict(prompt=q['prompt'], marks=q['marks'], difficulty=q['difficulty'], concept_ids=q['concept_ids'])
                    for q in revision['questions'][len(questions):len(questions)+batch_count]] if revision else None), output_schema=GeneratedAssessment)
            if len(generated.questions) != min(3, request.count-len(questions)):
                raise AppError('ASSESSMENT_INVALID_GENERATION', 'The generated assessment did not match its requested count.', 502)
            title = title or generated.title
            questions.extend(generated.questions)
        generated = GeneratedAssessment(title=title, questions=questions)
        allowed, tokens = set(concepts), {source['token'] for source in sources}
        if len({question.prompt.casefold().strip() for question in generated.questions}) != request.count or any(set(question.concept_ids)-allowed or set(question.source_tokens)-tokens or (request.grounded and not question.source_tokens) for question in generated.questions):
            raise AppError('ASSESSMENT_INVALID_GENERATION', 'The generated assessment did not match its approved targets. Try again.', 502)
        return generated, sources

    async def grade(self, job):
        assessment, attempt = job['assessment'], job['attempt']
        from .token_policy import check_input
        from .llm import MentraLLM
        batches, current = [], []
        # A question/rubric/answer is indivisible. Never silently trim student work.
        for question in assessment['questions']:
            proposed = [*current, question]
            payload = dict(questions=proposed, answers={q['id']:attempt['answers'][q['id']] for q in proposed},
                           transcription_confirmed=attempt['extraction'] is not None)
            try:
                check_input(MentraLLM.messages(self.llm, PromptSource.ASSESSMENT_GRADING, payload),
                            PromptSource.ASSESSMENT_GRADING, tools=[GradedAssessment])
                fits = len(proposed) <= 2
            except AppError:
                fits = False
            if not fits and current:
                batches.append(current)
                current = [question]
            else:
                current = proposed
        if current:
            batches.append(current)
        grades = []
        for batch in batches:
            partial = await self.llm.ainvoke(PromptSource.ASSESSMENT_GRADING,
                dict(questions=batch, answers={q['id']:attempt['answers'][q['id']] for q in batch},
                     transcription_confirmed=attempt['extraction'] is not None), output_schema=GradedAssessment)
            if len(partial.questions) != len(batch) or {q.question_id for q in partial.questions} != {q['id'] for q in batch}:
                raise AppError('ASSESSMENT_INVALID_GRADE', 'A grading batch was incomplete.', 502)
            grades.extend(partial.questions)
        result = GradedAssessment(questions=grades)
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
        withdraw = []
        for grade in grades.questions:
            question = questions[grade.question_id]
            for concept, value in grade.concept_grades.items():
                if min(grade.confidence, value.confidence) < .8:
                    old = previous.get((grade.question_id, concept))
                    if old:
                        withdraw.append(old)
                    continue
                requests.append(EvidenceSubmissionRequest(learner_id=job['owner'], concept_id=concept, context_id=assessment['context_id'],
                    source_type='HANDWRITTEN_ASSESSMENT' if attempt['extraction'] else 'CALIBRATION' if assessment['purpose']=='calibration' else 'QUIZ',
                    source_id=f"assessment:{job['id']}:{attempt['grade_revision']}:{grade.question_id}:{concept}", item_id=f"{assessment['id']}:{grade.question_id}",
                    session_id=job['id'], item_revision=attempt['grade_revision'], attempt_number=attempt['attempt_number'],
                    supersedes_evidence_id=previous.get((grade.question_id,concept)) if attempt['grade_revision']>1 else None,
                    result='CORRECT' if value.score==value.max_score else 'INCORRECT' if value.score==0 else 'PARTIAL',
                    score=value.score, max_score=value.max_score, difficulty=question['difficulty'],
                    independence=1 if attempt.get('assistance') == 'independent' else .4 if attempt.get('assistance') == 'assisted' else None, hint_count=0,
                    evidence_confidence=min(grade.confidence,value.confidence), occurred_at=attempt['submitted_at'],
                    metadata=dict(assessment_id=assessment['id'], attempt_id=job['id'], question_id=grade.question_id, grading_revision='assessment-grading-v1',
                        question_score=grade.score, question_max_score=question['marks'],
                        misconceptions=grade.misconceptions, transcription_confirmed=bool(attempt['extraction']),
                        assistance=attempt.get('assistance','unknown'), independence_provenance='self_reported', profile_context_version=job.get('profile_context_version'))))
        if withdraw:
            self.learner.withdraw_assessment_evidence_in_transaction(job['owner'], withdraw, job['id'], unit_of_work)
        if not requests:
            from .profile_bridge import project_learning_profile
            project_learning_profile(unit_of_work, job['owner'])
            return None
        results = self.learner.submit_evidence_batch_in_transaction(requests, unit_of_work,
            transcription_confirmation=f"assessment-transcription:{job['id']}" if attempt['extraction'] else None)
        from .profile_bridge import project_learning_profile
        project_learning_profile(unit_of_work, job['owner'])
        return [dict(result.model_dump(mode='json'),question_id=request.metadata['question_id']) for request,result in zip(requests,results)]
