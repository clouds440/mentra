"""Fail-closed production gate; local preview never implies qualification."""
import json
from hashlib import sha256
from pathlib import Path
from math import isfinite

INDEPENDENT={'G8','G9','G10','G14','G15','G16'}
# Metric, comparison, required value. Missing evidence is HELD, never zero/success.
RULES={
 'G0':{'integrity_failures':('max',0)},
 'G1':{'current_restore_passed':('is',True),'outbox_recovery_passed':('is',True)},
 'G2':{'desktop_runs':('min',30),'mobile_runs':('min',30),'desktop_p95_ms':('max',500),'mobile_p95_ms':('max',1000),'blocking_reads':('max',0)},
 'G3':{'desktop_p95_ms':('max',100),'mobile_p95_ms':('max',200),'navigation_writes':('max',0),'recovery_passed':('is',True)},
 'G4':{'sql':('max',8),'checkouts':('max',2),'commits':('max',0),'remote_combined_p95_ms':('max',1000),'parity_passed':('is',True)},
 'G5':{'operations':('min',1000),'checkout_timeouts':('max',0),'model_wait_holds':('max',0),'control_fences_passed':('is',True)},
 'G6':{'runs':('min',30),'usable_p50_ms':('max',10000),'usable_p95_ms':('max',20000),'full_p95_ms':('max',25000),'content_calls':('max',1),'blocking_organizer_calls':('max',0)},
 'G7':{'warm_p95_ms':('max',30000),'cold_p95_ms':('max',40000),'canary_jobs':('min',300),'canary_internal_failures':('max',0),'rolling_jobs':('min',1000),'rolling_success':('min',.99)},
 'G8':{'independent_items':('min',600),'english_items':('min',300),'arabic_items':('min',300),'severe_defects':('max',0),'deterministic_passed':('is',True)},
 'G9':{'quality_rate':('min',.95),'minimum_subgroup_rate':('min',.9),'written_kappa':('min',.8),'written_mae':('max',.1)},
 'G10':{'independent_turns':('min',300),'precision':('min',.95),'recall':('min',.9),'minimum_stratum_recall':('min',.85),'false_mastery':('max',0)},
 'G11':{'terminal_within_60s':('min',.995),'rated_load_passed':('is',True),'duplicate_effective_results':('max',0)},
 'G12':{'replayed_labels':('min',1000),'stable_identity_passed':('is',True),'lost_evidence':('max',0),'cleanup_recheck_passed':('is',True)},
 'G13':{'concepts':('min',100000),'evidence':('min',1000000),'states_materialized':('max',256),'prompt_skills':('max',8),'prompt_tokens':('max',2000),'read_p95_ms':('max',1000),'top5_recall':('min',.95),'exact_recall':('min',1),'age_strata_passed':('is',True)},
 'G14':{'browser_accessibility_passed':('is',True),'critical_violations':('max',0),'formative_users':('min',12),'task_success':('min',.9),'task_time_no_regression':('is',True)},
 'G15':{'prospective_protocol_passed':('is',True),'relative_brier_gain':('min',.1),'gain_ci_lower':('positive',0),'ece':('max',.05),'maximum_subgroup_loss':('max',.02)},
 'G16':{'blinded_suitability_improved':('is',True),'added_critical_path_ms':('max',200),'preregistered_delayed_gain_ci_lower':('positive',0),'power_analysis_passed':('is',True)},
 'G17':{'choice_runs':('min',30),'choice_processing_p95_ms':('max',200),'choice_model_calls':('max',0),
    'busy_model_does_not_block_choices':('is',True),'written_runs':('min',30),'written_processing_p95_ms':('max',20000),
    'answers_and_rubrics_preserved':('is',True)},
}


def assess(manifest,root):
    root=Path(root).resolve();results={}
    for gate,rules in RULES.items():
        entry=manifest.get('gates',{}).get(gate,{});failures=[]
        if not entry.get('evidence'):failures.append('missing hashed evidence')
        for artifact in entry.get('evidence',[]):
            path=(root/artifact['path']).resolve()
            if not path.is_relative_to(root):raise ValueError('Evidence must remain inside package')
            if not path.is_file() or sha256(path.read_bytes()).hexdigest()!=artifact['sha256']:failures.append('missing or changed evidence')
        if entry.get('revision')!=manifest.get('revision') or not manifest.get('revision'):failures.append('revision mismatch')
        if gate in INDEPENDENT and entry.get('independently_adjudicated') is not True:failures.append('independent review/study absent')
        metrics=entry.get('metrics',{})
        for key,(op,threshold) in rules.items():
            value=metrics.get(key)
            valid=(value is threshold if op=='is' else type(value) in (int,float) and isfinite(value) and value>=0 and
                (value<=threshold if op=='max' else value>=threshold if op=='min' else value>threshold))
            if not valid:failures.append(key)
        results[gate]=dict(status='held' if failures else 'passed',failures=failures,plan_b=entry.get('plan_b','See implementation acceptance register'))
    return dict(status='qualified' if all(v['status']=='passed' for v in results.values()) else 'held',gates=results)


def main():
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('manifest',type=Path);args=parser.parse_args()
    result=assess(json.loads(args.manifest.read_text(encoding='utf-8')),args.manifest.parent)
    print(json.dumps(result,indent=2));return 0 if result['status']=='qualified' else 2
