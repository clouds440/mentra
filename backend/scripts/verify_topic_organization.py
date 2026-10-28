"""Configured-provider checks using synthetic subjects, never student records."""
import asyncio
import json
from pathlib import Path
from uuid import uuid4

from app.core.config import settings
from app.langchain.llm import MentraLLM
from app.langchain.model_factory import ModelFactory
from app.langchain.concept_identity import ConceptIdentityResolver


async def main():
    resolver = ConceptIdentityResolver(MentraLLM(ModelFactory(settings)))
    labels = ['Inner joins', 'Left outer joins', 'Right outer joins', 'Full outer joins', 'Self joins', 'Cross joins']
    first = await asyncio.wait_for(resolver.organize(labels, 'SQL joins', 'Relational databases', [], {}), 90)
    assert len(first.placements) == len(labels)
    assert {p.label for p in first.placements} == set(labels)
    assert all(p.action == 'create_concept' and not p.topic_id and not p.skill_id for p in first.placements)
    assert len({p.topic_name.casefold() for p in first.placements}) == 1, 'A coherent six-skill topic fragmented'
    topic = dict(id=str(uuid4()), name=first.placements[0].topic_name, scope=first.placements[0].scope,
        subskills=[dict(concept_id=str(uuid4()), label=p.skill_name or p.label, ability=p.ability) for p in first.placements])
    second = await asyncio.wait_for(resolver.organize(['Keep every row from the left table, including unmatched ones'],
        'SQL joins', 'Relational databases', [topic], {}), 90)
    assert second.placements[0].action == 'reuse'
    expected = next(skill['concept_id'] for skill in topic['subskills'] if 'left' in skill['label'].casefold())
    assert second.placements[0].skill_id == expected
    assert second.placements[0].topic_id == topic['id']
    third = await asyncio.wait_for(resolver.organize(['Chain rule', 'Product rule'],
        'Differentiation rules', 'Calculus', [topic], {}), 90)
    assert all(p.action == 'create_concept' for p in third.placements), 'Unrelated skills were forced into SQL joins'
    result = dict(model=settings.ai_model, scope='Synthetic provider/domain checks; no real student data.',
        natural_six_skill_group=first.model_dump(mode='json'), repeated_niche=second.model_dump(mode='json'),
        different_subject=third.model_dump(mode='json'))
    path = Path('docs/audits/topic-organization-live-verification.json')
    path.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print('Passed: natural six-skill grouping, paraphrase reuse, different-subject separation.')


if __name__ == '__main__':
    asyncio.run(main())
