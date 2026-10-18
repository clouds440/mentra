from app.core.exceptions import AppError
from app.assessments.schemas import GeneratedAssessment, GeneratedAssessmentBatch, GradedAssessment, AssessmentTargets
from app.learner.schemas import EvidenceSubmissionRequest, LearnerContextRequest
from app.rag.schemas import AssessmentGroundingRequest
from .prompts import PromptSource
from .generation_recovery import invoke_generated, validate_questions, GenerationMismatch


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
        if not revision and request.concept_ids:
            exact = await run_in_threadpool(self.learner.get_practice_concepts, owner, request.context_id,
                                           [str(identifier) for identifier in request.concept_ids])
            concepts = [concept.id for concept in exact]
        elif not revision:
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
        elif not request.paper_sections and (request.question_formats or request.question_format in ('mixed', 'mock_paper') or request.count is None or request.instructions):
            from .assessment_design import design_assessment
            question_plan, paper = await design_assessment(self.llm, request, prompt_sources,
                profile_context.model_dump(mode='json') if profile_context else None, original=revision,
                learner_context=learner_context.model_dump(mode='json'))
        else:
            question_plan, paper = blueprint(request)
        if not paper: question_plan = question_plan[:min(request.count or 20,20)]
        async def save_progress():
            if checkpoint:
                await checkpoint(dict(schema_version=1, plan=question_plan, paper=paper.model_dump(mode='json') if paper else None,
                    questions=[question.model_dump(mode='json') for question in questions], title=title, source_signature=source_signature))
        await save_progress()
        import asyncio
        from .token_policy import output_budget
        from app.core.config import settings
        config=getattr(getattr(self.llm,'model_factory',None),'_settings',settings)
        reserve=output_budget(PromptSource.ASSESSMENT_GENERATION,config)
        weights={'mcq':350,'true_false':200,'short_answer':250,'multiple_select':450,
            'numerical':300,'fill_blank':250,'matching':400,'ordering':400,'essay':1000,'proof':1200,'case_study':1100}
        expected_output=600+sum(weights.get(item['question_type'],600) for item in question_plan)
        context_size=sum(len(item.get('context',''))+len(item.get('brief','')) for item in question_plan)+len(request.instructions)
        long_revision=bool(revision and sum(len(q['prompt']) for q in revision['questions'])>6000)
        split=expected_output>reserve*.95 or context_size>max(2000,config.chat_context_window_tokens-reserve-6000) or long_revision
        batch_size=(3 if long_revision else 6) if split else len(question_plan)
        workflow_logger.event('assessment.generation_plan', parts=len(question_plan), batch_size=batch_size,
            concurrent_batches=min(2,(len(question_plan)+batch_size-1)//batch_size))
        from .assessment_payloads import generation_payload
        shared_payload = dict(topic=request.topic, question_format=request.question_format,
            instructions=request.instructions, purpose=request.purpose, targets=targets,
            recommendations=[item.model_dump(mode='json', exclude_none=True) for item in recommendations if item.concept_id in concepts],
            verification=[item.model_dump(mode='json', exclude_none=True) for item in verification if item.concept_id in concepts],
            sources=prompt_sources, profile=profile_context.model_dump(mode='json', exclude_none=True) if profile_context else None,
            learner_context=learner_context.model_dump(mode='json', exclude_none=True), level=request.level, result_style=request.result_style,
            paper=dict(duration_minutes=paper.duration_minutes, total_marks=paper.total_marks, instructions=paper.instructions,
                sections=[dict(title=section.title, instructions=section.instructions) for section in paper.sections]) if paper else None,
            **(dict(revision_instructions=request.revision_instructions) if revision else {}))
        async def generate_batch(offset, prior):
            batch_plan = question_plan[offset:offset+batch_size]
            batch_count = len(batch_plan)
            generated = await invoke_generated(self.llm, PromptSource.ASSESSMENT_GENERATION,
            generation_payload(shared=shared_payload, plan=question_plan, offset=offset,
                batch_size=batch_size, prior=prior, revision=revision), output_schema=GeneratedAssessmentBatch,
                maximum_attempts=1 if batch_count>6 else 2,
                validate=lambda result: validate_questions(result, count=batch_count,
                    question_format=request.question_format, concepts=set(concepts) if request.concept_ids else None, require_attribution=bool(request.concept_ids),
                    tokens={source['token'] for source in sources}, grounded=request.grounded,
                    previous=[question.prompt.casefold().strip() + '|' + question.context.casefold().strip() for question in prior], plan=batch_plan))
            return generated, batch_plan
        # Independent outline batches overlap; only ordered prefixes are checkpointed.
        # This keeps refresh/retry deterministic even when a later call finishes first.
        while len(questions) < len(question_plan):
            prior=list(questions)
            offsets=range(len(questions),min(len(question_plan),len(questions)+batch_size*2),batch_size)
            tasks=[(offset,asyncio.create_task(generate_batch(offset,prior))) for offset in offsets]
            try:
                for offset,task in tasks:
                    generated,batch_plan=await task
                    try:
                        validate_questions(generated,count=len(batch_plan),question_format=request.question_format,concepts=None,
                            tokens={source['token'] for source in sources},grounded=request.grounded,
                            previous=[q.prompt.casefold().strip()+'|'+q.context.casefold().strip() for q in questions],plan=batch_plan)
                    except GenerationMismatch:
                        generated,batch_plan=await generate_batch(offset,list(questions))
                    title = title or generated.title
                    for question, planned in zip(generated.questions, batch_plan):
                        for key,value in planned.items():
                            if key in type(question).model_fields: setattr(question,key,value)
                    from .assessment_concepts import resolve_question_concepts
                    await resolve_question_concepts(self.learner,owner,request,generated.questions,targets)
                    questions.extend(generated.questions)
                    await save_progress()
            except AppError as error:
                if error.code=='ASSESSMENT_INVALID_GENERATION' and batch_size>6:
                    batch_size=6
                    workflow_logger.event('assessment.generation_fallback',batch_size=batch_size)
                else: raise
            finally:
                for _,task in tasks:
                    if not task.done(): task.cancel()
                await asyncio.gather(*(task for _,task in tasks),return_exceptions=True)
        generated = GeneratedAssessment(title=title, questions=questions, paper=paper)
        return generated, sources

    async def grade(self, job, *, checkpoint=None):
        assessment, attempt = job['assessment'], job['attempt']
        from app.assessments.grading_progress import grading_signature
        from app.assessments.schemas import QuestionGrade, ConceptGrade
        progress = attempt.get('grading_progress') or {}
        grades = [QuestionGrade.model_validate(value) for value in progress.get('grades', [])] if progress.get('signature') == grading_signature(job) else []
        completed_ids = {grade.question_id for grade in grades}
        import asyncio
        from .grading_batches import plan_grading_batches, grading_payload, grading_output_tokens
        from app.core.config import settings
        grading_config = getattr(getattr(self.llm, 'model_factory', None), '_settings', settings)
        pending = [q for q in assessment['questions'] if not q.get('options') and q['id'] not in completed_ids]
        batches = plan_grading_batches(self.llm, assessment, attempt, pending)
        workflow_logger.event('assessment.grading_plan', questions=len(assessment['questions']),
            pending_written=len(pending), completed=len(grades), batches=len(batches),
            batch_sizes=[len(batch) for batch in batches], concurrent_batches=len(batches))
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
        async def grade_batch(batch):
            def validate_batch(result):
                from app.assessments.grade_alignment import align_grades
                align_grades(result,batch)
            partial = await invoke_generated(self.llm, PromptSource.ASSESSMENT_GRADING,
                grading_payload(assessment, attempt, batch), output_schema=GradedAssessment, validate=validate_batch,
                output_tokens=grading_output_tokens(grading_config, batch))
            if len(partial.questions) != len(batch) or {q.question_id for q in partial.questions} != {q['id'] for q in batch}:
                raise AppError('ASSESSMENT_INVALID_GRADE', 'A grading batch was incomplete.', 502)
            return partial.questions
        tasks = [asyncio.create_task(grade_batch(batch)) for batch in batches]
        order = {q['id']: index for index, q in enumerate(assessment['questions'])}
        try:
            # Persist whichever batch finishes first. A retry only evaluates the
            # unfinished questions, even when the other call fails or times out.
            for finished in asyncio.as_completed(tasks):
                grades.extend(await finished)
                grades.sort(key=lambda grade: order[grade.question_id])
                if checkpoint: await checkpoint(grades)
        finally:
            for task in tasks:
                if not task.done(): task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
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
        lineage = assessment.get('practice_lineage') or {}
        exposed = bool(lineage.get('known_exposure'))
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
                    source_id=f"assessment:{job['id']}:{attempt['grade_revision']}:{grade.question_id}:{concept}",
                    item_id=lineage.get('question_items', {}).get(grade.question_id, f"{assessment['id']}:{grade.question_id}"),
                    session_id=job['id'], item_revision=attempt['grade_revision'], attempt_number=attempt['attempt_number'] + int(exposed),
                    supersedes_evidence_id=previous.get((grade.question_id,concept)) if attempt['grade_revision']>1 else None,
                    result='CORRECT' if value.score==value.max_score else 'INCORRECT' if value.score==0 else 'PARTIAL',
                    score=value.score, max_score=value.max_score, difficulty=question['difficulty'],
                    independence=0 if exposed else 1 if attempt.get('assistance') == 'independent' else .4 if attempt.get('assistance') == 'assisted' else None, hint_count=0,
                    evidence_confidence=min(grade.confidence,value.confidence), occurred_at=attempt['submitted_at'],
                    metadata=dict(assessment_id=assessment['id'], attempt_id=job['id'], question_id=grade.question_id, grading_revision='assessment-grading-v1',
                        question_score=grade.score, question_max_score=question['marks'],
                        misconceptions=grade.misconceptions, transcription_confirmed=bool(attempt['extraction']),
                        assistance=attempt.get('assistance','unknown'), independence_provenance='known_answer_exposure' if exposed else 'self_reported',
                        **(dict(known_exposure=True, source_attempt_id=lineage['attempt_id'], source_grade_revision=lineage['grade_revision']) if exposed else {}),
                        profile_context_version=job.get('profile_context_version'))))
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
