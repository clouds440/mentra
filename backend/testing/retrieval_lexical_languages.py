"""PostgreSQL simple versus English stemming across the held-out scripts."""
import argparse
import json
from pathlib import Path
import re
import statistics
from sqlalchemy import text
from app.rag.evaluation import retrieval_metrics
from testing.postgres import PostgresSandbox
from testing.retrieval_corpus import corpus


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--output',type=Path,required=True); args=parser.parse_args()
    if args.output.exists(): raise RuntimeError('Use a fresh evidence filename.')
    documents,queries=corpus(); report={}
    with PostgresSandbox() as db, db.engine.begin() as connection:
        connection.execute(text('CREATE TEMP TABLE study_words (id text,content text)'))
        connection.execute(text('INSERT INTO study_words VALUES (:id,:content)'),
            [dict(id=d['id'],content=d['text']) for d in documents if d['split']=='heldout'])
        query=text("""SELECT id FROM study_words WHERE to_tsvector(CAST(:configuration AS regconfig),content)
            @@ websearch_to_tsquery(CAST(:configuration AS regconfig),:terms)
            ORDER BY ts_rank_cd(to_tsvector(CAST(:configuration AS regconfig),content),
            websearch_to_tsquery(CAST(:configuration AS regconfig),:terms)) DESC,id LIMIT 3""")
        for configuration in ('simple','english'):
            rows=[]
            for item in queries:
                if item['split']!='heldout': continue
                ranked=list(connection.execute(query,dict(configuration=configuration,
                    terms=' OR '.join(re.findall(r'\w+',item['query'])))).scalars())
                rows.append(dict(id=item['id'],language=item['language'],answerable=bool(item['relevant_source_ids']),
                    returned=bool(ranked),**retrieval_metrics(item['relevant_source_ids'],ranked,3)))
            answerable=[r for r in rows if r['answerable']]
            probes={}
            for term in ('dictionaries','catalysts','wrapping','مزاحمت','المقاومة'):
                probes[term]=list(connection.execute(query,dict(configuration=configuration,terms=term)).scalars())
            report[configuration]=dict(recall_at3=statistics.mean(r['recall'] for r in answerable),
                mrr=statistics.mean(r['mrr'] for r in answerable),
                language_recall={lang:statistics.mean(r['recall'] for r in answerable if r['language']==lang)
                    for lang in {r['language'] for r in answerable}},probes=probes,cases=len(rows),observations=rows)
        connection.execute(text('DROP TABLE study_words'))
    report['decision']='Keep simple as default: English stemming is language-specific, needs a matching index, and is not a global multilingual policy.'
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:{a:b for a,b in v.items() if a!='observations'} if isinstance(v,dict) else v for k,v in report.items()},indent=2))


if __name__=='__main__': main()
