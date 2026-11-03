"""Offline, disposable, end-to-end research and acceptance runner.

Run in the baked image with dedicated TEST_DATABASE_URL/TEST_QDRANT_URL.
Writes a new evidence report; never overwrites a historical report.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import io
import json
import math
from pathlib import Path
import random
import statistics
import time
from uuid import uuid4

from qdrant_client import QdrantClient
from sqlalchemy import select, text, func, update
from app.core.config import Settings
from app.core.read_cache import ReadCache
from app.learner.engine import LearnerEngine
from app.learner.schemas import ResolveLearningContextRequest
from app.rag.embedding_process import ProcessEmbeddingService
from app.rag.evaluation import retrieval_metrics
from app.rag.processing import chunk_blocks
from app.rag.qdrant_store import QdrantVectorStore
from app.rag.repositories.postgres import RAGRepository
from app.rag.repositories.tables import chunks, generations
from app.rag.vector_store import VectorChunk
from app.rag.reranker import LocalReranker
from app.rag.schemas import SearchRequest
from app.rag.service import RAGService
from app.rag.worker import IngestionWorker
from testing.files import create_test_files
from testing.identities import TEST_LEARNERS, learner_id
from testing.postgres import PostgresSandbox
from testing.retrieval_corpus import corpus
from testing.process_resources import ProcessResources


def percentiles(values):
    ordered = sorted(values)
    return dict(samples=len(values), p50=statistics.median(values),
        p95=ordered[math.ceil(.95*len(values))-1], p99=ordered[math.ceil(.99*len(values))-1], raw=values)


def paired_interval(before, after, *, seed=1701):
    rng = random.Random(seed)
    diffs = [b-a for a,b in zip(before, after, strict=True)]
    means = sorted(statistics.mean(rng.choices(diffs, k=len(diffs))) for _ in range(1000))
    return dict(mean=statistics.mean(diffs), lower=means[24], upper=means[974], seed=seed)


def source_means(rows):
    groups={}
    for row in rows:
        if row['split']=='heldout' and row['supported']:
            groups.setdefault(row['id'].split('-q')[0],[]).append(row['recall'])
    return [statistics.mean(groups[key]) for key in sorted(groups)]


def main():
    import os
    import resource
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--load-only', action='store_true')
    args = parser.parse_args()
    if args.output.exists():
        raise RuntimeError('Evidence output already exists; use a fresh run filename.')
    settings = Settings(_env_file=None, qdrant_url=os.environ['TEST_QDRANT_URL'], qdrant_api_key='test-only',
        qdrant_collection='mentra_completion_'+uuid4().hex, rag_reranker_path='', rag_inference_wait_seconds=2,
        embedding_worker_timeout=60)
    embedding = ProcessEmbeddingService(settings)
    client = QdrantClient(url=settings.qdrant_url)
    vector = QdrantVectorStore(settings, embedding, client)
    ranker = LocalReranker('/opt/mentra/models/reranker', 5)
    documents, queries = corpus()
    report = dict(seed=1701, scope='synthetic learning workflow corpus; not a production distribution estimate',
        corpus_sha256=hashlib.sha256(json.dumps([documents,queries],sort_keys=True).encode()).hexdigest(),
        documents=len(documents), queries=len(queries), embedding=embedding.model_name,
        revision=embedding.model_version, dimension=embedding.dimension, quality={}, load={})
    resources=ProcessResources(); resources.__enter__()
    try:
        with PostgresSandbox() as db:
            learner = LearnerEngine(db.repository)
            owner = learner_id(TEST_LEARNERS[0])
            contexts = {split: learner.resolve_learning_context(ResolveLearningContextRequest(
                learner_id=owner, name=split, activate=True)).context_id for split in ('calibration','heldout')}
            files = create_test_files(db.sessions, settings)
            service = RAGService(RAGRepository(db.sessions, files), learner, embedding, vector, files, settings)
            worker = IngestionWorker(service)
            ids, reverse = {}, {}
            for document in documents:
                file = files.upload(owner, io.BytesIO(document['text'].encode()), document['id']+'.txt', 'library', document['id'])
                accepted = service.accept_extracted(owner, file_id=file['id'], filename=document['id']+'.txt',
                    title=document['id'], context_ids=[contexts[document['split']]], key=document['id'],
                    extracted=dict(blocks=[dict(text=document['text'])], warnings=[], reader_revision='judgments-v1'))
                worker.run_once()
                assert service.repository.get_job(owner, accepted['job_id'])['state'] == 'SUCCEEDED'
                ids[document['id']] = accepted['document_id']
                reverse[accepted['document_id']] = document['id']
            if not args.load_only:
                report['warmup'] = {}
                stamp=time.perf_counter(); report['warmup']['ok']=ranker.warmup()
                report['warmup']['seconds']=time.perf_counter()-stamp
                assert report['warmup']['ok']
                details = {}
                variants=[('dense',False,0,'simple'), ('hybrid',True,0,'simple'),
                        ('structured',True,0,'structured'), ('rerank10',True,10,'simple'),
                        ('rerank20',True,20,'simple'), ('rerank40',True,40,'simple')]
                random.Random(1701).shuffle(variants)
                report['variant_order']=[v[0] for v in variants]
                for mode, hybrid, cap, policy in variants:
                    service.settings=settings.model_copy(update=dict(rag_hybrid_enabled=hybrid,
                        rag_reranker_max_candidates=cap or 20, rag_lexical_policy=policy))
                    service.reranker = ranker if cap else None
                    observations=[]
                    for item in queries:
                        service._query_cache.clear(); service._candidate_cache=ReadCache()
                        result=service.search(owner, SearchRequest(query=item['query'], context_ids=[contexts[item['split']]], limit=3))
                        ranked=[reverse[c.source.document_id] for c in result.chunks]
                        metric=retrieval_metrics(item['relevant_source_ids'],ranked,3)
                        relevant=item['relevant_source_ids']
                        support=next((d['text'][d['support']['start']:d['support']['end']] for d in documents if d['id'] in relevant),None)
                        observations.append(dict(id=item['id'], split=item['split'], language=item['language'], **metric,
                            supported=bool(relevant), returned=bool(ranked), top_score=result.chunks[0].score if result.chunks else None,
                            support_span_found=bool(support and any(support in c.content for c in result.chunks)),
                            elapsed_ms=result.diagnostics.timings_ms['total'], degraded=result.status=='degraded'))
                    details[mode]=observations
                    print(f'Completed quality variant {mode}',flush=True)
                    held=[o for o in observations if o['split']=='heldout']; answerable=[o for o in held if o['supported']]
                    report['quality'][mode]=dict(answerable={k:statistics.mean(o[k] for o in answerable) for k in ('recall','mrr','ndcg','support_span_found')},
                        no_support_candidate_rate=statistics.mean(o['returned'] for o in held if not o['supported']),
                        language_recall={language:statistics.mean(o['recall'] for o in answerable if o['language']==language) for language in {o['language'] for o in answerable}},
                        latency_ms=percentiles([o['elapsed_ms'] for o in held]), degraded=sum(o['degraded'] for o in held))
                report['paired_recall_intervals']={mode:paired_interval(
                    source_means(details['dense']),source_means(rows)) for mode,rows in details.items() if mode!='dense'}
                report['bootstrap_unit']='source; all paraphrases grouped'
                # Select on calibration sources only; test exactly once on held-out sources.
                calibration=[o for o in details['rerank20'] if o['split']=='calibration']
                positive=[o['top_score'] for o in calibration if o['supported'] and o['top_score'] is not None]
                threshold=min(positive)
                held=[o for o in details['rerank20'] if o['split']=='heldout']
                false_abstention=statistics.mean(o['top_score'] is None or o['top_score']<threshold for o in held if o['supported'])
                false_support=statistics.mean(o['top_score'] is not None and o['top_score']>=threshold for o in held if not o['supported'])
                report['support_gate']=dict(calibration_threshold=threshold, heldout_false_abstention=false_abstention,
                    heldout_false_support=false_support, adopted=False,
                    decision='opt-in only; synthetic calibration is insufficient for a universal production cutoff')
                report['observations']=details
                print('Quality comparison complete', flush=True)
            # Context/cache/concurrency matrix: no quality conclusions from timing queries.
            service.reranker=None; service.settings=settings
            for size in (100,1000,10000):
                print(f'Load cohort {size}', flush=True)
                with db.sessions() as session:
                    count=session.scalar(select(func.count()).select_from(chunks))
                    seed=dict(session.execute(select(chunks).where(chunks.c.document_id==ids['study-05']).limit(1)).mappings().one())
                    ordinal=session.scalar(select(func.max(chunks.c.ordinal)).where(chunks.c.generation_id==seed['generation_id']))+1
                vector_value=embedding.embed_documents([seed['content']])[0]
                for start in range(count,size,250):
                    batch=[dict(seed,id=str(uuid4()),ordinal=ordinal+i) for i in range(min(250,size-start))]
                    ordinal+=len(batch)
                    with db.sessions.begin() as session:
                        session.execute(chunks.insert(),batch)
                        session.execute(update(generations).where(generations.c.id==seed['generation_id']).values(chunk_count=ordinal))
                    vector.upsert_chunks([VectorChunk(row['id'],owner,row['document_id'],row['generation_id'],
                        [contexts['heldout']],vector_value) for row in batch])
                for cache in ('cold','query','candidates'):
                  for concurrency in (1,2,4,8):
                    service._query_cache.clear(); service._candidate_cache=ReadCache(ttl=0 if cache!='candidates' else 120)
                    question='What does SQLSTATE 23505 mean?'
                    if cache!='cold':
                        service.search(owner,SearchRequest(query=question,context_ids=[contexts['heldout']]))
                    def timed(i):
                        query=question+f' Lookup {i}.' if cache=='cold' else question
                        start=time.perf_counter()
                        result=service.search(owner,SearchRequest(query=query,context_ids=[contexts['heldout']]))
                        return (time.perf_counter()-start)*1000,result.status
                    with ThreadPoolExecutor(max_workers=concurrency) as pool:
                        samples=list(pool.map(timed,range(32)))
                    report['load'][f'{size}:{cache}:{concurrency}']=dict(latency_ms=percentiles([s[0] for s in samples]),
                        degraded=sum(s[1]=='degraded' for s in samples))
            with db.sessions() as session:
                report['lexical_explain']=session.execute(text("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) SELECT id FROM rag_chunk WHERE to_tsvector('simple',content) @@ websearch_to_tsquery('simple','SQLSTATE OR 23505')")).scalar()
            # Exact tokenization/chunk boundary cost; production remains block-v2.
            report['chunking']={}
            long_text=('The course explains source provenance and reliable retrieval. '*100)
            for target in (250,350,450):
                stamp=time.perf_counter()
                # Direct tokenizer engine is available only inside the worker; compare
                # legacy per-count IPC with the equivalent single worker operation.
                old=chunk_blocks([dict(text=long_text)],embedding,owner,'benchmark',str(uuid4()),5000,120,target_tokens=target)
                report['chunking'][str(target)]=dict(chunks=len(old),elapsed_ms=(time.perf_counter()-stamp)*1000,
                    coverage=''.join(c['content'] for c in old)==long_text)
            generation=str(uuid4()); stamp=time.perf_counter()
            local=embedding.chunk_blocks([dict(text=long_text)],owner,'benchmark',generation,5000,120)
            report['chunking']['colocated']=dict(chunks=len(local),elapsed_ms=(time.perf_counter()-stamp)*1000,
                coverage=''.join(c['content'] for c in local)==long_text)
            report['parent_peak_rss_mib']=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024
            service.reranker=None
            files.close()
    finally:
        resources.__exit__()
        report['sampled_process_tree_peak_rss_mib']=resources.peak_mib
        ranker.close(); embedding.close()
        if client.collection_exists(settings.qdrant_collection): client.delete_collection(settings.qdrant_collection)
        client.close()
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k in ('documents','queries','quality','support_gate','chunking')},indent=2))


if __name__=='__main__':
    main()
