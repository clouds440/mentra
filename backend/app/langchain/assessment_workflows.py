from uuid import uuid4
from app.core.exceptions import AppError
from app.assessments.schemas import GeneratedAssessment, GradedAssessment, AssessmentTargets
from app.learner.schemas import EvidenceSubmissionRequest, LearnerContextRequest
from app.rag.schemas import AssessmentGroundingRequest
from .prompts import PromptSource
from .generation_recovery import invoke_generated, validate_questions


from app.core.logging import workflow_logger

@workflow_logger.connect_module(default_outcome='success')
class AssessmentWorkflows:
    def __init__(self, llm, learner, rag=None, profile=None): self.llm, self.learner, self.rag, self.profile = llm, learner, rag, profile

    async def generate(self, owner, request, *, revision=None, checkpoint=None, resume=None):
        from app.assessments.blueprint import blueprint
        from app.core.observability.timing import run_in_threadpool
        await run_in_threadpool(self.learner.get_context_summaries, owner, [request.context_id])
        concepts = list(dict.fromkeys(identifier for question in revision['questions'] for identifier in question['concept_ids'])) if revision else []
        sources = []
        if request.grounded:
            if self.rag is None:
                raise AppError('ASSESSMENT_SOURCES_REQUIRED', 'Study retrieval is required for a grounded assessment.', 503)
            if not request.document_ids: raise AppError('ASSESSMENT_SOURCES_REQUIRED', 'Select study documents to ground this assessment.', 422)
            retrieved = await run_in_threadpool(self.rag.search_assessment, owner, AssessmentGroundingRequest(query=request.topic, context_ids=[request.context_id], approved_document_ids=request.document_ids, limit=5))
            sources = [chunk.source.model_dump(mode='json') for chunk in retrieved.chunks]
            if not sources: raise AppError('ASSESSMENT_SOURCES_REQUIRED', 'No ready study sources matched this topic.', 409)
        prompt_sources = [{key:source[key] for key in ('token','title','excerpt')} for source in sources]
        if not revision:
            labels = [label.strip() for label in request.concept_names if label.strip()]
            inferred = not labels
            if inferred:
                ranked = await run_in_threadpool(self.learner.get_study_targets, owner, [request.context_id])
                known = list(dict.fromkeys(item.concept_id for item in [*ranked['recommendations'], *ranked['verification']]))[:10]
                known_concepts = await run_in_threadpool(self.learner.get_concepts, known)
                known_names = [known_concepts[identifier].canonical_name for identifier in known]
                try:
                    plan = await invoke_generated(self.llm, PromptSource.ASSESSMENT_TARGETS,
                        dict(topic=request.topic, count=request.count, purpose=request.purpose,
                             grounded=request.grounded, sources=prompt_sources, existing_concepts=known_names), output_schema=AssessmentTargets)
                    labels = plan.concept_names
                except AppError as error:
                    if error.code != 'ASSESSMENT_INVALID_GENERATION': raise
                    # A malformed optional topic plan cannot veto a valid request.
                    # Use the requested topic itself; questions still need full
                    # validation and grounded requests still require their sources.
                    workflow_logger.event('assessment.target_fallback', strategy='requested_topic')
                    labels = [request.topic]
            from app.learner.schemas import GeneratedConceptsRequest
            from .assessment_concepts import concept_label
            labels = list(dict.fromkeys(concept_label(label) for label in labels))
            concepts = []
            for offset in range(0, len(labels), 5):
                resolved = await self.learner.resolve_generated_concepts(GeneratedConceptsRequest(
                    learner_id=owner, context_id=request.context_id, topic=request.topic, labels=labels[offset:offset+5], permissive=True))
                concepts.extend(concept.id for concept in resolved)
            concepts = list(dict.fromkeys(concepts))
        ranked = await run_in_threadpool(self.learner.get_study_targets, owner, [request.context_id])
        recommendations, verification = ranked['recommendations'], ranked['verification']
        target_concepts = await run_in_threadpool(self.learner.get_concepts, concepts)
        targets = [dict(id=identifier, name=target_concepts[identifier].canonical_name) for identifier in concepts]
        questions = []
        title = None
        profile_context = await run_in_threadpool(self.profile.prompt_context, owner) if self.profile else None
        learner_context = await run_in_threadpool(self.learner.get_relevant_context,
            LearnerContextRequest(
                learner_id=owner, query=request.topic, context_ids=[request.context_id], max_concepts=8))
        from app.assessments.schemas import GeneratedQuestion, PaperInfo
        from hashlib import sha256
        import json
        source_signature = sha256(json.dumps([{key: source.get(key) for key in ('token','document_id','generation_id','chunk_id','excerpt')} for source in sources], sort_keys=True).encode()).hexdigest()
        resume = resume or {}
        if resume.get('plan') and resume.get('source_signature') == source_signature:
            question_plan = resume['plan']
            paper = PaperInfo.model_validate(resume['paper']) if resume.get('paper') else None
            questions = [GeneratedQuestion.model_validate(value) for value in resume.get('questions', [])]
            title = resume.get('title')
        elif not request.paper_sections and (request.question_format in ('mixed', 'mock_paper') or request.count is None or request.instructions):
            from .assessment_design import design_assessment
            question_plan, paper = await design_assessment(self.llm, request, prompt_sources,
                profile_context.model_dump(mode='json') if profile_context else None, original=revision,
                learner_context=learner_context.model_dump(mode='json'))
        else:
            question_plan, paper = blueprint(request)
        async def save_progress():
            if checkpoint:
                await checkpoint(dict(schema_version=1, plan=question_plan, paper=paper.model_dump(mode='json') if paper else None,
                    questions=[question.model_dump(mode='json') for question in questions], title=title, source_signature=source_signature))
        await save_progress()
        # Bound output per call instead of asking for ten long rubrics at once.
        while len(questions) < len(question_plan):
            batch_count = min(3, len(question_plan)-len(questions))
            batch_plan = question_plan[len(questions):len(questions)+batch_count]
            generated = await invoke_generated(self.llm, PromptSource.ASSESSMENT_GENERATION,
            dict(topic=request.topic, question_format=request.question_format, question_plan=batch_plan,
                paper=dict(duration_minutes=paper.duration_minutes, total_marks=paper.total_marks, instructions=paper.instructions,
                    sections=[dict(title=section.title, instructions=section.instructions) for section in paper.sections]) if paper else None, instructions=request.instructions,
                count=batch_count, question_offset=len(questions), purpose=request.purpose, targets=targets,
                recommendations=[item.model_dump(mode='json') for item in recommendations if item.concept_id in concepts],
                verification=[item.model_dump(mode='json') for item in verification if item.concept_id in concepts], sources=prompt_sources,
                profile=profile_context.model_dump(mode='json') if profile_context else None,
                learner_context=learner_context.model_dump(mode='json'), level=request.level, result_style=request.result_style,
                previous_prompts=[question.prompt[:250] for question in questions],
                revision_instructions=request.revision_instructions,
                original_overview=[dict(number=index, excerpt=q['prompt'][:160], truncated=len(q['prompt'])>160)
                    for index,q in enumerate(revision['questions'],1)] if revision else None,
                original_questions=[dict(prompt=q['prompt'], marks=q['marks'], difficulty=q['difficulty'], concept_ids=q['concept_ids'], options=q.get('options', []))
                    for q in revision['questions'][len(questions):len(questions)+batch_count]] if revision else None), output_schema=GeneratedAssessment,
                validate=lambda result: validate_questions(result, count=batch_count,
                    question_format=request.question_format, concepts=None,
                    tokens={source['token'] for source in sources}, grounded=request.grounded,
                    previous=[question.prompt.casefold().strip() + '|' + question.context.casefold().strip() for question in questions], plan=batch_plan))
            title = title or generated.title
            for question, planned in zip(generated.questions, batch_plan):
                for key, value in planned.items():
                    if key in type(question).model_fields:
                        setattr(question, key, value)
            from .assessment_concepts import resolve_question_concepts
            await resolve_question_concepts(self.learner, owner, request, generated.questions, targets)
            questions.extend(generated.questions)
            await save_progress()
        generated = GeneratedAssessment(title=title, questions=questions, paper=paper)
        return generated, sources

    async def grade(self, job, *, checkpoint=None):
        assessment, attempt = job['assessment'], job['attempt']
        from app.assessments.grading_progress import grading_signature
        from app.assessments.schemas import QuestionGrade, ConceptGrade
        progress = attempt.get('grading_progress') or {}
        grades = [QuestionGrade.model_validate(value) for value in progress.get('grades', [])] if progress.get('signature') == grading_signature(job) else []
        completed_ids = {grade.question_id for grade in grades}
        from .token_policy import check_input
        from .llm import MentraLLM
        batches, current = [], []
        # A question/rubric/answer is indivisible. Never silently trim student work.
        for question in assessment['questions']:
            if question.get('options') or question['id'] in completed_ids: continue
            proposed = [*current, question]
            payload = dict(questions=proposed, answers={q['id']:attempt['answers'][q['id']] for q in proposed},
                           result_style=assessment.get('preferences', {}).get('result_style','marks'),
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
        for question in assessment['questions']:
            if question.get('options') and question['id'] not in completed_ids:
                from app.assessments.choice_answers import selected_options
                chosen = set(selected_options(question, attempt['answers'][question['id']]))
                expected = set(question.get('correct_option_ids') or [question['correct_option_id']])
                incorrect_count = len(question['options']) - len(expected)
                fraction = len(chosen & expected) / len(expected) - len(chosen - expected) / max(1, incorrect_count)
                score = round(question['marks'] * max(0, fraction), 4)
                correct = chosen == expected
                grades.append(QuestionGrade(question_id=question['id'], score=score, confidence=1,
                    feedback=(('Correct. ' if correct else 'Partly correct. ' if score else 'Incorrect. ') + question['model_answer'])[:2000],
                    concept_grades={identifier:ConceptGrade(score=score, max_score=question['marks'], confidence=1)
                        for identifier in question['concept_ids']}))
        if checkpoint and grades: await checkpoint(grades)
        for batch in batches:
            batch = [q for q in batch if not q.get('options')]
            if not batch: continue
            from .generation_recovery import GenerationMismatch
            def validate_batch(result):
                by_id = {question['id']:question for question in batch}
                if len(result.questions) != len(batch) or {grade.question_id for grade in result.questions} != set(by_id):
                    raise GenerationMismatch('grade_question_ids_must_match_batch')
                for grade in result.questions:
                    question = by_id[grade.question_id]
                    if grade.score > question['marks'] or set(grade.concept_grades) != set(question['concept_ids']) or any(value.max_score != question['marks'] for value in grade.concept_grades.values()):
                        raise GenerationMismatch('grade_marks_and_concept_ids_must_match_question')
            partial = await invoke_generated(self.llm, PromptSource.ASSESSMENT_GRADING,
                dict(questions=batch, answers={q['id']:attempt['answers'][q['id']] for q in batch},
                     result_style=assessment.get('preferences', {}).get('result_style','marks'),
                     transcription_confirmed=attempt['extraction'] is not None), output_schema=GradedAssessment, validate=validate_batch)
            if len(partial.questions) != len(batch) or {q.question_id for q in partial.questions} != {q['id'] for q in batch}:
                raise AppError('ASSESSMENT_INVALID_GRADE', 'A grading batch was incomplete.', 502)
            grades.extend(partial.questions)
            if checkpoint: await checkpoint(grades)
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
                    source_type='HANDWRITTEN_ASSESSMENT' if attempt['extraction'] else 'MOCK_EXAM' if assessment.get('paper') else 'CALIBRATION' if assessment['purpose']=='calibration' else 'QUIZ',
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
