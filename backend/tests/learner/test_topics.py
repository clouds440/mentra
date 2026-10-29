"""Topic grouping preserves skill identity, ownership and independent evidence."""
import unittest
from datetime import datetime, timedelta, timezone

from app.learner.engine import LearnerEngine
from app.learner.schemas import GeneratedConceptsRequest, LearningProgressRequest, ResolveLearningContextRequest
from app.learner.topics import TopicOrganization, TopicPlacement
from app.learner.models import LearnerConceptState, LearningEvidence
from app.learner.scoring.mastery import HeuristicMasteryPolicy
from app.learner.scoring.signals import performance_estimate
from testing.postgres import PostgresSandbox
from testing.identities import learner_id


class Resolver:
    def __init__(self):
        self.calls = 0

    async def organize(self, labels, topic, context, candidates, existing):
        self.calls += 1
        parent = candidates[0] if candidates else None
        return TopicOrganization(placements=[TopicPlacement(label=label, skill_name=label,
            action='add_subskill' if parent else 'create_concept', topic_id=parent['id'] if parent else None,
            topic_name='Differentiation rules', scope='Rules for differentiating functions; excludes integration.',
            ability='Apply ' + label) for label in labels])


class TopicTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.db = PostgresSandbox()
        self.addCleanup(self.db.close)
        self.owner = learner_id('alice')
        self.resolver = Resolver()
        self.engine = LearnerEngine(self.db.repository, generated_concept_resolver=self.resolver)
        self.context = self.engine.resolve_learning_context(ResolveLearningContextRequest(
            learner_id=self.owner, name='Calculus', activate=True)).context_id

    def request(self, labels):
        return GeneratedConceptsRequest(learner_id=self.owner, context_id=self.context,
            topic='Differentiation', labels=labels)

    def page_request(self, **extra):
        return LearningProgressRequest(learner_id=self.owner, context_ids=[self.context], **extra)

    async def test_batch_bindings_keep_original_labels_after_renaming_and_reordering(self):
        async def organize(labels, topic, context, candidates, existing):
            self.resolver.calls+=1
            return TopicOrganization(placements=[TopicPlacement(label=label,skill_name='Chain rule',
                action='create_concept',topic_name='Differentiation rules',scope='Derivative composition rules.',
                ability='Differentiate a composition.') for label in reversed(labels)])
        self.resolver.organize=organize
        request=self.request(['Differentiate a composite function','Chain rule for nested functions'])
        bindings=await self.engine.resolve_generated_concept_labels(request)
        self.assertEqual(set(bindings),set(request.labels))
        self.assertEqual(len(set(bindings.values())),1)
        self.assertEqual(self.resolver.calls,1)
        repeated=await self.engine.resolve_generated_concept_labels(request)
        self.assertEqual(repeated,bindings)
        self.assertEqual(self.resolver.calls,1)  # No per-label or repeat model calls.
        self.assertEqual(self.db.repository.list_evidence(self.owner,next(iter(bindings.values()))),[])

    async def test_subject_binding_does_not_reuse_an_excluded_subject(self):
        await self.engine.resolve_generated_concepts(self.request(['Chain rule']))
        # The old token-subset shortcut saw "integration" in "excludes
        # integration" and incorrectly accepted it as the same subject.
        known=self.db.repository.known_topic_labels(self.owner,self.context,['Chain rule'],'Integration')
        self.assertEqual(known,{})

    async def test_wider_lookup_actually_expands_children_not_only_parent_count(self):
        labels=[f'Rule {i}' for i in range(10)]
        await self.engine.resolve_generated_concepts(self.request(labels))
        narrow=self.db.repository.topic_candidates(self.owner,self.context,'Differentiation',12)
        wide=self.db.repository.topic_candidates(self.owner,self.context,'Differentiation',24)
        self.assertEqual(len(narrow[0]['subskills']),5)
        self.assertTrue(narrow[0]['subskills_truncated'])
        self.assertEqual(len(wide[0]['subskills']),10)
        self.assertFalse(wide[0]['subskills_truncated'])

    async def test_compact_reuse_does_not_require_repeated_topic_descriptions(self):
        first=await self.engine.resolve_generated_concepts(self.request(['Chain rule']))
        membership=self.engine.get_skill_topics(self.owner,[first[0].id])[first[0].id]
        async def reuse(labels, topic, context, candidates, existing):
            self.resolver.calls+=1
            return TopicOrganization(placements=[TopicPlacement(label=labels[0],action='reuse',
                skill_id=first[0].id,topic_id=membership['topic_id'])])
        self.resolver.organize=reuse
        translated=await self.engine.resolve_generated_concept_labels(self.request(['Composite differentiation']))
        self.assertEqual(translated['Composite differentiation'],first[0].id)
        after=self.engine.get_skill_topics(self.owner,[first[0].id])[first[0].id]
        self.assertEqual(after['ability'],membership['ability'])
        self.assertEqual(after['scope'],membership['scope'])

    async def test_accepted_bindings_remain_owner_context_and_identity_scoped(self):
        first=await self.engine.resolve_generated_concepts(self.request(['Chain rule']))
        other=self.engine.resolve_learning_context(ResolveLearningContextRequest(
            learner_id=self.owner,name='Other subject')).context_id
        self.assertEqual(self.db.repository.known_topic_labels(self.owner,other,['Chain rule'],'Differentiation'),{})
        self.assertEqual(self.db.repository.known_topic_labels(learner_id('bob'),self.context,['Chain rule'],'Differentiation'),{})
        second=await self.engine.resolve_generated_concepts(self.request(['Product rule']))
        from app.learner.exceptions import LearnerError
        with self.assertRaises(LearnerError):
            with self.db.repository.transaction(learner_ids=[self.owner]) as repository:
                repository.save_skill_resolution_bindings(self.owner,self.context,'Differentiation',{'Chain rule':second[0].id})
        known=self.db.repository.known_topic_labels(self.owner,self.context,['Chain rule'],'Differentiation')
        self.assertEqual(known['Chain rule'].id,first[0].id)

    async def test_missing_candidate_can_request_bounded_synonym_lookup(self):
        from unittest.mock import patch
        first=await self.engine.resolve_generated_concepts(self.request(['Chain rule']))
        membership=self.engine.get_skill_topics(self.owner,[first[0].id])[first[0].id]
        count=0
        async def organize(labels, topic, context, candidates, existing):
            nonlocal count
            count+=1
            if count==1:
                return TopicOrganization(placements=[],needs_wider_lookup=True,search_terms=['chain rule'])
            return TopicOrganization(placements=[TopicPlacement(label=labels[0],action='reuse',
                skill_id=first[0].id,topic_id=membership['topic_id'])])
        self.resolver.organize=organize
        with patch.object(self.db.repository,'topic_candidates',wraps=self.db.repository.topic_candidates) as search:
            result=await self.engine.resolve_generated_concept_labels(self.request(['Composite derivative']))
        self.assertEqual(result['Composite derivative'],first[0].id)
        self.assertEqual(count,2)
        self.assertTrue(search.call_args_list[1].args[2].startswith('chain rule '))
        self.assertEqual(search.call_args_list[1].args[3],24)

    async def test_thousand_skill_topic_keeps_lookup_bounded_and_repeats_model_free(self):
        from sqlalchemy import insert
        from unittest.mock import patch
        from app.learner.repositories.tables import concept
        from app.learner.repositories.tables.topics import topic_skill
        first=await self.engine.resolve_generated_concepts(self.request(['Chain rule']))
        parent=self.engine.get_skill_topics(self.owner,[first[0].id])[first[0].id]['topic_id']
        with self.db.sessions.begin() as session:
            session.execute(insert(concept),[dict(id=f'load-{i}',canonical_name=f'Load skill {i}',normalized_name=f'load skill {i}') for i in range(1000)])
            session.execute(insert(topic_skill),[dict(learner_id=self.owner,concept_id=f'load-{i}',topic_id=parent,
                label=f'Load skill {i}',ability='A synthetic ability.',phrases=f'\nload skill {i}\n',resolver_version='test') for i in range(1000)])
        narrow=self.db.repository.topic_candidates(self.owner,self.context,'load skill 999',12)
        wide=self.db.repository.topic_candidates(self.owner,self.context,'load skill 999',24)
        self.assertEqual(len(narrow[0]['subskills']),5)
        self.assertEqual(len(wide[0]['subskills']),12)
        self.assertIn('load-999',{item['concept_id'] for item in narrow[0]['subskills']})
        count=self.resolver.calls
        with patch.object(self.db.repository,'topic_registry_version',side_effect=AssertionError('Exact reuse must not scan registry versions')):
            repeated=await self.engine.resolve_generated_concepts(self.request(['Chain rule']))
        self.assertEqual(repeated[0].id,first[0].id)
        self.assertEqual(self.resolver.calls,count)

    async def test_staged_topics_are_hidden_until_publication_and_reuse_is_fast(self):
        first = await self.engine.resolve_generated_concepts(self.request(['Chain rule']))
        self.assertEqual(self.engine.get_learning_topics(self.page_request()).total, 0)
        second = await self.engine.resolve_generated_concepts(self.request(['CHAIN RULE']))
        self.assertEqual(first[0].id, second[0].id)
        self.assertEqual(self.resolver.calls, 1)
        with self.db.repository.transaction(learner_ids=[self.owner]) as repo:
            repo.publish_topic_skills(self.owner, [first[0].id])
        page = self.engine.get_learning_topics(self.page_request())
        self.assertEqual(page.total, 1)
        self.assertEqual(page.items[0].subskill_count, 1)
        self.assertEqual(page.items[0].checked_count, 0)
        detail = self.engine.get_topic_subskills(self.page_request(), page.items[0].id)
        self.assertEqual(detail.items[0].name, 'Chain rule')
        self.assertEqual(detail.items[0].ability, 'Apply Chain rule')
        self.assertIsNone(detail.items[0].mastery)

    async def test_natural_subskill_count_and_paginated_search(self):
        skills = []
        for batch in ([f'Rule {i}' for i in range(10)], ['Rule 10', 'Rule 11']):
            skills.extend(await self.engine.resolve_generated_concepts(self.request(batch)))
        with self.db.repository.transaction(learner_ids=[self.owner]) as repo:
            repo.publish_topic_skills(self.owner, [skill.id for skill in skills])
        page = self.engine.get_learning_topics(self.page_request(query='rule 11'))
        self.assertEqual(page.total, 1)
        self.assertEqual(page.items[0].subskill_count, 12)
        detail = self.engine.get_topic_subskills(self.page_request(limit=5, offset=5), page.items[0].id)
        self.assertEqual(detail.total, 12)
        self.assertEqual(len(detail.items), 5)

    async def test_legacy_organization_preserves_identity_and_no_mastery_is_created(self):
        original = self.engine.register_concept('Product rule')
        self.engine.link_context_concept(self.owner, self.context, original.id)
        result = await self.engine.organize_learning_topics(self.owner, self.context)
        self.assertEqual(result['organized'], 1)
        page = self.engine.get_learning_topics(self.page_request())
        detail = self.engine.get_topic_subskills(self.page_request(), page.items[0].id)
        self.assertEqual(detail.items[0].concept_id, original.id)
        self.assertIsNone(detail.items[0].mastery)
        self.assertEqual(self.db.repository.list_evidence(self.owner, original.id), [])

    async def test_foreign_topic_is_never_returned(self):
        await self.engine.topics.resolve(self.request(['Chain rule']), published=True)
        foreign = self.engine.get_learning_topics(self.page_request()).items[0].id
        bob = learner_id('bob')
        other_context = self.engine.resolve_learning_context(ResolveLearningContextRequest(
            learner_id=bob, name='Calculus', activate=True)).context_id
        self.assertEqual(self.engine.get_learning_topics(LearningProgressRequest(
            learner_id=bob, context_ids=[other_context])).total, 0)
        from app.core.exceptions import AppError
        with self.assertRaises(AppError) as caught:
            self.engine.get_topic_subskills(LearningProgressRequest(learner_id=bob,
                context_ids=[other_context]), foreign)
        self.assertEqual(caught.exception.status_code, 404)

    async def test_preview_apply_and_undo_preserve_legacy_history(self):
        original = self.engine.register_concept('Product rule')
        self.engine.link_context_concept(self.owner, self.context, original.id)
        preview = await self.engine.organize_learning_topics(self.owner, self.context, preview=True)
        self.assertIn('proposal_id', preview)
        self.assertEqual(self.engine.get_learning_topics(self.page_request()).total, 0)
        applied = self.engine.apply_topic_organization(self.owner, preview['proposal_id'])
        self.assertEqual(applied['organized'], 1)
        self.assertEqual(self.engine.apply_topic_organization(self.owner, preview['proposal_id'])['organized'], 1)
        self.assertEqual(self.engine.get_learning_topics(self.page_request()).total, 1)
        self.engine.apply_topic_organization(self.owner, preview['proposal_id'], undo=True)
        self.engine.apply_topic_organization(self.owner, preview['proposal_id'], undo=True)
        self.assertEqual(self.engine.get_learning_topics(self.page_request()).ungrouped_count, 1)
        self.assertEqual(self.engine.get_concept(original.id).id, original.id)
        self.assertEqual(self.db.repository.list_evidence(self.owner, original.id), [])

    async def test_provider_failure_keeps_a_skill_without_guessing_a_parent(self):
        from unittest.mock import AsyncMock
        self.resolver.organize = AsyncMock(side_effect=ValueError('bad structured advice'))
        concepts = await self.engine.resolve_generated_concepts(self.request(['Chain rule']))
        self.assertEqual(len(concepts), 1)
        self.assertEqual(self.engine.get_skill_topics(self.owner, [concepts[0].id])[concepts[0].id]['topic_id'], None)
        self.assertEqual(self.engine.get_learning_topics(self.page_request()).total, 0)
        self.assertEqual(self.resolver.organize.await_count, 2)
        with self.db.repository.transaction(learner_ids=[self.owner]) as repository:
            repository.add_context_concept(self.context, concepts[0].id, learner_id=self.owner)
            repository.publish_topic_skills(self.owner, [concepts[0].id])
        page = self.engine.get_topic_subskills(self.page_request(query='chain'), 'ungrouped')
        self.assertEqual(page.total, 1)
        self.assertEqual(page.items[0].name, 'Chain rule')

    async def test_concurrent_advice_rechecks_registry_before_publishing(self):
        import asyncio
        original = self.resolver.organize
        async def slow(*args):
            result = await original(*args)
            await asyncio.sleep(.02)
            return result
        self.resolver.organize = slow
        first, second = await asyncio.gather(self.engine.topics.resolve(self.request(['Chain rule']), published=True),
            self.engine.topics.resolve(self.request(['Chain rule']), published=True))
        self.assertEqual(first[0].id, second[0].id)
        page = self.engine.get_learning_topics(self.page_request())
        self.assertEqual(page.total, 1)
        self.assertEqual(page.items[0].subskill_count, 1)

    async def test_chat_encounter_uses_owned_grouping_without_learning_evidence(self):
        from app.langchain.learner_tools import create_learner_tools
        tool = next(value for value in create_learner_tools(self.engine, self.owner) if value.name == 'resolve_student_concept')
        first = await tool.ainvoke(dict(label='Chain rule', context_id=self.context))
        again = await tool.ainvoke(dict(label='Chain rule', context_id=self.context))
        self.assertEqual(first['concept_id'], again['concept_id'])
        page = self.engine.get_learning_topics(self.page_request())
        self.assertEqual(page.total, 1)
        self.assertEqual(page.items[0].subskill_count, 1)
        self.assertEqual(page.items[0].checked_count, 0)
        self.assertEqual(self.db.repository.list_evidence(self.owner, first['concept_id']), [])

    async def test_failed_preview_does_not_write_fallback_membership(self):
        from unittest.mock import AsyncMock
        from app.core.exceptions import AppError
        concept = self.engine.register_concept('Previewed legacy skill')
        self.engine.link_context_concept(self.owner, self.context, concept.id)
        self.resolver.organize = AsyncMock(side_effect=TimeoutError())
        with self.assertRaises(AppError): await self.engine.organize_learning_topics(self.owner, self.context, preview=True)
        self.assertEqual(self.db.repository.skill_memberships(self.owner, [concept.id]), {})
        self.assertEqual(self.engine.get_learning_topics(self.page_request()).total, 0)

    async def test_large_topic_does_not_crowd_other_topics_out_of_recommendations(self):
        from app.learner.schemas import StudyRecommendationsRequest, LearningGoalRequest
        for index in range(13):
            concept = self.engine.register_concept(f'Ranking skill {index}')
            self.engine.link_context_concept(self.owner, self.context, concept.id)
            second = index == 12
            with self.db.repository.transaction(learner_ids=[self.owner]) as repository:
                repository.save_topic_membership(self.owner, self.context, concept.id,
                    TopicPlacement(label=concept.canonical_name, action='create_concept',
                        topic_name='Integration techniques' if second else 'Differentiation rules',
                        scope='Integral calculation' if second else 'Derivative calculation', ability='Solve this skill'), published=True)
            if second:
                self.engine.set_learning_goal(LearningGoalRequest(learner_id=self.owner, context_id=self.context,
                    concept_id=concept.id, importance=.1, target_difficulty=.5))
        values = self.engine.get_study_recommendations(StudyRecommendationsRequest(learner_id=self.owner, context_ids=[self.context], limit=2))
        self.assertEqual(len(values), 2)
        self.assertEqual({value.topic_name for value in values}, {'Differentiation rules', 'Integration techniques'})

    async def test_foreign_advice_ids_are_rejected_before_writing(self):
        from app.core.exceptions import AppError
        from unittest.mock import AsyncMock
        self.resolver.organize = AsyncMock(return_value=TopicOrganization(placements=[TopicPlacement(
            label='Chain rule', action='reuse', skill_id='foreign', topic_id='foreign',
            topic_name='Foreign topic', scope='Not owned', ability='Foreign ability')]))
        with self.assertRaises(AppError):
            await self.engine.resolve_generated_concepts(self.request(['Chain rule']))
        self.assertEqual(self.db.repository.context_concepts(self.owner, [self.context]), [])

    async def test_manual_move_undo_and_rename_keep_evidence_state(self):
        from uuid import uuid4
        from app.learner.schemas import EvidenceSubmissionRequest, ConceptStateRequest
        from app.core.exceptions import AppError
        skills = await self.engine.topics.resolve(self.request(['Chain rule']), published=True)
        skill = skills[0]
        source = self.engine.get_skill_topics(self.owner, [skill.id])[skill.id]['topic_id']
        other = self.engine.register_concept('Integration fixture')
        with self.db.repository.transaction(learner_ids=[self.owner]) as repository:
            target = repository.save_topic_membership(self.owner, self.context, other.id, TopicPlacement(
                label='Integration fixture', action='create_concept', topic_name='Integration methods',
                scope='Methods for integration, excluding differentiation.', ability='Integrate functions'), published=True)
            repository.add_context_concept(self.context, other.id, learner_id=self.owner)
        now = datetime.now(timezone.utc)
        self.engine.submit_evidence(EvidenceSubmissionRequest(learner_id=self.owner, concept_id=skill.id,
            context_id=self.context, source_type='QUIZ', source_id='move-fixture', item_id='move-item',
            result='CORRECT', difficulty=.5, independence=1, occurred_at=now))
        request = ConceptStateRequest(learner_id=self.owner, concept_id=skill.id)
        before = self.engine.get_concept_state(request).model_dump(exclude={'retention_confidence'})
        operation = str(uuid4())
        revision = self.engine.get_skill_topics(self.owner, [skill.id])[skill.id]['revision']
        self.engine.move_topic_subskill(self.owner, source, skill.id, target, operation, revision)
        self.engine.move_topic_subskill(self.owner, source, skill.id, target, operation, revision)
        self.assertEqual(self.engine.get_skill_topics(self.owner, [skill.id])[skill.id]['topic_id'], target)
        self.engine.move_topic_subskill(self.owner, source, skill.id, target, operation, revision, undo=True)
        self.assertEqual(self.engine.get_skill_topics(self.owner, [skill.id])[skill.id]['topic_id'], source)
        with self.assertRaises(AppError):
            self.engine.move_topic_subskill(self.owner, source, skill.id, target, str(uuid4()), revision)
        current_revision = self.engine.get_skill_topics(self.owner, [skill.id])[skill.id]['revision']
        self.engine.rename_learning_topic(self.owner, source, 'Rules of differentiation', current_revision)
        self.assertEqual(self.engine.get_learning_topics(self.page_request()).items[-1].name, 'Rules of differentiation')
        self.assertEqual(self.engine.get_concept_state(request).model_dump(exclude={'retention_confidence'}), before)


class FreshnessTests(unittest.TestCase):
    def test_failed_chat_answer_does_not_rejuvenate_old_successes(self):
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        policy = HeuristicMasteryPolicy()
        state = LearnerConceptState('learner', 'skill')
        for i in range(10):
            state = policy.update(state, LearningEvidence(id=str(i), learner_id='learner', concept_id='skill',
                source_type='QUIZ', source_id=str(i), item_id=str(i), result='CORRECT', occurred_at=now,
                difficulty=.8, independence=1, evidence_confidence=1))
        later = now + timedelta(days=90)
        before = performance_estimate(state, .8, later)[0]
        state = policy.update(state, LearningEvidence(id='failed', learner_id='learner', concept_id='skill',
            source_type='CHAT', source_id='failed', item_id='failed', result='INCORRECT', occurred_at=later,
            difficulty=.8, independence=1, evidence_confidence=1))
        after = performance_estimate(state, .8, later)[0]
        self.assertLess(after, before)
