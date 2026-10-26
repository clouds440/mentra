"""Trusted capability metadata; schemas and authorization remain domain-owned."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Capability:
    domain: str
    outcome: str
    tools: tuple[str, ...]
    writes: tuple[str, ...] = ()


CAPABILITIES = (
    Capability('history', 'Find earlier conversations and recover original wording.',
               ('history_lookup', 'conversation_summary_search')),
    Capability('memory', 'Recall relevant preferences or propose evidence-backed saved facts.', ('user_memory',)),
    Capability('learner', 'Read learning progress and practice priorities; resolve topic identity.',
               ('get_active_learning_contexts', 'get_relevant_learner_context', 'get_study_recommendations',
                'get_verification_candidates', 'resolve_student_concept'), ('resolve_student_concept',)),
    Capability('rag', 'Study selected Library material using cited passages.',
               ('search_study_material', 'get_study_source_chunk')),
    Capability('events', 'Read the agenda or prepare authorized schedule changes.',
               ('event_lookup', 'event_manage'), ('event_manage',)),
    Capability('assessment', 'Test understanding with native interactive practice; read, revise, answer or review assessments. Written papers when requested.',
               ('assessment_generate', 'assessment_generate_advanced', 'assessment_lookup', 'assessment_revise', 'assessment_question',
                'assessment_answer', 'assessment_status'),
               ('assessment_generate', 'assessment_generate_advanced', 'assessment_revise', 'assessment_answer')),
    Capability('chat', 'Present clickable clarification choices; explain or draft directly.',
               ('present_choices',), ('present_choices',)),
    Capability('web', 'Verify current external facts or research public sources.', ('web_search', 'web_research')),
)
DOMAINS = {tool: capability.domain for capability in CAPABILITIES for tool in capability.tools}
DOMAINS['memory_summary_context'] = 'memory'
DOMAINS['validate_study_selection'] = 'rag'
WRITES = {tool for capability in CAPABILITIES for tool in capability.writes}
OUTCOMES = {capability.domain: capability.outcome for capability in CAPABILITIES}


def catalog(tools, domains):
    """Only constructed tools appear: metadata never grants unavailable access."""
    available = {}
    for tool in tools:
        domain = domains.get(tool.name)
        if domain:
            available.setdefault(domain, []).append(tool.name)
    return {domain: dict(description=OUTCOMES.get(domain, domain), tools=names)
            for domain, names in available.items()}
