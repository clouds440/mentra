"""Configured-model routing checks on synthetic paused requests only."""
import asyncio
import json
from pathlib import Path
from app.core.config import settings
from app.langchain.llm import MentraLLM
from app.langchain.model_factory import ModelFactory
from app.langchain.response_continuation import is_continuation


async def main():
    llm = MentraLLM(ModelFactory(settings))
    original = 'Create twelve practice questions about SQL joins.'
    cases = [('continue', 'continue'), ('Make the questions a little harder.', 'change'),
             ('Actually explain differential equations instead.', 'new'),
             ('انہی سوالات کو تھوڑا آسان کر دو', 'change'), ('تابع من حيث توقفت', 'continue'),
             ('My corrected answer to question one is LEFT JOIN.', 'new'),
             ('I always confuse inner and outer joins.', 'new')]
    results = []
    for message, expected in cases:
        actual = await is_continuation(llm, original, message)
        results.append(dict(message=message, expected=expected, actual=actual))
        assert actual == expected, results[-1]
    Path('docs/chat/verification/response-continuation-live-verification.json').write_text(
        json.dumps(dict(model=settings.ai_model, scope='Synthetic messages only; no student records.', cases=results),
                   ensure_ascii=False, indent=2), encoding='utf-8')
    print('Passed seven continuation/new-request checks, including multilingual changes and new learner statements.')


if __name__ == '__main__': asyncio.run(main())
