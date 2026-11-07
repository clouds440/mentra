import unittest
from uuid import uuid4
from datetime import datetime,timedelta,timezone
from unittest.mock import patch
from sqlalchemy import select,update,func
from sqlalchemy import event
from sqlalchemy.exc import DBAPIError
from app.core.exceptions import AppError
from app.assessments.schemas import StartAttempt,SubmitAnswers
from app.assessments.worker import AssessmentWorker
from app.assessments.evidence_worker import AssessmentEvidenceWorker
from app.assessments.generation_worker import AssessmentGenerationWorker
from app.challenge.repositories.worker import ChallengeWorker
from app.challenge.repositories.tables import choices,outcomes,states,families,jobs
from app.challenge.repositories.controls import page,change
from app.challenge.schemas import ChallengeControl
from app.challenge.repositories.actions import queue_action
from app.learner.schemas import LearnerContextRequest
from app.learner.engine import LearnerEngine
from app.learner.repositories.tables import learning_evidence
from app.langchain.prompts import PromptSource
from tests import test_challenge_actions as actions


class ChallengeLearningTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        actions.ChallengeActionTests.setUp(self)
        self.time=datetime(2026,11,6,12,tzinfo=timezone.utc)
        self.service.repository.clock=lambda:self.time
        self.learner=LearnerEngine(self.db.repository,clock=lambda:self.time)
        self.service.workflows.learner=self.learner
        self.family_number=0
        self.item_language='en'
        invoke=self.service.workflows.llm.ainvoke
        async def generate(source,payload,**kwargs):
            result=await invoke(source,payload,**kwargs)
            if source is PromptSource.ASSESSMENT_GENERATION:
                for index,question in enumerate(result.questions):
                    planned=payload['question_plan'][index]
                    question.difficulty=planned.get('difficulty_target',.4)
                    question.language=self.item_language
                    question.prompt+=f' Set {self.family_number}; challenge {question.difficulty}; item {index}.'
            return result
        self.service.workflows.llm.ainvoke=generate

    original=actions.ChallengeActionTests.original
    action=actions.ChallengeActionTests.action

    async def intervention(self,*,correct=True,assistance='independent',same_source=None,run_challenge=True):
        self.family_number+=1
        conversation,original=same_source or await self.original()
        scope=self.action(conversation,original)
        job=queue_action(self.service,self.owner,scope)
        await AssessmentGenerationWorker(self.service).run_once()
        complete=self.service.generation_jobs.get(self.owner,job['id'])
        self.assertEqual(complete['state'],'completed',complete)
        from app.chat.repositories.tables import turns
        with self.db.sessions.begin() as session:
            session.execute(update(turns).where(turns.c.learner_id==self.owner,turns.c.id==scope['turn_id']).values(state='SUCCEEDED',lease_until=None))
        card=complete['result'];paper=card['assessment']
        attempt=self.service.repository.start(self.owner,card['assessment_id'],StartAttempt(client_request_id=uuid4()))
        private=self.service.repository.revision_source(self.owner,paper['id'])
        answers={q['id']:q['correct_option_id'] if correct else next(option['id'] for option in q['options'] if option['id']!=q['correct_option_id']) for q in private['questions']}
        self.service.submit(self.owner,str(attempt.id),SubmitAnswers(expected_revision=attempt.revision,client_request_id=uuid4(),answers=answers,assistance=assistance))
        self.assertTrue(await AssessmentWorker(self.service).run_once())
        self.assertTrue(await AssessmentEvidenceWorker(self.service).run_once())
        saved=self.service.repository.attempt(self.owner,str(attempt.id))
        self.assertIn(saved.evidence_status,('applied','partial'))
        if run_challenge:self.assertTrue(await ChallengeWorker(self.service.repository).run_once())
        return card,attempt,(conversation,original)

    async def test_three_families_remain_shadow_until_opt_in_then_reach_learner_packet(self):
        for _ in range(3):
            card,_,_=await self.intervention();self.time+=timedelta(days=1)
        items=page(self.service.repository,self.owner)['items']
        self.assertTrue(items,items)
        self.assertTrue(any(row['offset']==.1 for row in items),items)
        selected=next(row for row in items if row['offset']==.1)
        self.assertFalse(selected['enabled'])
        request=LearnerContextRequest(learner_id=self.owner,context_ids=[selected['context_id']],query='Linear equations',max_concepts=8)
        with self.learner.read_scope() as scoped:packet=scoped.get_relevant_context(request)
        self.assertFalse(any(item.challenge_preferences for item in packet.concepts))
        body=ChallengeControl(context_id=selected['context_id'],concept_id=selected['concept_id'],enabled=True,
            expected_revision=0,client_request_id=uuid4())
        result=change(self.service.repository,self.owner,body)
        self.assertEqual(change(self.service.repository,self.owner,body),result)
        with self.learner.read_scope() as scoped:packet=scoped.get_relevant_context(request)
        self.assertTrue(any(item.challenge_preferences for item in packet.concepts))
        with patch('app.core.config.settings.learner_challenge_adaptation_enabled',False):
            with self.learner.read_scope() as scoped:disabled=scoped.get_relevant_context(request)
            self.assertFalse(any(item.challenge_preferences for item in disabled.concepts))

    async def test_replays_reports_and_resets_cannot_inflate_or_revive_preference(self):
        latest=None
        for _ in range(3):latest=await self.intervention();self.time+=timedelta(days=1)
        item=next(row for row in page(self.service.repository,self.owner)['items'] if row['offset']==.1)
        body=ChallengeControl(context_id=item['context_id'],concept_id=item['concept_id'],enabled=True,expected_revision=0,client_request_id=uuid4())
        change(self.service.repository,self.owner,body)
        with self.db.sessions() as session:before=session.scalar(select(func.count()).select_from(outcomes))
        self.assertFalse(await ChallengeWorker(self.service.repository).run_once())
        card=latest[0];paper=card['assessment']
        self.service.repository.review_item(self.owner,paper['id'],paper['questions'][0]['id'],paper['revision'],str(uuid4()),'wrong_answer')
        with self.db.sessions() as session:self.assertEqual(session.scalar(select(func.count()).select_from(states)),0)
        while await ChallengeWorker(self.service.repository).run_once():pass
        self.assertTrue(all(row['offset']==0 for row in page(self.service.repository,self.owner)['items']))
        reset=body.model_copy(update={'reset':True,'expected_revision':1,'client_request_id':uuid4()})
        change(self.service.repository,self.owner,reset)
        with self.db.sessions() as session:self.assertEqual(session.scalar(select(func.count()).select_from(outcomes)),before)

    async def test_assisted_work_never_establishes_fit(self):
        for _ in range(3):await self.intervention(assistance='assisted');self.time+=timedelta(days=1)
        self.assertTrue(all(row['families']==0 and row['offset']==0 for row in page(self.service.repository,self.owner)['items']))

    async def test_mini_worker_failure_does_not_undo_saved_results_or_formal_evidence(self):
        card,attempt,_=await self.intervention(run_challenge=False)
        before=self.service.repository.attempt(self.owner,str(attempt.id))
        self.assertEqual(before.state,'graded')
        with self.db.sessions() as session:count=session.scalar(select(func.count()).select_from(learning_evidence))
        self.assertGreater(count,0)
        with patch('app.challenge.repositories.store.observe',side_effect=RuntimeError('Test independent failure')):
            self.assertTrue(await ChallengeWorker(self.service.repository).run_once())
        after=self.service.repository.attempt(self.owner,str(attempt.id))
        self.assertEqual(after,before)
        with self.db.sessions() as session:
            self.assertEqual(session.scalar(select(func.count()).select_from(learning_evidence)),count)
            self.assertEqual(session.scalar(select(jobs.c.state)),'failed')

    async def test_owner_controls_and_immutable_outcomes_are_enforced(self):
        await self.intervention()
        self.assertEqual(page(self.service.repository,self.other)['items'],[])
        row=page(self.service.repository,self.owner)['items'][0]
        with self.assertRaises(AppError):change(self.service.repository,self.other,ChallengeControl(
            context_id=row['context_id'],concept_id=row['concept_id'],enabled=True,expected_revision=0,client_request_id=uuid4()))
        with self.assertRaises(DBAPIError):
            with self.db.sessions.begin() as session:session.execute(update(outcomes).values(payload={}))

    async def test_same_family_siblings_count_once_and_ineligible_repeat_cannot_erase_it(self):
        first=await self.intervention()
        await self.intervention(same_source=first[2])
        await self.intervention(same_source=first[2],assistance='assisted')
        with self.db.sessions() as session:
            self.assertEqual(session.scalar(select(func.count()).select_from(outcomes)),3)
            effective=session.execute(select(families)).mappings().all()
        self.assertEqual(len(effective),1)
        self.assertTrue(effective[0]['valid'])
        self.assertEqual(effective[0]['payload']['items'],3)
        self.assertEqual(page(self.service.repository,self.owner)['items'][0]['offset'],0)

    async def test_reporting_an_intermediate_variant_withdraws_descendant_support(self):
        first=await self.intervention()
        await self.intervention(same_source=(first[2][0],first[0]))
        paper=first[0]['assessment']
        self.service.repository.review_item(self.owner,paper['id'],paper['questions'][0]['id'],paper['revision'],str(uuid4()),'wrong_answer')
        with self.db.sessions() as session:
            self.assertFalse(session.scalar(select(families.c.valid)))
            self.assertEqual(session.scalar(select(func.count()).select_from(states)),0)
        while await ChallengeWorker(self.service.repository).run_once():pass
        self.assertTrue(all(row['offset']==0 for row in page(self.service.repository,self.owner)['items']))

    async def test_source_report_before_late_outcome_cannot_restore_support(self):
        _,_,source=await self.intervention(run_challenge=False)
        paper=source[1]['assessment']
        self.service.repository.review_item(self.owner,paper['id'],paper['questions'][0]['id'],paper['revision'],str(uuid4()),'wrong_answer')
        while await ChallengeWorker(self.service.repository).run_once():pass
        with self.db.sessions() as session:
            self.assertFalse(session.scalar(select(families.c.valid)))

    async def test_served_report_and_duplicate_outcome_cannot_restore_withdrawn_support(self):
        card,_,_=await self.intervention()
        paper=card['assessment']
        with self.db.sessions() as session:original_payload=session.scalar(select(outcomes.c.payload))
        self.service.repository.review_item(self.owner,paper['id'],paper['questions'][0]['id'],paper['revision'],str(uuid4()),'wrong_answer')
        with self.db.sessions.begin() as session:
            session.execute(update(jobs).where(jobs.c.kind=='outcome').values(state='queued',attempts=0))
        while await ChallengeWorker(self.service.repository).run_once():pass
        with self.db.sessions() as session:
            self.assertFalse(session.scalar(select(families.c.valid)))
            self.assertEqual(session.scalar(select(outcomes.c.payload)),original_payload)
            self.assertTrue(all(value=='applied' for value in session.scalars(select(jobs.c.state))))

    async def test_unknown_language_and_low_confidence_abstain(self):
        from app.assessments.repositories.tables import attempts
        self.item_language='und'
        await self.intervention()
        self.item_language='en'
        _,attempt,_=await self.intervention(run_challenge=False)
        with self.db.sessions.begin() as session:
            grades=session.scalar(select(attempts.c.grades).where(attempts.c.id==str(attempt.id)))
            for grade in grades:grade['confidence']=.2
            session.execute(update(attempts).where(attempts.c.id==str(attempt.id)).values(grades=grades))
        await ChallengeWorker(self.service.repository).run_once()
        self.assertTrue(all(row['families']==0 and row['offset']==0 for row in page(self.service.repository,self.owner)['items']))

    async def test_reset_blocks_late_old_jobs_and_retries_are_idempotent(self):
        _,attempt,_=await self.intervention(run_challenge=False)
        concept=self.service.repository.revision_source(self.owner,str(attempt.assessment_id))['questions'][0]['concept_ids'][0]
        self.time+=timedelta(seconds=1)
        change(self.service.repository,self.owner,ChallengeControl(context_id=self.request.context_id,concept_id=concept,
            enabled=True,reset=True,expected_revision=0,client_request_id=uuid4()))
        await ChallengeWorker(self.service.repository).run_once()
        with self.db.sessions.begin() as session:
            before=session.scalar(select(func.count()).select_from(outcomes))
            session.execute(update(jobs).values(state='queued',attempts=0))
        await ChallengeWorker(self.service.repository).run_once()
        with self.db.sessions() as session:self.assertEqual(session.scalar(select(func.count()).select_from(outcomes)),before)
        self.assertTrue(all(row['families']==0 and row['offset']==0 for row in page(self.service.repository,self.owner)['items']))

    async def test_active_preferences_keep_foreground_read_budget_and_prompt_observations(self):
        from app.learner.prompt_context import compact
        import json
        for _ in range(3):await self.intervention();self.time+=timedelta(days=1)
        row=page(self.service.repository,self.owner)['items'][0]
        change(self.service.repository,self.owner,ChallengeControl(context_id=row['context_id'],concept_id=row['concept_id'],
            enabled=True,expected_revision=0,client_request_id=uuid4()))
        counts=dict(queries=0,checkouts=0,commits=0)
        def query(*args):counts['queries']+=1
        def checkout(*args):counts['checkouts']+=1
        def commit(*args):counts['commits']+=1
        hooks=[('before_cursor_execute',query),('checkout',checkout),('commit',commit)]
        for name,callback in hooks:event.listen(self.db.engine,name,callback)
        try:packet=self.learner.get_assessment_context(self.owner,self.request.context_id,'Linear equations',[row['concept_id']]).packet
        finally:
            for name,callback in hooks:event.remove(self.db.engine,name,callback)
        self.assertTrue(any(item.challenge_preferences for item in packet.concepts))
        self.assertLessEqual(counts['queries'],7)
        self.assertEqual((counts['checkouts'],counts['commits']),(1,0))
        self.assertLessEqual(len(json.dumps(compact(packet),ensure_ascii=False,separators=(',',':')).encode()),2000)
        fits=[fit for skill in compact(packet)['skills'] for fit in skill.get('challenge_fit',[])]
        self.assertTrue(fits)
        self.assertTrue(all(fit['context_id']==self.request.context_id for fit in fits))
        print('ACTIVE_CHALLENGE_PREPARATION_METRIC',counts)

    async def test_controls_have_revision_fences_and_owner_pagination(self):
        from app.challenge.repositories.operations import export_page,rebuild
        await self.intervention()
        row=page(self.service.repository,self.owner)['items'][0]
        body=ChallengeControl(context_id=row['context_id'],concept_id=row['concept_id'],enabled=True,expected_revision=0,client_request_id=uuid4())
        change(self.service.repository,self.owner,body)
        with self.assertRaises(AppError):change(self.service.repository,self.owner,body.model_copy(update={'client_request_id':uuid4()}))
        with self.assertRaises(AppError):change(self.service.repository,self.owner,body.model_copy(update={'enabled':False}))
        self.assertEqual(export_page(self.service.repository,self.other,'choices')['items'],[])
        exported=export_page(self.service.repository,self.owner,'choices')['items'][0]
        self.assertNotIn('payload',exported)
        self.assertEqual(rebuild(self.service.repository,self.other)['rebuilt'],0)
        self.assertEqual(rebuild(self.service.repository,self.owner)['rebuilt'],1)

    async def test_lease_reclaim_fences_old_worker_and_exhausted_crashes_terminate(self):
        from app.challenge.repositories.worker import enqueue
        from app.challenge.repositories.operations import retry
        repo=self.service.repository
        with repo.transactions.write(self.owner) as tx:enqueue(repo,tx._session,self.owner,'refresh','lease-case',dict(scopes=[]))
        worker=ChallengeWorker(repo);old=worker.claim()
        self.assertIsNone(worker.claim())
        self.time+=timedelta(seconds=61)
        current=worker.claim();self.assertNotEqual(current['claim_id'],old['claim_id'])
        worker.complete(old)
        with self.db.sessions() as session:self.assertEqual(session.scalar(select(jobs.c.state)),'running')
        worker.fail(current)
        with self.assertRaises(AppError):retry(repo,self.other,current['id'])
        retry(repo,self.owner,current['id'])
        current=worker.claim()
        with self.db.sessions.begin() as session:session.execute(update(jobs).values(attempts=3,claim_until=self.time-timedelta(seconds=1)))
        self.assertIsNone(worker.claim())
        with self.db.sessions() as session:self.assertEqual(session.scalar(select(jobs.c.state)),'failed')

    async def test_expiry_and_window_are_bounded_without_scanning_the_ledger(self):
        from app.challenge.repositories.store import refresh_many
        from app.challenge.policy import scope_key,POLICY
        now=self.time;dimensions=dict(context_id=self.request.context_id,concept_id=str(uuid4()),language='en',answer_mode='text')
        key=scope_key(**dimensions)
        with self.db.sessions.begin() as session:
            session.execute(families.insert(),[dict(learner_id=self.owner,scope_key=key,family=str(i),assessment_id=str(uuid4()),
                attempt_id=str(uuid4()),grade_revision=1,occurred_at=now-timedelta(days=i),valid=True,
                payload=dict(**dimensions,direction='harder',items=2,score=.9,session=str(i))) for i in range(100)])
            refresh_many(session,self.owner,{key:dimensions},now)
            state=session.execute(select(states)).mappings().one()
            self.assertEqual(state['payload']['families'],32)
            self.assertEqual(state['expires_at'],now+timedelta(days=59))
            self.assertEqual(state['policy'],POLICY)
            refresh_many(session,self.owner,{key:dimensions},now+timedelta(days=100))
            self.assertEqual(session.scalar(select(states.c.payload))['families'],0)
