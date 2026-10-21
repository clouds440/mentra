"""Small, explicit capability metadata shared by selection and discovery."""
from pydantic import BaseModel, ConfigDict, Field, StrictBool
from app.chat.titles import NewChatReply


DOMAINS = {
    'memory_summary_context': 'memory',
    'web_research': 'web',
    'web_search': 'web',
    'history_lookup': 'history', 'user_memory': 'memory',
    'event_lookup': 'events', 'event_manage': 'events',
    'get_active_learning_contexts': 'learner', 'get_relevant_learner_context': 'learner',
    'get_study_recommendations': 'learner', 'get_verification_candidates': 'learner',
    'resolve_student_concept': 'learner', 'search_study_material': 'rag',
    'get_study_source_chunk': 'rag', 'present_choices': 'chat',
    'assessment_generate': 'assessment', 'assessment_answer': 'assessment',
    'assessment_lookup': 'assessment', 'assessment_revise': 'assessment',
    'assessment_question': 'assessment', 'assessment_status': 'assessment',
}
WRITES = {'event_manage', 'resolve_student_concept', 'present_choices',
          'assessment_generate', 'assessment_revise', 'assessment_answer'}
CAPABILITIES = {
    'web': 'Search current or additional external knowledge when needed; optional website restriction and dated citations.',
    'history': 'Retrieve earlier conversations.', 'memory': 'Recall or propose saved preferences; consent and evidence checks apply.',
    'events': 'Read your agenda or prepare authorized event changes; review may be required.',
    'learner': 'Read learning contexts and ranked practice targets; new concepts require review.',
    'rag': 'Search approved study material and cite returned passages.',
    'assessment': 'Create, revise, discuss, or prepare answers for assessments; grading uses validated jobs.',
    'chat': 'Explain general concepts and present clarification choices.',
}


def is_write(name, arguments):
    return name in WRITES or (name == 'user_memory' and arguments.get('action') != 'recall')


class DirectAnswer(BaseModel):
    """Final answer only when every part is general and needs no tools."""
    model_config = ConfigDict(extra='forbid')
    content: str = Field(min_length=1)
    general_query: StrictBool
    needs_tools: StrictBool
    uncertain: StrictBool


class DirectNewChatReply(NewChatReply):
    """First-turn answer/title plus explicit no-tool eligibility, in one call."""
    general_query: StrictBool
    needs_tools: StrictBool
    uncertain: StrictBool


def approved_direct(response):
    return response.general_query is True and response.needs_tools is False and response.uncertain is False


def catalog(tools, domains):
    available = {}
    for tool in tools:
        domain = domains.get(tool.name)
        if domain:
            available.setdefault(domain, []).append(tool.name)
    return {domain: dict(description=CAPABILITIES.get(domain, domain), tools=names)
            for domain, names in available.items()}
