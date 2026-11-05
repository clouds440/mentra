import unittest
from copy import deepcopy
from app.assessments.evaluation import quality_gate,grading_gate


class EvaluationGateTests(unittest.TestCase):
    def corpus(self):
        # Synthetic gate-contract fixture, never independent empirical evidence.
        ratings=dict(alignment=4,solvability=5,clarity=4,level=4)
        return [dict(id=str(index),source_hash=f'synthetic-{index}',language='en' if index<300 else 'ar',format='mcq',generator_id='generator',
            reviews=[dict(reviewer_id=name,method='independent_human',blinded=True,ratings=dict(ratings),defects=[])
                for name in ('synthetic-reviewer-a','synthetic-reviewer-b')],adjudication=dict(accepted=True,ratings=dict(ratings),defects=[])) for index in range(600)]

    def test_missing_independent_review_and_empty_corpus_cannot_pass(self):
        self.assertFalse(quality_gate([])['G8'])
        items=self.corpus();items[0]['reviews'][1]['reviewer_id']='synthetic-reviewer-a'
        self.assertFalse(quality_gate(items)['G8'])
        items=self.corpus();items[0]['reviews'][0]['method']='model'
        self.assertFalse(quality_gate(items)['G8'])

    def test_single_severe_defect_or_unresolved_disagreement_holds_release(self):
        items=self.corpus()
        self.assertTrue(quality_gate(items)['G8'])
        items[0]['adjudication']['defects']=['wrong_key']
        self.assertFalse(quality_gate(items)['G8'])
        items=self.corpus();items[0]['reviews'][1]['ratings']=dict(alignment=1,solvability=5,clarity=4,level=4)
        self.assertFalse(quality_gate(items)['G8'])

    def test_language_and_quality_thresholds_and_grade_agreement(self):
        self.assertFalse(quality_gate(self.corpus()[:599])['G8'])
        items=deepcopy(self.corpus())
        for item in items[:40]: item['adjudication']['ratings']['alignment']=3
        self.assertFalse(quality_gate(items)['G9_items'])
        self.assertFalse(grading_gate([])['passed'])
        pairs=[dict(model_score=score,adjudicated_score=score,max_score=4) for score in range(5)]
        self.assertTrue(grading_gate(pairs)['passed'])
        pairs[0]['model_score']=4
        self.assertFalse(grading_gate(pairs)['passed'])
