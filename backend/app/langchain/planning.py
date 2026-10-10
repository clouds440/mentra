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

from app.core.logging import workflow_logger

@workflow_logger.operation(outcome='success')
def plan_request(query: str, *, attachments=False, selected_sources=False):
    text = query.strip().casefold()
    greeting = bool(re.fullmatch(r'(hi|hello|hey|thanks|thank you)[.! ]*', text))
    personal = bool(re.search(r'\b(remember|preference|previous chat|earlier conversation|my profile|saved memory)\b', text))
    event = bool(re.search(r'\b(my|our|i have|schedule|add|upcoming|remind)\b.*\b(exam|quiz|deadline|assignment|event|session)\b|\b(my events|my agenda)\b', text))
    assessment = bool(re.search(r'\b(generate|create|start|grade|take)\b.*\b(assessment|test|practice quiz)\b', text))
    learning = not greeting and not (personal or event) or assessment
    modules = ['chat']
    if personal: modules.extend(['history', 'memory', 'profile'])
    if event: modules.append('events')
    if learning: modules.extend(['learner', 'profile'])
    if selected_sources or learning: modules.append('rag')
    if attachments: modules.append('documents')
    if assessment: modules.append('assessment')
    intent = 'compound' if sum((personal, event, assessment)) > 1 else 'assessment' if assessment else 'events' if event else 'personal' if personal else 'learning' if learning else 'conversation'
    allocation = {'chat':0, 'learner':1800, 'profile':600, 'rag':3200, 'documents':2400, 'history':1500, 'memory':800, 'events':800, 'assessment':0}
    return ExecutionPlan(intent=intent, steps=[ExecutionStep(module=module, required=module == 'documents', token_budget=allocation[module]) for module in dict.fromkeys(modules)], confirmation_required=event)
