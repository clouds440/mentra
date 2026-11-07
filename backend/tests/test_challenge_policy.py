"""Production-policy checks, independent of the historical design simulation."""
import unittest
from types import SimpleNamespace
from app.challenge.policy import evaluate,target,scope_key
from app.challenge.generation import planning_targets


class ChallengePolicyTests(unittest.TestCase):
    def rows(self,direction='harder',score=.9):
        return [dict(direction=direction,score=score,items=2,session=str(i%2)) for i in range(3)]

    def test_support_needs_families_items_and_sessions(self):
        good=self.rows()
        self.assertEqual(evaluate(good)['offset'],.1)
        for rows in (good[:2],[dict(r,items=1) for r in good],[dict(r,session='one') for r in good]):
            self.assertEqual(evaluate(rows)['offset'],0)

    def test_mixed_performance_prefers_supported_harder_and_flags_uncertainty(self):
        result=evaluate(self.rows()+self.rows('easier',.2))
        self.assertEqual(result['offset'],.1)
        self.assertEqual(result['flags'],['mixed_difficulty_results'])

    def test_easier_is_a_preference_not_a_mastery_estimate(self):
        for score in (.1,.9):self.assertEqual(evaluate(self.rows('easier',score))['offset'],-.1)
        self.assertIn('diagnostic_recommended',evaluate(self.rows('easier',.1))['flags'])
        self.assertEqual(evaluate(self.rows('harder',.1))['offset'],0)

    def test_invalid_scores_and_unbounded_windows_are_rejected(self):
        for value in (float('nan'),float('inf'),-1,2):
            with self.assertRaises(ValueError):evaluate(self.rows(score=value))
        with self.assertRaises(ValueError):evaluate(self.rows()*11)

    def test_explicit_targets_win_and_never_accumulate(self):
        request=SimpleNamespace(challenge_direction='easier')
        plan=[{},{}]
        planning_targets(request,dict(questions=[dict(difficulty=.5,concept_ids=['skill']),dict(difficulty=0,concept_ids=['skill'])]),plan,None)
        self.assertEqual([p['difficulty_target'] for p in plan],[.4,0])
        self.assertTrue(all(p['required_subskill_ids']==['skill'] for p in plan))
        self.assertEqual(target(.95,offset=.1),.9)
        self.assertEqual(target(.05,offset=-.1),.1)

    def test_context_skill_language_and_format_are_separate(self):
        values=['context','skill','en','text']
        key=scope_key(*values)
        for i in range(4):
            other=values.copy();other[i]+='other'
            self.assertNotEqual(scope_key(*other),key)
