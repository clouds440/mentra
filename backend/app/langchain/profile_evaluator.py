"""Specialized structured evaluator, using Mentra's configured model factory."""
import logging
from app.student_profile.schemas import AIEvaluation, DIMENSIONS
from app.student_profile.policy import dimension_items
from app.student_profile.errors import EvaluationUnavailable
from .llm import MentraLLM
from .prompts import PromptSource, get_prompt_version

logger = logging.getLogger('mentra')
PROMPT_VERSION = get_prompt_version(PromptSource.STUDENT_PROFILE_EVALUATION)


def evaluation_payload(evidence, context):
    return {
        'prompt_version': PROMPT_VERSION,
        'profile_context': context.model_dump(mode='json'),
        'assessment_context': evidence.details_snapshot.model_dump(mode='json'),
        'source_type': evidence.input.source_type,
        'reliability': min(evidence.input.reliability, .35) if evidence.input.source_type == 'interaction' else evidence.input.reliability,
        'occurred_at': evidence.input.occurred_at.isoformat(),
        'items': [item.model_dump(mode='json') for item in evidence.input.items],
        'deterministic_dimensions': {dimension: {
            'item_ids': [item.id for item in dimension_items(evidence, dimension)],
            'correct': sum(item.correct for item in dimension_items(evidence, dimension)),
            'total': len(dimension_items(evidence, dimension)),
        } for dimension in DIMENSIONS},
    }


class LangChainProfileEvaluator:
    def __init__(self, llm):
        self.llm = llm if isinstance(llm, MentraLLM) else MentraLLM(llm)

    async def evaluate(self, evidence, context):
        import json
        try:
            # The same MentraLLM component routes by this fixed, server-owned source.
            return await self.llm.ainvoke(PromptSource.STUDENT_PROFILE_EVALUATION,
                evaluation_payload(evidence, context), output_schema=AIEvaluation)
        except Exception as exc:
            # Intentional provider/parser boundary. Never expose provider internals,
            # arbitrary generated text, or partial estimates to the client.
            logger.warning('Student profile evaluation unavailable (%s).', type(exc).__name__)
            raise EvaluationUnavailable('Profile evaluation is temporarily unavailable') from exc
