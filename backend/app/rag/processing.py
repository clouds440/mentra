"""Deterministic block-aware chunks with recoverable normalized source offsets."""
import hashlib
import time
from uuid import UUID, uuid5
from app.rag.errors import ExtractionError

CHUNKER_VERSION = 'block-token-v1'


def chunk_blocks(blocks, embedding, owner, document_id, generation_id, max_chunks, max_seconds=120):
    items = []
    deadline = time.monotonic() + max_seconds
    ceiling = min(450, embedding.max_tokens - 2)
    for number, block in enumerate(blocks):
        text = block['text'].replace('\r\n', '\n').replace('\r', '\n').strip('\n')
        if not text.strip():
            continue
        start = 0
        while start < len(text):
            if time.monotonic() > deadline:
                raise ExtractionError('Chunking exceeded the time limit. Split the material into smaller files.')
            # Binary search the exact tokenizer limit; never assume characters=tokens.
            low, high = 1, min(len(text) - start, ceiling * 8, 4096)
            counts = {}
            def tokens(length):
                if length not in counts:
                    counts[length] = embedding.token_count(text[start:start + length])
                return counts[length]
            if tokens(high) <= ceiling:
                low = high
            while low < high:
                mid = (low + high + 1) // 2
                if tokens(mid) <= ceiling:
                    low = mid
                else:
                    high = mid - 1
            end = start + low
            if end < len(text):
                cut = max(text.rfind('\n', start, end), text.rfind('. ', start, end), text.rfind(' ', start, end))
                if cut > start + low // 2:
                    end = cut + 1
            content = text[start:end]
            token_count = tokens(end - start)
            if token_count > ceiling:
                raise ExtractionError('A source unit cannot fit the embedding budget.')
            span = dict(block=number, start=start, end=end, page=block.get('page'),
                        slide=block.get('slide'), method=block.get('method', 'native'))
            ordinal = len(items)
            items.append(dict(id=str(uuid5(UUID(generation_id), str(ordinal))), learner_id=owner,
                document_id=document_id, generation_id=generation_id, ordinal=ordinal, content=content,
                content_hash=hashlib.sha256(content.encode()).hexdigest(), heading_path=block.get('heading_path', []),
                spans=[span], token_count=token_count, concept_ids=[]))
            if len(items) > max_chunks:
                raise ExtractionError('Material exceeds the chunk limit. Split it into smaller files.')
            start = end
    if not items:
        raise ExtractionError('No usable text was extracted from this material.')
    return items


def reciprocal_rank_fusion(branches, constant=60):
    scores = {}
    for branch in branches:
        for rank, key in enumerate(dict.fromkeys(branch), 1):
            scores[key] = scores.get(key, 0.0) + 1.0 / (constant + rank)
    return sorted(scores.items(), key=lambda pair: (-pair[1], pair[0]))
