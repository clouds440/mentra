"""Real CPU E5 and local Qdrant retrieval; no external corpus or credentials needed."""
import argparse
import json
from contextlib import closing
from pathlib import Path

from qdrant_client import QdrantClient, models
from app.core.config import Settings
from app.rag.embeddings import EMBEDDING_CACHE_DIR, SentenceTransformerEmbeddingService


PASSAGES = {
    'en': ['Plants use sunlight to make food through photosynthesis.',
           'The heart pumps blood throughout the body.',
           'Gravity keeps planets in orbit around the sun.'],
    'ur': ['پودے ضیائی تالیف کے ذریعے سورج کی روشنی سے خوراک بناتے ہیں۔',
           'دل پورے جسم میں خون پمپ کرتا ہے۔',
           'کشش ثقل سیاروں کو سورج کے گرد مدار میں رکھتی ہے۔'],
    'ar': ['تستخدم النباتات ضوء الشمس لصنع الغذاء من خلال عملية البناء الضوئي.',
           'يضخ القلب الدم إلى جميع أنحاء الجسم.',
           'تحافظ الجاذبية على دوران الكواكب في مدارات حول الشمس.'],
}
QUERIES = {
    'en': ['How do plants make food?', 'Which organ circulates blood?', 'Why do planets orbit the sun?'],
    'ur': ['پودے خوراک کیسے بناتے ہیں؟', 'کون سا عضو خون کی گردش کرتا ہے؟', 'سیارے سورج کے گرد کیوں گھومتے ہیں؟'],
    'ar': ['كيف تصنع النباتات غذاءها؟', 'ما العضو الذي يضخ الدم؟', 'لماذا تدور الكواكب حول الشمس؟'],
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model-path', type=Path, default=EMBEDDING_CACHE_DIR)
    args = parser.parse_args()
    embedding = SentenceTransformerEmbeddingService(Settings(_env_file=None,
        embedding_model='intfloat/multilingual-e5-small', embedding_device='cpu'), model_path=args.model_path)
    assert embedding.dimension == 384
    results = []
    with closing(QdrantClient(':memory:')) as client:
        for language, passages in PASSAGES.items():
            client.create_collection(language, vectors_config=models.VectorParams(size=384, distance=models.Distance.COSINE))
            client.upsert(language, points=[models.PointStruct(id=i, vector=v)
                for i, v in enumerate(embedding.embed_documents(passages))])
        for language, queries in QUERIES.items():
            for expected, query in enumerate(queries):
                vector = embedding.embed_query(query)
                for corpus in PASSAGES:
                    hit = client.query_points(corpus, query=vector, limit=1).points[0]
                    results.append(dict(query_language=language, corpus_language=corpus,
                        expected=expected, actual=hit.id, score=round(hit.score, 4)))
    report = dict(model=embedding.model_name, revision=embedding.model_version, dimension=embedding.dimension,
        cases=len(results), passed=sum(r['expected'] == r['actual'] for r in results), results=results)
    print(json.dumps(report, indent=2))
    assert report['passed'] == report['cases'], 'Multilingual top-1 retrieval failed'


if __name__ == '__main__':
    main()
