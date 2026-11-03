"""Generic-plan expression microbenchmark, not an application latency forecast."""
import json
from statistics import median
from time import perf_counter
from sqlalchemy import text
from testing.postgres import PostgresSandbox


def main():
    with PostgresSandbox() as db:
        with db.engine.begin() as connection:
            connection.execute(text('CREATE TABLE audit_fts (id integer PRIMARY KEY, content text NOT NULL)'))
            connection.execute(text("INSERT INTO audit_fts SELECT n,CASE WHEN n=1 THEN 'uniquesupport' ELSE 'ordinary source text' END FROM generate_series(1,20000) n"))
            connection.execute(text("CREATE INDEX audit_fts_vector ON audit_fts USING gin(to_tsvector('simple'::regconfig,content))"))
            connection.execute(text('ANALYZE audit_fts'))
            connection.execute(text('SET LOCAL plan_cache_mode=force_generic_plan'))
            connection.execute(text("PREPARE audit_old(regconfig,text) AS SELECT id FROM audit_fts WHERE to_tsvector($1,content) @@ plainto_tsquery('simple',$2)"))
            connection.execute(text("PREPARE audit_new(text) AS SELECT id FROM audit_fts WHERE to_tsvector('simple'::regconfig,content) @@ plainto_tsquery('simple',$1)"))
            result={}
            for name,query in [('bound_config',"EXECUTE audit_old('simple','uniquesupport')"),('literal_config',"EXECUTE audit_new('uniquesupport')")]:
                plan=connection.execute(text('EXPLAIN (FORMAT JSON) '+query)).scalar_one()
                samples=[]
                for _ in range(12):
                    started=perf_counter();rows=connection.execute(text(query)).all()
                    samples.append((perf_counter()-started)*1000)
                    assert rows==[(1,)]
                result[name]=dict(plan=plan,median_ms=median(samples),samples_ms=samples)
            assert result['bound_config']['plan'][0]['Plan']['Node Type']=='Seq Scan'
            assert result['literal_config']['plan'][0]['Plan']['Node Type']=='Bitmap Heap Scan'
            print(json.dumps(result,indent=2))


if __name__=='__main__':main()
