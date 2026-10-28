"""Validated execution allocation. Tool selection remains model-driven."""
import re
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

Module = Literal['chat', 'learner', 'rag', 'documents', 'history', 'memory', 'profile', 'events', 'assessment', 'web']

class ExecutionStep(BaseModel):
    model_config = ConfigDict(extra='forbid')
    module: Module
    required: bool = False
    token_budget: int = Field(ge=0, le=12000)

class ExecutionPlan(BaseModel):
    model_config = ConfigDict(extra='forbid')
    intent: Literal['conversation', 'learning', 'personal', 'events', 'assessment', 'compound']
    steps: list[ExecutionStep] = Field(min_length=1, max_length=10)
    deadline_seconds: int = Field(default=150, ge=1, le=150)
    evidence_eligible: bool = False
    confirmation_required: bool = False
    direct_candidate: bool = False
    capabilities_query: bool = False
    tool_names: list[str] = Field(default_factory=list)
    required_outcome: Literal['assessment'] | None = None
    required_domains: list[Literal['events', 'memory', 'history', 'rag', 'web']] = Field(default_factory=list)
    edit_source_id: str | None = None
    assessment_edit: bool = False


def general_query(query):
    """Conservative eligibility only; the answer model must approve separately."""
    text = query.strip().casefold()
    from .request_intent import supplied_content_task
    if supplied_content_task(query):
        return True
    if re.fullmatch(r'(hi|hello|hey|thanks|thank you)[.! ]*', text):
        return True
    if re.fullmatch(r'(what can you do|how can you help(?: me)?|what are your capabilities|what can mentra do)[?!. ]*', text):
        return True
    if re.search(r'\b(my|our|mine|remember|previous|earlier|today|current|latest|tomorrow|now|upload|attached|file|document|notes|quote|source|according|based|textbook|passage|chapter|lesson|this|that|it|these|those|remind|harder|easier|health|price|weather|news|law|medical|dose|dosing)\b|\band\s+(?:create|save|add|change|schedule|quiz|test|grade|evaluate)\b', text):
        return False
    return bool(re.match(r'^(explain|define|what is|what are|what does|how does|how do|how can i|how to|why does|why do|describe)\s+\S', text))


def direct_content_safe(content):
    # A no-tool answer cannot promise an action, invent a citation, or claim a
    # retrieved personal/current fact. This is an additional guard, not certainty.
    public_prose = re.sub(r'(?ms)^(`{3,}|~{3,})[^\n]*\n.*?^\1[ \t]*(?:\n|$)', '', content)
    return not bool(re.search(r'\[\[(?:S|H|M|W)\d+\]\]|\b(?:your (?:mastery|assessment|exam|event|profile|notes)|I (?:saved|created|scheduled|retrieved|checked|graded|searched|browsed)|currently available|as of today)\b', public_prose, re.I))


def fulfills_domain_attempt(plan, domain, tool_name, arguments, query):
    """Completion needs the requested operation, not merely a nearby domain read."""
    if domain not in getattr(plan, 'required_domains', []):
        return True
    if domain == 'web':
        return tool_name in ('web_search', 'web_research')
    if tool_name not in getattr(plan, 'tool_names', []):
        return False
    if domain == 'memory':
        writing = bool(re.search(r'\b(?:remember (?:that|my|this preference|i|we)|save|store)\b', query, re.I))
        return not writing or arguments.get('action', 'recall') != 'recall'
    return True

from app.core.logging import workflow_logger

@workflow_logger.operation(outcome='success')
def plan_request(query: str, *, attachments=False, selected_sources=False, context_rows=()):
    text = query.strip().casefold()
    history = bool(re.search(r'\b(?:past|previous|earlier|last) (?:chat|conversation|message)s?\b|\b(?:where|when) did we (?:discuss|talk)|\bwhat (?:did i (?:say|ask)|we discussed)\b', text))
    memory = bool(re.search(r'\b(?:my preferences?|saved preferences?|my profile|saved memor(?:y|ies))\b|\bwhat do you (?:know|remember) about me\b|\b(?:please )?remember (?:that|my|this preference|i|we)\b|\b(?:save|store)\b.*\b(?:preference|fact|goal|memory)\b', text)) and not history
    personal = history or memory
    event = bool(re.search(r'\b(agenda|deadline|remind|upcoming|schedule|event)\b|\bwhen\b.*\bexam\b', text))
    from .request_intent import practice_request, assessment_mentioned, web_request, supplied_content_task
    requested_practice = practice_request(query)
    assessment = requested_practice or bool(re.search(r'\b(grade|evaluate|mark)\b.*\b(answers?|paper)\b', text))
    if assessment_mentioned(text) and re.search(
            r'\b(?:show|open|review|submit|resume|status|results?)\b.*\b(?:my|the|this|that|previous|last)\b|'
            r'\b(?:my|this|that|previous|last) (?:assessment|quiz|test|answer sheet)\b', text):
        assessment = True
    from app.history_management.events.capture import event_candidate
    scheduled = event_candidate(query)
    if scheduled:
        event = True
        assessment = assessment and requested_practice
    recent = next((row.get('metadata', {}) for row in reversed(context_rows) if row.get('role') == 'assistant'), {})
    assessment_edit = bool(recent.get('assessment_cards') and re.match(r'^(?:and\s+)?(?:please\s+|(?:can|could|would) you\s+)?(?:harder|easier|revise|change|make|edit|update|replace|rewrite|shorten|simplify)\b', text)
                           and re.search(r'\b(?:it|this|that|assessment|quiz|test|questions?|harder|easier)\b', text[:120])
                           and not re.search(r'\b(?:new|another|different) (?:assessment|quiz|test|paper)\b', text))
    if assessment_edit or recent.get('assessment_cards') and re.search(
            r'\b(?:this|that|the|my|previous|last|current) (?:assessment|quiz|test|question|answer)\b|'
            r'\b(?:question|answer) (?:number )?\d+\b|^(?:my )?answer(?: is|:)', text):
        assessment = True
    if re.search(r'\b(it|that|move|reschedule)\b', text) and recent.get('event_references'):
        event = True
    capability = bool(re.fullmatch(r'(what can you do|how can you help(?: me)?|what are your capabilities|what can mentra do)[?!. ]*', text))
    from .request_intent import response_edit_source
    edit_source = response_edit_source(query, context_rows) if not attachments else None
    direct = bool(edit_source) or (general_query(query) and not selected_sources and not attachments
                                  and (supplied_content_task(query) or not requested_practice))
    if direct:
        assessment = personal = history = memory = event = scheduled = requested_practice = False
    # Assessment workflows resolve their own targets. Do not prefetch broad
    # learner packets and bind four redundant reads before generation begins.
    learning = not direct and not assessment and bool(re.search(
        r'\b(?:progress|weakness(?:es)?|mastery|learning context|recommend(?:ation)?|what should i (?:study|learn)|what (?:should i (?:do|practice) )?next)\b', text))
    # The learner's chosen form of address is available even for simple greetings.
    modules = ['chat', 'profile']
    if personal: modules.extend(['history', 'memory', 'profile'])
    if event: modules.append('events')
    if learning: modules.extend(['learner', 'profile'])
    explicit_web = bool(re.search(r'\b(?:search (?:the )?(?:web|internet)|browse|research)\b|https?://', text))
    source_request = bool(re.search(r'\b(file|document|notes|source|attached|uploaded|passage|quote|library)\b', text))
    source_request = source_request and (not explicit_web or bool(re.search(r'\b(?:my|our|library|uploaded|attached)\b', text)))
    if not direct and (selected_sources or source_request): modules.append('rag')
    if attachments and not direct: modules.append('documents')
    if assessment: modules.append('assessment')
    external = not direct and web_request(text) and (explicit_web or not (personal or learning or event or source_request))
    if external: modules.append('web')
    intent = 'compound' if sum((personal, event, assessment)) > 1 else 'assessment' if assessment else 'events' if event else 'personal' if personal else 'learning' if learning else 'conversation'
    allocation = {'chat':0, 'learner':1800, 'profile':600, 'rag':3200, 'documents':2400, 'history':1500, 'memory':800, 'events':800, 'assessment':0, 'web':0}
    names = []
    if memory: names.append('user_memory')
    if history:
        if re.search(r'\b(?:chats?|conversations?)\b|\bwhere did we\b', text):
            names.append('conversation_summary_search')
        names.append('history_lookup')
    if event: names.append('event_manage' if scheduled or re.search(r'\b(add|create|schedule|remind|move|reschedule|cancel)\b', text) else 'event_lookup')
    if learning: names.append('get_relevant_learner_context')
    if re.search(r'\b(next|weakness(?:es)?|practice target|recommend)\b', text) and learning: names.append('get_study_recommendations')
    if 'rag' in modules: names.append('search_study_material')
    if external: names.append('web_research' if re.search(r'\b(research|in.depth|multi.source)\b', text) else 'web_search')
    if assessment:
        if assessment_edit: names.append('assessment_revise')
        elif re.search(r'\b(harder|easier|revise|change)\b', text): names.extend(['assessment_lookup', 'assessment_revise'])
        elif requested_practice:
            names.append('assessment_generate_advanced' if re.search(r'\b(?:paper|sections?|parts?|marks?|minutes?|duration)\b', text) else 'assessment_generate')
        elif re.search(r'\b(grade|evaluate|mark|submit|answers?)\b', text): names.extend(['assessment_lookup', 'assessment_answer'])
        elif re.search(r'\b(question|status|progress|explain)\b', text): names.extend(['assessment_lookup', 'assessment_question', 'assessment_status'])
        else: names.append('assessment_lookup')
    required_domains = []
    if external: required_domains.append('web')
    if event and (not scheduled or re.search(r'\b(?:remind|add|create|schedule|reschedule|move)\b', text)):
        required_domains.append('events')
    if memory and re.search(r'\b(?:remember|save|store|search|find)\b', text): required_domains.append('memory')
    if history and re.search(r'\bwhere did we\b|\b(?:find|search|look up)\b', text): required_domains.append('history')
    if not assessment and not attachments and not direct and (selected_sources or source_request):
        required_domains.append('rag')
    plan = ExecutionPlan(intent=intent, steps=[ExecutionStep(module=module, required=module in ('documents', 'rag') and (source_request or selected_sources or attachments), token_budget=allocation[module]) for module in dict.fromkeys(modules)], confirmation_required=event, direct_candidate=direct and not external, capabilities_query=capability, tool_names=list(dict.fromkeys(names)), required_outcome='assessment' if requested_practice else None, required_domains=required_domains, edit_source_id=str(edit_source['id']) if edit_source and edit_source.get('id') else None)
    plan.assessment_edit = assessment_edit and assessment and not direct
    if plan.assessment_edit:
        plan.required_outcome = 'assessment'
    workflow_logger.event('routing.plan', intent=plan.intent, tool_names=plan.tool_names,
                          required_outcome=plan.required_outcome, required_domains=required_domains,
                          preparation_modules=[step.module for step in plan.steps])
    return plan
