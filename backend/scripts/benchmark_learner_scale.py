"""Disposable-schema scale qualification. TEST_DATABASE_URL only; no live writes."""
import json,os
from time import perf_counter
from statistics import median
from sqlalchemy import text,event
from tests.test_ranking_projection import RankingIndexTests


def main():
    fixture=RankingIndexTests();fixture.setUp()
    try:
        fixture.seed(1)
        owner,context=fixture.owner,fixture.context
        with fixture.db.engine.begin() as conn:
            conn.execute(text("""INSERT INTO concept(id,canonical_name,normalized_name)
                SELECT 'scale-'||n,'Scale '||n,'scale '||n FROM generate_series(1,100000) n"""))
            conn.execute(text("""INSERT INTO context_concept(learner_id,context_id,concept_id)
                SELECT :owner,:context,'scale-'||n FROM generate_series(1,100000) n"""),dict(owner=owner,context=context))
            conn.execute(text("""INSERT INTO learner_concept_state
                (learner_id,concept_id,mastery,estimate_confidence,retention_confidence,evidence_count,independent_successes,
                 last_evidence_at,last_demonstrated_at,version,policy_data_json,mastery_policy_version,retention_policy_version)
                SELECT learner_id,'scale-'||n,(n%100)/100.0,(n%97)/97.0,(n%89)/89.0,evidence_count,independent_successes,
                    last_evidence_at,last_demonstrated_at,version,policy_data_json,mastery_policy_version,retention_policy_version
                FROM learner_concept_state CROSS JOIN generate_series(1,100000) n WHERE concept_id='projection-0'"""))
            fields=['policy_identity','base_half_life','anchor','independent_items','retention_half_life',
                'mastery','estimate_confidence','retention_confidence','last_demonstrated_at','verification_required',
                'mastery_policy_version','retention_policy_version']+[
                f'{band}_{field}' for band in ('easy','medium','hard') for field in ('amplitude','half_life','supported')]
            names=','.join(fields)
            values=','.join({'mastery':'(n%100)/100.0','estimate_confidence':'(n%97)/97.0',
                'retention_confidence':'(n%89)/89.0','verification_required':'false'}.get(name,name) for name in fields)
            conn.execute(text(f"""INSERT INTO learner_ranking_projection(learner_id,concept_id,state_version,{names})
                SELECT learner_id,'scale-'||n,state_version,{values} FROM learner_ranking_projection
                CROSS JOIN generate_series(1,100000) n WHERE concept_id='projection-0'"""))
            conn.execute(text("""INSERT INTO learning_evidence
                (id,learner_id,concept_id,context_id,source_type,source_id,result,hint_count,evidence_confidence,metadata_json)
                SELECT 'scale-evidence-'||n,:owner,'scale-'||((n-1)%100000+1),:context,'QUIZ','scale-evidence-'||n,
                    'CORRECT',0,1,'{}'::jsonb FROM generate_series(1,1000000) n"""),dict(owner=owner,context=context))
            for table in ('concept','context_concept','learner_concept_state','learner_ranking_projection','learning_evidence'):
                conn.execute(text('ANALYZE '+table))
        durations=[];max_materialized=0;ledger_reads=0;query_times={};plans=[]
        def query(conn,cursor,statement,*args):
            nonlocal ledger_reads
            if statement.lstrip().upper().startswith('SELECT') and 'learning_evidence' in statement:
                ledger_reads+=1
            args[-2]._scale_started=perf_counter()
        def finished(conn,cursor,statement,parameters,context,executemany):
            name='candidates' if 'ranking_scope' in statement else statement[:80]
            query_times.setdefault(name,[]).append((perf_counter()-context._scale_started)*1000)
            if name=='candidates' and not plans:
                plans.append('Profiling')
                rows=conn.exec_driver_sql('EXPLAIN (ANALYZE,BUFFERS) '+statement,parameters).all()
                plans[:]=[str(row[0]) for row in rows]
        event.listen(fixture.db.engine,'before_cursor_execute',query)
        event.listen(fixture.db.engine,'after_cursor_execute',finished)
        runs=int(os.environ.get('SCALE_RUNS','30'))
        for _ in range(runs):
            started=perf_counter()
            with fixture.engine.read_scope() as scoped:
                result=scoped.get_study_targets(owner,[context],supported_verification=True)
                max_materialized=max(max_materialized,len(scoped.states._read_states))
            durations.append((perf_counter()-started)*1000)
            assert len(result['recommendations'])==5
        metrics=dict(concepts=100001,evidence=1000000,runs=runs,median_ms=median(durations),
            p95_ms=sorted(durations)[min(len(durations)-1,int(len(durations)*.95))],max_ms=max(durations),max_materialized=max_materialized,ledger_reads=ledger_reads,
            topology='Local Docker PostgreSQL 17; host desktop; no provider or network inference')
        event.remove(fixture.db.engine,'before_cursor_execute',query)
        event.remove(fixture.db.engine,'after_cursor_execute',finished)
        print('QUERY_TIMINGS',json.dumps({key:median(times) for key,times in query_times.items()}),flush=True)
        print('QUERY_PLAN\n'+'\n'.join(plans),flush=True)
        if runs<30:
            print('DIAGNOSTIC_ONLY',json.dumps(metrics),flush=True)
            return
        # Offline oracle may materialize everything; the served path never does.
        from app.learner.schemas import StudyRecommendationsRequest
        request=StudyRecommendationsRequest(learner_id=owner,context_ids=[context])
        concepts=fixture.db.repository.context_concepts(owner,[context])
        all_states={s.concept_id:s for s in fixture.db.repository.list_states(owner)}
        contexts=fixture.engine.contexts.select(owner,[context])
        data=(concepts,all_states,{},fixture.db.repository.context_factors(owner,contexts),fixture.now)
        fixture.engine.retrieval._membership_cache={c.id:None for c in concepts}
        predictions={}
        oracle=dict(recommendations=fixture.engine.retrieval.recommend(request,data=data,predictions=predictions),
            verification=fixture.engine.retrieval.recommend(request,data=data,verification=True,supported_only=True,predictions=predictions))
        recalls=[]
        for mode in oracle:
            gold={v.concept_id for v in oracle[mode]}
            recalls.append(len(gold & {v.concept_id for v in result[mode]})/len(gold) if gold else 1)
        exact=[f'scale-{n}' for n in (1,2,9,87,431,9001,99999,100000)]
        assert {v.id for v in fixture.engine.get_practice_concepts(owner,context,exact)}==set(exact)
        metrics.update(top5_recall=min(recalls),exact_target_recall=1)
        print(json.dumps(metrics,indent=2),flush=True)
        assert max_materialized<=256 and ledger_reads==0
        assert metrics['p95_ms']<=1000,metrics
        assert min(recalls)>=.95,metrics
    finally:
        fixture.doCleanups()


if __name__=='__main__': main()
