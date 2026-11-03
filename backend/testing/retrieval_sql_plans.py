"""Verify expression-index behavior under generic prepared PostgreSQL plans."""
import argparse
import hashlib
import json
import random
import statistics
import math
from pathlib import Path
from uuid import uuid4
from sqlalchemy import select, text
from app.rag.repositories.tables import chunks
from tests.rag.test_workflows import WorkflowTests


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--output',type=Path,required=True); args=parser.parse_args()
    if args.output.exists(): raise RuntimeError('Use a fresh output path.')
    fixture=WorkflowTests(); fixture.setUp()
    try:
        fixture.ready()
        with fixture.db.sessions.begin() as session:
            row=dict(session.execute(select(chunks).limit(1)).mappings().one())
            content='Course administration and ordinary study sessions.'
            for start in range(1,10000,500):
                session.execute(chunks.insert(),[dict(row,id=str(uuid4()),ordinal=i,content=content,
                    content_hash=hashlib.sha256(content.encode()).hexdigest()) for i in range(start,min(start+500,10000))])
            session.execute(text('ANALYZE rag_chunk'))
            session.execute(text('SET LOCAL plan_cache_mode=force_generic_plan'))
            session.execute(text("PREPARE variable_config(regconfig,text) AS SELECT id FROM rag_chunk WHERE to_tsvector($1,content) @@ websearch_to_tsquery($1,$2)"))
            session.execute(text("PREPARE fixed_config(text) AS SELECT id FROM rag_chunk WHERE to_tsvector('simple'::regconfig,content) @@ websearch_to_tsquery('simple'::regconfig,$1)"))
            report={}
            for name,sql in [('variable',"EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON) EXECUTE variable_config('simple','decorators')"),
                             ('fixed',"EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON) EXECUTE fixed_config('decorators')")]:
                report[name]=session.execute(text(sql)).scalar()
            order=['variable','fixed']*32; random.Random(1701).shuffle(order)
            samples={'variable':[],'fixed':[]}
            statements={'variable':"EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON) EXECUTE variable_config('simple','decorators')",
                'fixed':"EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON) EXECUTE fixed_config('decorators')"}
            for name in order:
                samples[name].append(session.execute(text(statements[name])).scalar()[0]['Execution Time'])
            report['latency_ms']={name:dict(p50=statistics.median(values),p95=sorted(values)[math.ceil(.95*len(values))-1],
                samples=len(values),raw=values) for name,values in samples.items()}
            report['indexes']=list(session.execute(text("SELECT indexdef FROM pg_indexes WHERE schemaname=current_schema() AND tablename='rag_chunk'")).scalars())
            session.execute(text('DEALLOCATE variable_config')); session.execute(text('DEALLOCATE fixed_config'))
        args.output.write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(report['latency_ms']))
    finally: fixture.doCleanups()


if __name__=='__main__': main()
