"""Validated execution allocation. Tool selection remains model-driven."""
import re
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

Module = Literal['chat', 'learner', 'rag', 'documents', 'history', 'memory', 'profile', 'events', 'assessment']

class ExecutionStep(BaseModel):
    model_config = ConfigDict(extra='forbid')
    module: Module
    required: bool = False
    token_budget: int = Field(ge=0, le=12000)

class ExecutionPlan(BaseModel):
    model_config = ConfigDict(extra='forbid')
    intent: Literal['conversation', 'learning', 'personal', 'events', 'assessment', 'compound']
    steps: list[ExecutionStep] = Field(min_length=1, max_length=9)
    deadline_seconds: int = Field(default=150, ge=1, le=150)
    evidence_eligible: bool = False
    confirmation_required: bool = False
    direct_candidate: bool = False
    capabilities_query: bool = False
    tool_names: list[str] = Field(default_factory=list)


def general_query(query):
    """Conservative eligibility only; the answer model must approve separately."""
    text = query.strip().casefold()
    if re.fullmatch(r'(hi|hello|hey|thanks|thank you)[.! ]*', text):
        return True
    if re.fullmatch(r'(what can you do|how can you help(?: me)?|what are your capabilities|what can mentra do)[?!. ]*', text):
        return True
    if re.search(r'\b(my|our|mine|remember|previous|earlier|today|current|latest|tomorrow|now|upload|attached|file|document|notes|quote|source|according|based|textbook|passage|chapter|lesson|this|that|it|these|those|quiz|test|assessment|event|agenda|schedule|remind|grade|evaluate|create|save|add|change|harder|easier|health|price|weather|news|law|medical|dose|dosing)\b', text):
        return False
    return bool(re.match(r'^(explain|define|what is|what are|how does|why does|describe)\s+\S', text))


def direct_content_safe(content):
    # A no-tool answer cannot promise an action, invent a citation, or claim a
    # retrieved personal/current fact. This is an additional guard, not certainty.
    return not bool(re.search(r'\[\[(?:S|H|M|W)\d+\]\]|\b(?:your (?:mastery|assessment|exam|event|profile|notes)|I (?:saved|created|scheduled|retrieved|checked|graded|searched|browsed)|currently available|as of today)\b', content, re.I))

from app.core.logging import workflow_logger

@workflow_logger.operation(outcome='success')
def plan_request(query: str, *, attachments=False, selected_sources=False, context_rows=()):
    text = query.strip().casefold()
    greeting = bool(re.fullmatch(r'(hi|hello|hey|thanks|thank you)[.! ]*', text))
    personal = bool(re.search(r'\b(remember|preference|previous chat|earlier conversation|my profile|saved memory)\b', text))
    event = bool(re.search(r'\b(agenda|deadline|remind|upcoming|schedule|event)\b|\bwhen\b.*\bexam\b', text))
    assessment = bool(re.search(r'\b(assessment|quiz|mock paper|mock exam|answer sheet|test)\b|\b(grade|evaluate|mark)\b.*\b(answers?|paper)\b', text))
    recent = next((row.get('metadata', {}) for row in reversed(context_rows) if row.get('role') == 'assistant'), {})
    if re.search(r'\b(harder|easier|revise|change|question|answers?|it|that)\b', text) and recent.get('assessment_cards'):
        assessment = True
    if re.search(r'\b(it|that|move|reschedule)\b', text) and recent.get('event_references'):
        event = True
    study = bool(re.search(r'\b(explain|learn|study|understand|solve|revise|practice|concept|algebra|calculus)\b', text))
    capability = bool(re.fullmatch(r'(what can you do|how can you help(?: me)?|what are your capabilities|what can mentra do)[?!. ]*', text))
    direct = general_query(query) and not assessment and not personal and not event and not selected_sources and not attachments
    learning = not direct and (assessment or study or bool(re.search(r'\b(progress|weakness|mastery|learning context)\b', text)))
    # The learner's chosen form of address is available even for simple greetings.
    modules = ['chat', 'profile']
    if personal: modules.extend(['history', 'memory', 'profile'])
    if event: modules.append('events')
    if learning: modules.extend(['learner', 'profile'])
    source_request = bool(re.search(r'\b(file|document|notes|source|attached|uploaded|passage|quote|library)\b', text))
    if (selected_sources and not direct) or source_request: modules.append('rag')
    if attachments and not direct: modules.append('documents')
    if assessment: modules.append('assessment')
    intent = 'compound' if sum((personal, event, assessment)) > 1 else 'assessment' if assessment else 'events' if event else 'personal' if personal else 'learning' if learning else 'conversation'
    allocation = {'chat':0, 'learner':1800, 'profile':600, 'rag':3200, 'documents':2400, 'history':1500, 'memory':800, 'events':800, 'assessment':0}
    names = []
    if personal: names.extend(['history_lookup', 'user_memory'])
    if event: names.append('event_manage' if re.search(r'\b(add|create|schedule|remind|move|reschedule|cancel)\b', text) else 'event_lookup')
    if learning: names.extend(['get_active_learning_contexts', 'get_relevant_learner_context'])
    if re.search(r'\b(next|weakness|progress|practice target|recommend)\b', text) and learning: names.append('get_study_recommendations')
    if 'rag' in modules: names.append('search_study_material')
    if assessment:
        if re.search(r'\b(harder|easier|revise|change)\b', text): names.extend(['assessment_lookup', 'assessment_revise'])
        elif re.search(r'\b(grade|evaluate|mark|submit|answers?)\b', text): names.extend(['assessment_lookup', 'assessment_answer'])
        elif re.search(r'\b(generate|create|give|build|prepare|make|want|need)\b|\b(?:quiz|test) me\b', text): names.append('assessment_generate')
        elif re.search(r'\b(question|status|progress|explain)\b', text): names.extend(['assessment_lookup', 'assessment_question', 'assessment_status'])
        else: names.extend(['get_active_learning_contexts', 'assessment_generate'])
    return ExecutionPlan(intent=intent, steps=[ExecutionStep(module=module, required=module in ('documents', 'rag') and (source_request or selected_sources or attachments), token_budget=allocation[module]) for module in dict.fromkeys(modules)], confirmation_required=event, direct_candidate=direct, capabilities_query=capability, tool_names=list(dict.fromkeys(names)))
