"""Portable held-out retrieval metrics; judgments refer to sources, not chunk IDs."""
import argparse
import json
import math
from pathlib import Path


def retrieval_metrics(relevant, ranked, k=8):
    relevant = set(relevant)
    ranked = list(dict.fromkeys(ranked))[:k]
    hits = [1 if doc in relevant else 0 for doc in ranked]
    first = next((i + 1 for i, hit in enumerate(hits) if hit), None)
    dcg = sum(hit / math.log2(i + 2) for i, hit in enumerate(hits))
    ideal = sum(1 / math.log2(i + 2) for i in range(min(len(relevant), k)))
    return dict(recall=sum(hits) / len(relevant) if relevant else 0,
                precision=sum(hits) / k, mrr=1 / first if first else 0,
                ndcg=dcg / ideal if ideal else 0)


def evaluate(items, search, k=8):
    scores = []
    for item in items:
        result = search(item)
        metrics = retrieval_metrics(item['relevant_source_ids'], result, k)
        scores.append(dict(id=item['id'], **metrics, no_answer_returned_sources=len(result) if not item['relevant_source_ids'] else None,
            excluded_source_violations=len(set(result).intersection(item.get('excluded_source_ids', [])))))
    answerable = [s for s in scores if s['no_answer_returned_sources'] is None]
    no_answer = [s for s in scores if s['no_answer_returned_sources'] is not None]
    def mean(rows):
        return {key: sum(s[key] for s in rows) / len(rows) if rows else 0 for key in ('recall','precision','mrr','ndcg')}
    return dict(k=k, cases=scores, mean=mean(scores), answerable_mean=mean(answerable),
        no_answer_queries=len(no_answer), no_answer_candidate_rate=sum(s['no_answer_returned_sources'] > 0 for s in no_answer) / len(no_answer) if no_answer else None)


def main():
    parser = argparse.ArgumentParser(description='Compare held-out source rankings from dense/hybrid/reranked/tuned runs.')
    parser.add_argument('judgments', type=Path)
    parser.add_argument('rankings', type=Path, help='JSON mapping query IDs to ranked source IDs; no private source text.')
    parser.add_argument('--k', type=int, default=8)
    args = parser.parse_args()
    if not 1 <= args.k <= 100:
        parser.error('k must be between 1 and 100')
    items = json.loads(args.judgments.read_text(encoding='utf-8'))
    rankings = json.loads(args.rankings.read_text(encoding='utf-8'))
    if any(item['id'] not in rankings for item in items):
        parser.error('Every held-out query must have a ranking entry, including no-match queries')
    print(json.dumps(evaluate(items, lambda item: rankings[item['id']], args.k), indent=2))


if __name__ == '__main__':
    main()
