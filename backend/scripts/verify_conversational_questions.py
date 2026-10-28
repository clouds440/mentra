"""Configured-model checks: synthetic chat questions versus assessment creation.

Uses real chat prompts/tool orchestration, an in-memory assessment stub and no
student database, profile, memory, grading or learner-evidence service.
"""
import asyncio
import json
import logging
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from langchain_core.messages import HumanMessage
from app.core.config import settings
from app.chat.titles import NewChatReply
from app.langchain.history_orchestration import tool_reply
from app.langchain.llm import MentraLLM
from app.langchain.model_factory import ModelFactory
from app.langchain.planning import plan_request


CASES = (
    ("I'm a beginner. I want to learn English. Where do I start? Can you ask me a few options/questions to get started?", False),
    ('Ask me a few questions about my goals before suggesting a learning path.', False),
    ('Give me one ungraded grammar question here in chat; no quiz or saved assessment.', False),
    ('Help me practice English through a conversation, one question at a time.', False),
    ('Can you give me advice about my upcoming test and ask about my goals?', False),
    ('مجھے انگریزی سیکھنی ہے۔ پہلے میرے مقاصد اور دلچسپیوں کے بارے میں چند سوال پوچھیں، کوئی ٹیسٹ نہیں۔', False),
    ('Quiero aprender inglés. Hazme unas preguntas sobre mis objetivos antes de empezar, sin examen.', False),
    ('Create an assessment, but first let me choose between English grammar and vocabulary using options. Wait for my choice before creating it.', False),
    ('Create a one-question quiz on English greetings.', True),
    ('Give me an assessment.', True),
    ('مجھے انگریزی کا ایک سوال کا کوئز دیں', True),
)


async def verify():
    llm = MentraLLM(ModelFactory(settings))
    results = []
    for query, assessment_requested in CASES:
        generated = []

        async def generate(owner, conversation, **arguments):
            generated.append(arguments)
            identifier = str(uuid4())
            return dict(id=identifier, assessment_id=None,
                assessment=dict(id=identifier, title='English greetings quiz', questions=[]))

        scope = dict(current_user_message_id=str(uuid4()), user_sequence=1,
            conversation_id=str(uuid4()), current_answer_text=query, history_references=[],
            memory_references=[], context_rows=[], execution_plan=plan_request(query),
            assessment_service=SimpleNamespace(generate_chat_from_topic=generate))
        reply = await tool_reply(llm, [HumanMessage(content=query)], None, str(uuid4()),
            scope, (), {}, output_schema=NewChatReply)
        result = dict(query=query, expected_assessment=assessment_requested,
            assessment_calls=len(generated), conversational_cards=len(scope.get('interactions', [])),
            nonempty_reply=bool(reply.content.strip()),
            required_outcome=scope['execution_plan'].required_outcome)
        results.append(result)
        assert bool(generated) == assessment_requested and result['nonempty_reply'], result
        if not assessment_requested:
            assert not scope.get('assessment_cards') and not scope.get('_assessment_attempted'), result
    Path('docs/audits/conversational-questions-live-verification.json').write_text(
        json.dumps(dict(model=settings.ai_model, scope='Synthetic prompts and in-memory assessment stub only; no student records.',
            cases=results), ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(f'Passed {len(results)} configured-model conversation/assessment checks.')


if __name__ == '__main__':
    logging.disable(logging.CRITICAL)
    asyncio.run(verify())
