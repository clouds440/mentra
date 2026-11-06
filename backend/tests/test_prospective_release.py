import copy,unittest,tempfile,json
from datetime import datetime,timedelta,timezone
from pathlib import Path
from hashlib import sha256
from app.learner.prospective import evaluate,blinded_ablation
from app.assessments.release_gate import assess,RULES

class ProspectiveTests(unittest.TestCase):
    def setUp(self):
        self.protocol=dict(registered_at='2026-01-01T00:00:00+00:00',holdout_after='2026-01-02T00:00:00+00:00',
            training_students=[],training_item_families=[],minimum_outcomes=100,minimum_students=20,minimum_families=20,minimum_subgroup=30,
            required_subgroups=['language:en','language:ar','answer_mode:single_choice'])
        self.rows=[]
        for i in range(120):
            at=datetime(2026,2,1,tzinfo=timezone.utc)+timedelta(minutes=i);outcome=i%2
            self.rows.append(dict(student=f's{i%30}',item_family=f'f{i%40}',attempt_id=f'a{i}',question_id=f'q{i}',
                captured_at=at.isoformat(),outcome_at=(at+timedelta(seconds=1)).isoformat(),expected_score=outcome,
                baseline_recent=.5,baseline_band=.6,supported=True,first_exposure=True,observed=outcome,
                assistance='independent',language='ar' if i%2 else 'en',answer_mode='single_choice',valid=True,independently_reviewed=True,synthetic=False))

    def test_protocol_gates_and_paired_cluster_results(self):
        result=evaluate(self.rows,self.protocol,resamples=200)
        self.assertEqual(result['status'],'passed') # Synthetic unit fixture validates math, never real qualification.
        self.assertEqual(result['baselines']['baseline_recent']['ci95'],[1,1])
        for key,value in [('synthetic',True),('independently_reviewed',False),('first_exposure',False),('assistance','unknown')]:
            rows=copy.deepcopy(self.rows)
            for row in rows:row[key]=value
            self.assertEqual(evaluate(rows,self.protocol,resamples=200)['status'],'held')
        bad=copy.deepcopy(self.rows);bad[0]['outcome_at']=bad[0]['captured_at']
        with self.assertRaises(ValueError):evaluate(bad,self.protocol,resamples=200)
        with self.assertRaises(ValueError):evaluate(self.rows+[self.rows[-1]],self.protocol,resamples=200)
        protocol=dict(self.protocol,training_students=['s0'])
        with self.assertRaises(ValueError):evaluate(self.rows,protocol,resamples=200)
        self.assertEqual(evaluate(self.rows[:20],self.protocol,resamples=200)['status'],'held')

    def test_blinded_ablation_changes_only_learner_packet_and_does_not_mutate(self):
        cases=[dict(id='c1',task='Explain force',sources=['same source'],learner_context={'skills':['force']})]
        before=copy.deepcopy(cases);result=blinded_ablation(cases,42)
        self.assertEqual(cases,before);self.assertEqual(len(result['cases']),2)
        self.assertEqual(sum(row['learner_context'] is None for row in result['cases']),1)
        self.assertEqual(result,blinded_ablation(cases,42))
        self.assertTrue(all(row['task']==cases[0]['task'] and row['sources']==cases[0]['sources'] for row in result['cases']))

class ReleaseGateTests(unittest.TestCase):
    def test_absent_changed_nonindependent_or_wrong_revision_evidence_holds_release(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'evidence.json';path.write_text('{}')
            evidence=[dict(path=path.name,sha256=sha256(path.read_bytes()).hexdigest())]
            gates={key:dict(revision='revision',evidence=evidence,independently_adjudicated=True,
                metrics={name:(True if op=='is' else threshold+.001 if op=='positive' else threshold) for name,(op,threshold) in rules.items()}) for key,rules in RULES.items()}
            manifest=dict(revision='revision',gates=gates)
            self.assertEqual(assess(manifest,directory)['status'],'qualified')
            gates['G15']['independently_adjudicated']=False
            self.assertEqual(assess(manifest,directory)['status'],'held')
            gates['G15']['independently_adjudicated']=True;path.write_text('{"changed":true}')
            self.assertTrue(all(value['status']=='held' for value in assess(manifest,directory)['gates'].values()))
            self.assertEqual(assess({},directory)['status'],'held')
