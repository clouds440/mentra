"""Disposable PostgreSQL migration/10,000-subskill check; never uses DATABASE_URL."""
import json
import statistics
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from sqlalchemy import select, func
from alembic import command
from app.db.migrate import migration_config
from app.learner.engine import LearnerEngine
from app.learner.schemas import ResolveLearningContextRequest, LearningProgressRequest
from app.learner.topics import TopicPlacement
from app.learner.models import Concept
from app.learner.repositories.tables import concept, context_concept
from app.learner.repositories.tables.topics import topic_skill
from app.auth.repositories.tables import learner
from testing.postgres import PostgresSandbox
from testing.identities import learner_id


def main():
    with PostgresSandbox() as db:
        with db.engine.connect() as connection:
            before = connection.scalar(select(func.count()).select_from(learner))
            connection.commit()
            command.downgrade(migration_config(connection), '20261025_0031')
            command.upgrade(migration_config(connection), 'head')
            assert connection.scalar(select(func.count()).select_from(learner)) == before
            connection.commit()
        engine = LearnerEngine(db.repository)
        owner = learner_id('alice')
        context = engine.resolve_learning_context(ResolveLearningContextRequest(learner_id=owner,
            name='Synthetic large collection', activate=True)).context_id
        first = Concept(str(uuid4()), 'synthetic-first')
        with db.repository.transaction(learner_ids=[owner]) as repository:
            repository.create_concept(first)
            topic_id = repository.save_topic_membership(owner, context, first.id, TopicPlacement(
                label='Synthetic skill 0000', action='create_concept', topic_name='Synthetic large topic',
                scope='Storage/query scalability fixture, not a real educational taxonomy.', ability='Synthetic ability'), published=True)
            repository.add_context_concept(context, first.id, learner_id=owner)
        ids = [(str(uuid4()), index) for index in range(1, 10000)]
        with db.engine.begin() as connection:
            connection.execute(concept.insert(), [dict(id=identifier, canonical_name=f'synthetic-{index:04}',
                normalized_name=f'synthetic-{index:04}') for identifier, index in ids])
            connection.execute(context_concept.insert(), [dict(learner_id=owner, context_id=context,
                concept_id=identifier) for identifier, _ in ids])
            connection.execute(topic_skill.insert(), [dict(learner_id=owner, concept_id=identifier, topic_id=topic_id,
                label=f'Synthetic skill {index:04}', ability='Synthetic ability', published=True,
                phrases=f'\nsynthetic skill {index:04}\n', resolver_version='storage-fixture') for identifier, index in ids])
        timings = []
        for _ in range(5):
            start = perf_counter()
            with engine.read_scope() as scoped:
                page = scoped.get_learning_topics(LearningProgressRequest(learner_id=owner,
                    context_ids=[context], query='9999'))
            timings.append((perf_counter() - start) * 1000)
            assert page.total == 1 and page.items[0].subskill_count == 10000
            assert page.items[0].matching_skills == ['Synthetic skill 9999']
        children = engine.get_topic_subskills(LearningProgressRequest(learner_id=owner,
            context_ids=[context], limit=10, offset=9990), topic_id)
        assert children.total == 10000 and len(children.items) == 10
        assert children.items[-1].name == 'Synthetic skill 9999'
        candidates = db.repository.topic_candidates(owner, context, 'Synthetic skill 9999')
        assert len(candidates) <= 12 and all(len(row['subskills']) <= 5 for row in candidates)
        assert any(skill['label'] == 'Synthetic skill 9999' for row in candidates for skill in row['subskills'])
        report = dict(scope='Dedicated disposable PostgreSQL schema; synthetic data only.',
            upgrade_downgrade_reupgrade_preserves_learners=True, subskills=10000,
            grouped_search_ms=timings, median_ms=statistics.median(timings), max_ms=max(timings),
            topic_payload_bytes=len(page.model_dump_json().encode()), detail_page_items=len(children.items),
            candidate_topics=len(candidates), max_candidate_subskills=max(len(row['subskills']) for row in candidates))
        Path('docs/audits/topic-storage-verification.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
