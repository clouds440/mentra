import unittest
from dataclasses import replace
from testing.challenge_preference_reference import Scope, Outcome, suggest


class ChallengePreferenceDesignTests(unittest.TestCase):
    def setUp(self):
        self.scope=Scope('student','physics','net-force')

    def events(self,direction='harder',score=.9):
        return [Outcome(self.scope,f'{direction}-{index}',str(index%2),direction,score) for index in range(3)]

    def test_clicks_without_graded_work_do_not_establish_fit(self):
        self.assertEqual(suggest(self.events(score=None),self.scope)['learned_offset'],0)

    def test_repeated_independent_harder_success_supports_one_bounded_step(self):
        result=suggest(self.events(),self.scope)
        self.assertEqual((result['learned_offset'],result['target']),(.1,.6))

    def test_harder_success_and_easier_struggle_prefers_harder_but_flags_the_pattern(self):
        result=suggest(self.events()+self.events('easier',.3),self.scope)
        self.assertEqual(result['learned_offset'],.1)
        self.assertTrue(result['flags'])

    def test_easier_can_be_a_valid_preference_even_with_high_scores(self):
        self.assertEqual(suggest(self.events('easier',.9),self.scope)['learned_offset'],-.1)

    def test_current_explicit_choice_wins_without_changing_learned_fit(self):
        result=suggest(self.events(),self.scope,explicit_direction='easier')
        self.assertEqual((result['target'],result['learned_offset']),(.4,.1))

    def test_repeated_families_assistance_uncertainty_and_reports_cannot_inflate_fit(self):
        for changes in [dict(family='same-family'),dict(assisted=True),dict(first_exposure=False),
                dict(grade_confidence=.3),dict(valid=False),dict(served=False),dict(items=1)]:
            with self.subTest(changes=changes):
                self.assertEqual(suggest([replace(event,**changes) for event in self.events()],self.scope)['learned_offset'],0)

    def test_withdrawal_replay_removes_support_and_processing_is_idempotent(self):
        events=self.events()
        self.assertEqual(suggest(events,self.scope),suggest(events*10,self.scope))
        result=suggest(events+[replace(events[0],valid=False)],self.scope)
        self.assertEqual(result['learned_offset'],0)

    def test_foreign_users_skills_languages_and_formats_never_transfer(self):
        for scope in [replace(self.scope,owner='other'),replace(self.scope,skill='calculus'),
                replace(self.scope,language='ar'),replace(self.scope,answer_mode='text')]:
            self.assertEqual(suggest(self.events(),scope)['learned_offset'],0)

    def test_window_and_target_remain_bounded(self):
        events=[Outcome(self.scope,str(index),str(index),'harder',.9) for index in range(1000)]
        result=suggest(events,self.scope,baseline=.95)
        self.assertEqual(result['window_families'],32)
        self.assertEqual(result['target'],.9)

    def test_single_session_or_fewer_than_three_families_abstains(self):
        self.assertEqual(suggest(self.events()[:2],self.scope)['learned_offset'],0)
        self.assertEqual(suggest([replace(event,session='same') for event in self.events()],self.scope)['learned_offset'],0)
