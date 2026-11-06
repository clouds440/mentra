import unittest
from app.learner.signal_evaluation import signal_gate,KINDS


class SignalEvaluationTests(unittest.TestCase):
    def corpus(self):
        kinds=sorted(KINDS)
        # Synthetic arithmetic/contract fixtures, not actual human annotation.
        return [dict(id=str(index),source_hash=f'synthetic-hash-{index}',language='en' if index<150 else 'ar',
            review=dict(method='independent_human',reviewer_id='synthetic-reviewer',adjudicated=True),
            gold=[dict(id=f'gold-{index}',kind=kinds[index%5],source_id='user')],
            predictions=[dict(kind=kinds[index%5],source_id='user',matched_gold_id=f'gold-{index}',adjudicated_match=True)]) for index in range(300)]

    def test_missing_independent_labels_never_pass(self):
        self.assertFalse(signal_gate([])['G10'])
        records=self.corpus();records[0]['review']['method']='agent_development_fixture'
        self.assertFalse(signal_gate(records)['G10'])

    def test_recall_precision_duplicate_sources_and_mastery_gates(self):
        records=self.corpus()
        self.assertTrue(signal_gate(records)['G10'])
        records[0]['predictions'][0]['claims_mastery']=True
        self.assertFalse(signal_gate(records)['G10'])
        records=self.corpus();records[1]['source_hash']=records[0]['source_hash']
        self.assertFalse(signal_gate(records)['G10'])
        records=self.corpus()
        for record in records[:40]:record['predictions']=[]
        self.assertFalse(signal_gate(records)['G10'])
        records=self.corpus()
        for record in records[:20]:record['predictions'].append(dict(kind='struggle',source_id='user'))
        self.assertFalse(signal_gate(records)['G10'])
