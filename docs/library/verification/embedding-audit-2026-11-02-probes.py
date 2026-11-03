"""Offline audit reproductions. Run from repo root with PYTHONPATH=backend.

Uses production selection/chunking/reranker code with explicit fake dependencies.
No network, provider, database, model downloads or application data mutations.
These are baseline observations, not assertions that bugs are desired behavior.
"""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock
from uuid import uuid4

from app.core.config import Settings
from app.rag.service import RAGService
from app.rag.schemas import SearchRequest
from app.rag.processing import chunk_blocks
from app.rag.reranker import LocalReranker
from app.rag.vector_store import VectorMatch


class Embedding:
    model_name, model_version, dimension, max_tokens = 'audit-fake', '1', 3, 512
    def token_count(self, text):
        return len(text.split()) + 2
    query_token_count = token_count
    def embed_query(self, text):
        return [1., 0., 0.]


def search_case(kind, rerank):
    rows = []
    for i in range(30):
        doc = 'doc-a' if i < 20 else 'doc-b'
        content = ('duplicate' if kind == 'duplicates' and i < 20 else f'passage {i}')
        rows.append(dict(id=str(i), document_id=doc, generation_id=doc+'-gen',
            version_id=doc+'-v', title=doc, heading_path=[], spans=[], warnings=[],
            content=content, content_hash=hashlib.sha256(content.encode()).hexdigest(),
            concept_ids=[], token_count=450 if kind == 'budget' and i < 20 else 10))
    docs = [dict(id=d, active_generation_id=d+'-gen', context_ids=['ctx'], concept_ids=[], revision=1)
            for d in ['doc-a', 'doc-b']]
    repo = NS(hydrate=lambda *a: rows, lexical=lambda *a: [], record_usage=Mock())
    vector = NS(collection_name='offline', query_chunks=lambda *a: [VectorMatch(r['id'], 1-i/100) for i,r in enumerate(rows)])
    service = RAGService(repo, None, Embedding(), vector, None,
        Settings(_env_file=None, rag_hybrid_enabled=False, rag_reranker_path=''), parser=NS(version='fake'))
    service._eligible = lambda *a, **kw: (['ctx'], docs)
    if rerank:
        service.reranker = NS(rank=lambda q, p: list(range(len(p), 0, -1)))
    if kind == 'usage_failure':
        repo.record_usage.side_effect = RuntimeError('synthetic metadata write failure')
    try:
        result = service.search('owner', SearchRequest(query='query', limit=8, token_budget=100 if kind == 'budget' else 2400))
        return dict(count=len(result.chunks), documents=sorted({r.source.document_id for r in result.chunks}), status=result.status)
    except Exception as error:
        return dict(error=type(error).__name__, message=str(error))


def main():
    result = {'method': 'production Python code, deterministic fake dependencies; not model quality or latency evidence'}
    result['selection'] = {kind: {mode: search_case(kind, enabled) for mode, enabled in [('dense', False), ('reranked', True)]}
        for kind in ['diversity', 'duplicates', 'budget', 'usage_failure']}
    tokenizer = NS(encode=lambda query, passage=None, **kw: [0] * (len(query) + len(passage or '') + 3))
    ranker = LocalReranker('unused', 1)
    predict = Mock(return_value=[1.])
    ranker._model = NS(tokenizer=tokenizer, predict=predict)
    passage = 'a' * 500 + ' ANSWER_AT_END'
    ranker._rank('query', [passage])
    actual = predict.call_args.args[0][0][1]
    result['reranker_tail'] = dict(original_characters=len(passage), scored_characters=len(actual), answer_visible='ANSWER_AT_END' in actual)
    try:
        ranker._rank('q' * 238, ['answer'])
    except ValueError as error:
        result['reranker_long_query'] = str(error)
    ranker.close()
    emb = Embedding()
    emb.token_count = Mock(side_effect=emb.token_count)
    blocks = [dict(text='a short paragraph') for _ in range(100)]
    chunks = chunk_blocks(blocks, emb, 'owner', 'doc', str(uuid4()), 5000)
    result['short_blocks'] = dict(blocks=100, chunks=len(chunks), token_count_calls=emb.token_count.call_count,
        total_embedding_tokens=sum(c['token_count'] for c in chunks))
    emb.token_count.reset_mock()
    chunks = chunk_blocks([dict(text='word ' * 10000)], emb, 'owner', 'doc', str(uuid4()), 5000)
    result['long_block'] = dict(chunks=len(chunks), token_count_calls=emb.token_count.call_count,
        character_coverage=sum(len(c['content']) for c in chunks), original_characters=50000)
    target = Path(__file__).with_name('embedding-audit-2026-11-02-probes.json')
    target.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
