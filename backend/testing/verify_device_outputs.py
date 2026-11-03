"""Compare actual CPU model outputs with frozen pre-utility implementations."""
import json
from pathlib import Path
import numpy as np
from app.core.config import Settings
from app.rag.embeddings import SentenceTransformerEmbeddingService
from app.rag.reranker import LocalReranker


def frozen(path,name):
    namespace={'__name__':'app.rag.'+name,'__package__':'app.rag'}
    exec(compile(path.read_text(encoding='utf-8'),str(path),'exec'),namespace)
    return namespace


def main():
    root=Path('.cache/system-audit')
    config=Settings(embedding_device='cpu',local_inference_device='cpu')
    old=frozen(root/'pre_fix_embeddings.py','baseline_embeddings')['SentenceTransformerEmbeddingService'](config)
    new=SentenceTransformerEmbeddingService(config)
    texts=['Gravity and force','قوت اور حرکت','القوة والحركة','力和运动','गति और बल','Fuerza y movimiento','Force et mouvement','Kraft und Bewegung','力と運動','Сила и движение']
    old_vectors=np.array(old.embed_documents(texts));new_vectors=np.array(new.embed_documents(texts))
    assert np.isfinite(new_vectors).all()
    assert np.array_equal(old_vectors,new_vectors)
    from app.rag.embedding_process import ProcessEmbeddingService
    process=ProcessEmbeddingService(config)
    try:
        process_equal=np.array_equal(np.array(process.embed_documents(texts)),new_vectors)
        assert process_equal
    finally: process.close()
    old_ranker=frozen(root/'pre_fix_reranker.py','baseline_reranker')['LocalReranker']('/opt/mentra/models/reranker',5)
    new_ranker=LocalReranker('/opt/mentra/models/reranker',5,device='cpu')
    pairs=[('gravity',['Gravity attracts masses.','Cells contain DNA.','Python has dictionaries.']),
           ('قوت اور حرکت',['قوت جسم کی حرکت بدل سکتی ہے۔','Atoms contain electrons.'])]
    rows=[]
    for query,passages in pairs:
        before=old_ranker._rank(query,passages);after=new_ranker._rank(query,passages)
        assert before==after
        rows.append(dict(passages=len(passages),scores_equal=True))
    try:
        assert new_ranker.rank(*pairs[0])==old_ranker._rank(*pairs[0])
    finally: new_ranker.close();old_ranker.close()
    print(json.dumps(dict(backend='CPU',embedding_model=new.model_name,embedding_revision=new.model_version,
        language_cases=len(texts),dimension=new.dimension,max_absolute_vector_difference=float(np.max(np.abs(old_vectors-new_vectors))),
        reranker=rows,subprocess_vectors_equal=bool(process_equal),subprocess_reranker_equal=True,
        device=new._runtime.choice.__dict__),indent=2))


if __name__=='__main__':main()
