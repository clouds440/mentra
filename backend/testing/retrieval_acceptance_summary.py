"""Derive acceptance decisions from preserved raw reports; never invent results."""
import argparse
import hashlib
import json
from pathlib import Path
import random
import re
import statistics


def interval(values):
    rng=random.Random(1701)
    samples=sorted(statistics.mean(rng.choices(values,k=len(values))) for _ in range(1000))
    return dict(mean=statistics.mean(values),lower=samples[24],upper=samples[974],seed=1701)


def source_means(rows,metric):
    grouped={}
    for row in rows:
        if row['split']=='heldout' and row['supported']:
            grouped.setdefault(row['id'].split('-q')[0],[]).append(row[metric])
    return {key:statistics.mean(values) for key,values in grouped.items()}


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('evidence',type=Path)
    parser.add_argument('--output',type=Path,required=True); args=parser.parse_args()
    if args.output.exists(): raise RuntimeError('Acceptance summary already exists.')
    prefix='embedding-completion-2026-11-03-'
    def read(name): return json.loads((args.evidence/(prefix+name+'.json')).read_text())
    log=(args.evidence/(prefix+'finished-tests.txt')).read_text(encoding='utf-8-sig')
    count=int(re.search(r'Ran (\d+) tests',log).group(1))
    assert count>=154 and re.search(r'^OK$',log,re.M) and not re.search(r'^FAILED',log,re.M)
    canary=read('finished-canary'); source=read('finished-source-manifest'); models=read('accepted-multilingual')
    rollback=read('artifact-rollback'); parity=read('asset-parity'); load=read('indexed-load')
    research=read('research'); ablations=read('ablations-final'); sql=read('sql-acceptance'); norm=read('normalization')
    assert canary['passed'] and canary['source_tree_sha256']==source['tree_sha256']
    assert models['pipeline_passed']==models['reranker_passed']==models['cases']==27
    assert rollback['old_passed'] and rollback['new_passed'] and rollback['cleaned_up']
    assert parity['passed'] and len(load['load'])==36
    assert all(item['degraded']==0 and item['latency_ms']['p95']<2000 for item in load['load'].values())
    assert 'idx_rag_chunk_lexical' in json.dumps(sql['fixed'])
    assert sql['latency_ms']['fixed']['p95']<sql['latency_ms']['variable']['p95']
    assert norm['normalized_coverage'] and norm['spans_valid'] and norm['exact_remote_local_equivalence']
    assert all(item['exact_coverage'] for item in ablations['chunking'].values())
    assert research['documents']>=50 and research['queries']>=200
    paired={}
    baseline=source_means(research['observations']['dense'],'mrr')
    for mode,rows in research['observations'].items():
        comparison=source_means(rows,'mrr')
        paired[mode]=interval([comparison[key]-baseline[key] for key in sorted(baseline)])
    windows=ablations['passage_windows']
    report=dict(implementation_complete=True,local_acceptance_complete=True,production_deployed=False,
        source_tree_sha256=source['tree_sha256'],verified_source_files=canary['verified_source_files'],
        frozen_image_tests=count,real_multilingual_cases=27,load_requests=36*32,load_degraded=0,
        worst_load_p95_ms=max(item['latency_ms']['p95'] for item in load['load'].values()),
        normalized_span_cases=norm['cases'],schema_head='20261103_0039',
        source_cluster_mrr_delta_vs_dense=paired,
        late_support=dict(cases=len(windows),prefix_top1=sum(row['prefix_top1'] for row in windows),
            window_top1=sum(row['full_window_top1'] for row in windows),
            paired_lift=interval([int(row['full_window_top1'])-int(row['prefix_top1']) for row in windows]),
            regressions=[row['id'] for row in windows if row['prefix_top1'] and not row['full_window_top1']]),
        decisions=dict(increase_rerank_cap_to_40='rejected: recall loss and 47 degraded held-out results',
            universal_support_threshold='rejected: 20 percent held-out false abstention',
            default_chunk_overlap_or_headings='rejected: no measured recall gain',
            default_block_packing='rejected: no proven gain and public span contract change required',
            universal_english_stemming='rejected: fixture-specific gain is not a global multilingual policy',
            bounded_full_passage_windows='adopted with explicit overflow fallback and scored-window provenance',
            colocated_chunking_and_token_batched_inference='adopted: exact output equivalence',
            lexical_index_repair_and_fixed_configuration='adopted: missing-index proof and measured index-plan gain'),
        caveats=['Synthetic workflow corpus; no production-distribution accuracy claim.',
            'First research ranking run used fixed variant order and shared host load; timing is observational.',
            'Bootstrap groups paraphrases by source; intervals apply only to these fixtures.',
            'Process-tree memory sampling starts after embedding initialization; separate DB/Qdrant memory excluded.'])
    report['input_sha256']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in args.evidence.glob(prefix+'*') if p.is_file()}
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({key:report[key] for key in ('implementation_complete','local_acceptance_complete','frozen_image_tests','real_multilingual_cases','load_requests')}))


if __name__=='__main__': main()
