"""Live configured-provider checks on synthetic, ungraded questionnaires only."""
import asyncio
import json
import logging
from pathlib import Path
from uuid import uuid4
from langchain_core.messages import HumanMessage
from app.core.config import settings
from app.chat.titles import NewChatReply
from app.langchain.llm import MentraLLM
from app.langchain.model_factory import ModelFactory
from app.langchain.history_orchestration import tool_reply
from app.langchain.planning import plan_request


async def main():
    llm = MentraLLM(ModelFactory(settings))
    results = []
    for query in (
        'Ask me five getting-started questions about learning English, with four options each. Let me answer all five together before suggesting a plan. This is a conversation about preferences, not an assessment.',
        'انگریزی سیکھنے کے لیے میرے مقاصد اور ترجیحات کے بارے میں پانچ سوال پوچھیں، ہر سوال کے چار اختیارات ہوں۔ سب کے جواب ایک ساتھ بھیجنا چاہتا ہوں، کوئی ٹیسٹ نہیں۔',
    ):
        scope = dict(current_user_message_id=str(uuid4()), conversation_id=str(uuid4()), user_sequence=1,
            current_answer_text=query, history_references=[], memory_references=[], context_rows=[], execution_plan=plan_request(query))
        reply = await tool_reply(llm, [HumanMessage(content=query)], None, str(uuid4()), scope, (), {}, output_schema=NewChatReply)
        cards = scope.get('interactions', [])
        assert len(cards) == 1 and cards[0]['kind'] == 'questionnaire', cards
        questions = cards[0]['questions']
        assert len(questions) == 5 and all(len(q.get('options', [])) == 4 for q in questions), questions
        assert not scope.get('assessment_cards') and not scope.get('tool_warnings') and reply.content.strip()
        results.append(dict(question_count=len(questions), options_per_question=[len(q['options']) for q in questions],
            grouped_card_count=len(cards), domain_writes=scope['_tool_budget'].writes, question_ids=[q['id'] for q in questions]))
    Path('docs/audits/chat-questionnaire-provider-verification.json').write_text(json.dumps(dict(
        model=settings.ai_model, scope='Synthetic English and Urdu prompts; no student database, assessments or grading services.',
        cases=results), ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print('Both configured-model cases preserved all five questions and all four options in one questionnaire.')


if __name__ == '__main__':
    logging.disable(logging.CRITICAL)
    asyncio.run(main())
