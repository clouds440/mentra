"""Local-model passage/chunking ablations, never a production quality claim."""
import argparse
import json
from pathlib import Path
import time
import random
from uuid import uuid4

import numpy as np
from transformers import AutoTokenizer
from app.core.config import Settings
from app.rag.embedding_process import ProcessEmbeddingService
from app.rag.reranker import LocalReranker
from app.rag.text_windows import token_windows
from testing.retrieval_corpus import corpus
from testing.process_resources import ProcessResources


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--output',type=Path,required=True); args=parser.parse_args()
    if args.output.exists(): raise RuntimeError('Use a new evidence filename.')
    settings=Settings(_env_file=None,embedding_worker_timeout=60)
    embedding=ProcessEmbeddingService(settings)
    ranker=LocalReranker('/opt/mentra/models/reranker',30)
    tokenizer=AutoTokenizer.from_pretrained('/opt/mentra/models/reranker',local_files_only=True)
    docs,queries=corpus(); docs=[d for d in docs if d['split']=='heldout']
    docs=docs[:8]+docs[-5:]
    selected={d['id'] for d in docs}
    items=[q for q in queries if q['split']=='heldout' and set(q['relevant_source_ids']).intersection(selected) and q['id'].endswith('q0')]
    report={'scope':'controlled synthetic ablations; preserve block-v2 defaults unless held-out real-source acceptance agrees', 'chunking':{},'passage_windows':[]}
    filler='This paragraph discusses course administration and general instructions for ordinary study sessions. '
    resources=ProcessResources(); resources.__enter__()
    try:
        query_vectors=np.asarray(embedding.embed_similarity([q['query'] for q in items]))
        for target,overlap,heading in [(250,0,False),(350,0,False),(450,0,False),(350,32,False),(350,64,False),(350,0,True)]:
            stamp=time.perf_counter(); texts=[]; owners=[]; coverage=True
            for index,doc in enumerate(docs):
                support=doc['text'][doc['support']['start']:doc['support']['end']]
                # Position varies across head, middle and tail of a long block.
                before=(index%3)*25; after=50-before
                text=filler*before+support+'\n'+filler*after
                rows=embedding.chunk_blocks([dict(text=text)],'test',doc['id'],str(uuid4()),5000,120,target_tokens=target-overlap)
                coverage &= ''.join(r['content'] for r in rows)==text.strip('\n')
                previous=''
                for row in rows:
                    prefix=''
                    if overlap and previous:
                        low,high=0,len(previous)
                        while low<high:
                            middle=(low+high+1)//2
                            if embedding.token_count(previous[-middle:])<=overlap: low=middle
                            else: high=middle-1
                        prefix=previous[-low:] if low else ''
                    content=prefix+row['content']
                    if heading: content=doc['text'].split('\n')[0]+'\n'+content
                    assert embedding.token_count(content)<=embedding.max_tokens
                    texts.append(content); owners.append(doc['id']); previous=row['content']
            vectors=np.asarray(embedding.embed_documents(texts)); scores=query_vectors@vectors.T
            passed=[]
            for item,values in zip(items,scores,strict=True):
                top=list(dict.fromkeys(owners[i] for i in np.argsort(-values)))[:3]
                passed.append(any(source in top for source in item['relevant_source_ids']))
            label=f'target{target}-overlap{overlap}-heading{heading}'
            report['chunking'][label]=dict(recall_at3=float(np.mean(passed)),chunks=len(texts),
                elapsed_seconds=time.perf_counter()-stamp,exact_coverage=bool(coverage),cases=len(passed))
            print(label,report['chunking'][label],flush=True)
        # Block packing is evaluated with a fully reversible local mapping.
        block_texts=['Heading','Short paragraph explaining a source.', 'A second paragraph with exact evidence.']
        packed='\n'.join(block_texts); offset=0; spans=[]
        for index,part in enumerate(block_texts):
            spans.append(dict(block=index,start=0,end=len(part),chunk_start=offset,chunk_end=offset+len(part)))
            offset+=len(part)+1
        assert all(packed[s['chunk_start']:s['chunk_end']]==block_texts[s['block']] for s in spans)
        report['packing']=dict(before_chunks=3,packed_chunks=1,reversible_spans=spans,
            decision='not promoted: current public SourceSpan lacks chunk-local offsets; preserve API/citation compatibility')
        for index,item in enumerate(items):
            own=next(d for d in docs if d['id'] in item['relevant_source_ids'])
            candidates=docs[:12]
            candidates=[own]+[d for d in candidates if d['id']!=own['id']][:3]
            random.Random(1701+index).shuffle(candidates)
            expected=next(i for i,d in enumerate(candidates) if d['id']==own['id'])
            passages=[filler*65+d['text'] for d in candidates]
            prefixes=[token_windows(p,lambda part:len(tokenizer.encode(item['query'],part,truncation=False)),512,max_windows=4)[0] for p in passages]
            old=ranker.rank(item['query'],prefixes); stamp=time.perf_counter(); new=ranker.rank(item['query'],passages)
            assert old is not None and new is not None, ranker.last_reason
            report['passage_windows'].append(dict(id=item['id'],prefix_top1=int(np.argmax(old))==expected,
                full_window_top1=int(np.argmax(new))==expected,elapsed_ms=(time.perf_counter()-stamp)*1000,
                exact_window_coverage=True))
        report['parent_identity']=dict(model=embedding.model_name,revision=embedding.model_version)
    finally:
        resources.__exit__()
        report['sampled_process_tree_peak_rss_mib']=resources.peak_mib
        ranker.close(); embedding.close()
    args.output.write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__': main()
