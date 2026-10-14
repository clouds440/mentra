"""Choose omissions using the same owner-bound read tools as chat."""
import asyncio
from app.assessments.schemas import AssessmentSelection, GenerationRequest
from app.learner.schemas import ResolveLearningContextRequest
from app.core.observability.timing import run_in_threadpool
from .learner_tools import create_learner_tools
from .generation_recovery import invoke_generated, GenerationMismatch
from .prompts import PromptSource


async def resolve_assessment_intent(workflows, owner, intent):
    learner = workflows.learner
    if intent.context_id:
        await run_in_threadpool(learner.get_context_summaries, owner, [intent.context_id])
    # An explicit topic and format need no extra model decision.
    if intent.topic and intent.question_format != 'auto':
        topic, context_id, kind, labels = intent.topic, intent.context_id, intent.question_format, intent.concept_names
    else:
        tools = {tool.name: tool for tool in create_learner_tools(learner, owner)}
        contexts = (await tools['get_active_learning_contexts'].ainvoke({}))['contexts']
        if not contexts:
            rows = await run_in_threadpool(learner.get_context_page, owner, limit=20)
            contexts = [row.model_dump(mode='json') for row in rows if row.status != 'ARCHIVED']
        identifiers = [intent.context_id] if intent.context_id else [row['context_id'] for row in contexts[:20]]
        scope = dict(context_ids=identifiers) if identifiers else {}
        calls = [('priorities', 'get_study_recommendations', scope),
                 ('verification', 'get_verification_candidates', scope),
                 ('learner', 'get_relevant_learner_context', dict(query=intent.topic or intent.instructions or 'Choose useful assessment practice', **scope))]
        values = await asyncio.gather(*(tools[name].ainvoke(arguments) for _, name, arguments in calls))
        data = dict(zip((key for key, _, _ in calls), values))
        contexts = [row for row in contexts if row['status'] != 'ARCHIVED']
        allowed = {row['context_id'] for row in contexts}
        if intent.context_id: allowed.add(intent.context_id)
        data['contexts'] = contexts[:20]
        if intent.document_ids and workflows.rag:
            documents = await run_in_threadpool(workflows.rag.assessment_materials, owner, intent.document_ids)
            data['selected_materials'] = [dict(title=value['title'], context_ids=value['context_ids']) for value in documents]
            identifiers = list(dict.fromkeys(identifier for value in documents for identifier in value['context_ids']))
            summaries = await run_in_threadpool(learner.get_context_summaries, owner, identifiers) if identifiers else []
            eligible = [row.model_dump(mode='json') if hasattr(row,'model_dump') else row for row in summaries]
            allowed.update(row['context_id'] for row in eligible if row['status'] != 'ARCHIVED')
            data['material_contexts'] = eligible
        profile = await run_in_threadpool(workflows.profile.prompt_context, owner) if workflows.profile else None
        def validate(result):
            if result.context_id is not None and result.context_id not in allowed:
                raise GenerationMismatch('choose_a_supplied_context_or_null')
            if not result.question_format.strip() or result.question_format == 'auto':
                raise GenerationMismatch('choose_a_concrete_question_format')
        selected = await invoke_generated(workflows.llm, PromptSource.ASSESSMENT_SELECTION,
            dict(request=intent.model_dump(mode='json'), tools=data,
                 profile=profile.model_dump(mode='json') if profile else None),
            output_schema=AssessmentSelection, validate=validate)
        topic = intent.topic or selected.topic
        context_id = intent.context_id or selected.context_id
        if intent.grounded and not intent.context_id and data.get('material_contexts'):
            material_ids = [row['context_id'] for row in data['material_contexts'] if row['status'] != 'ARCHIVED']
            if material_ids and context_id not in material_ids: context_id = material_ids[0]
        kind = selected.question_format if intent.question_format == 'auto' else intent.question_format
        labels = intent.concept_names or (selected.concept_names if not intent.topic else [])
    if context_id is None:
        context = await run_in_threadpool(learner.resolve_learning_context,
            ResolveLearningContextRequest(learner_id=owner, name=topic))
        context_id = context.context_id
    return GenerationRequest.model_validate(dict(intent.model_dump(mode='json'), topic=topic,
        context_id=context_id, question_format=kind, concept_names=labels))
