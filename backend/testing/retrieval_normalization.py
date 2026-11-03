"""Exact remote/local chunking equivalence and normalization acceptance."""
import argparse
import json
from pathlib import Path
import time
from uuid import uuid4
from app.core.config import Settings
from app.rag.embedding_process import ProcessEmbeddingService
from app.rag.processing import chunk_blocks
from testing.retrieval_corpus import corpus


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--output',type=Path,required=True); args=parser.parse_args()
    if args.output.exists(): raise RuntimeError('Use a fresh evidence path.')
    engine=ProcessEmbeddingService(Settings(_env_file=None))
    filler='This paragraph discusses course administration and general instructions for ordinary study sessions. '
    report={'cases':0,'normalized_coverage':True,'spans_valid':True}
    try:
        for index,doc in enumerate(d for d in corpus()[0] if d['split']=='heldout'):
            support=doc['text'][doc['support']['start']:doc['support']['end']]
            before=(index%3)*25; original=filler*before+support+'\n'+filler*(50-before)
            normalized=original.replace('\r\n','\n').replace('\r','\n').strip('\n')
            for target in (250,350,450):
                rows=engine.chunk_blocks([dict(text=original)],'test','doc',str(uuid4()),5000,120,target_tokens=target)
                assert ''.join(row['content'] for row in rows)==normalized
                assert all(normalized[row['spans'][0]['start']:row['spans'][0]['end']]==row['content'] for row in rows)
                report['cases']+=1
        generation=str(uuid4()); blocks=[dict(text=filler*50)]
        stamp=time.perf_counter(); legacy=chunk_blocks(blocks,engine,'test','doc',generation,5000)
        report['legacy_ipc_ms']=(time.perf_counter()-stamp)*1000
        stamp=time.perf_counter(); colocated=engine.chunk_blocks(blocks,'test','doc',generation,5000,120)
        report['colocated_ms']=(time.perf_counter()-stamp)*1000
        assert legacy==colocated
        report['exact_remote_local_equivalence']=True
    finally: engine.close()
    args.output.write_text(json.dumps(report,indent=2)+'\n'); print(json.dumps(report))


if __name__=='__main__': main()
