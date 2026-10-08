import unittest
from uuid import uuid4
from app.rag.processing import chunk_blocks, reciprocal_rank_fusion
from app.rag.evaluation import retrieval_metrics
from app.rag.errors import ExtractionError


class CharacterEmbedding:
    max_tokens = 32
    def token_count(self, text):
        return len(text) + 2


class ProcessingTests(unittest.TestCase):
    def test_short_block_only_tokenizes_once_and_preserves_offsets(self):
        from unittest.mock import Mock
        embedding = CharacterEmbedding()
        embedding.token_count = Mock(side_effect=embedding.token_count)
        text = '    return wrapper'
        chunks = chunk_blocks([dict(text=text)], embedding, 'owner', 'doc', str(uuid4()), 100)
        self.assertEqual(chunks[0]['content'], text)
        self.assertEqual(chunks[0]['spans'][0]['end'], len(text))
        self.assertEqual(chunks[0]['token_count'], len(text) + 2)
        embedding.token_count.assert_called_once_with(text)

    def test_exact_token_budget_preserves_every_source_character(self):
        text = 'Decorators add behavior.\nCode and formulas: x = y + 2.'
        chunks = chunk_blocks([dict(text=text, page=3, language='ts')], CharacterEmbedding(), 'owner', 'doc', str(uuid4()), 100)
        self.assertEqual(''.join(c['content'] for c in chunks), text)
        self.assertTrue(all(c['token_count'] <= 30 for c in chunks))
        self.assertEqual(chunks[-1]['spans'][0]['end'], len(text))
        self.assertTrue(all(c['spans'][0]['page'] == 3 for c in chunks))
        self.assertTrue(all(c['spans'][0]['language'] == 'ts' for c in chunks))

    def test_empty_extraction_fails(self):
        with self.assertRaises(ExtractionError):
            chunk_blocks([dict(text=' ')], CharacterEmbedding(), 'owner', 'doc', str(uuid4()), 100)

    def test_fusion_uses_ranks_and_deduplicates_each_branch(self):
        result = reciprocal_rank_fusion([['a','a','b'], ['b','c']])
        self.assertEqual(result[0][0], 'b')
        self.assertEqual(len(result), 3)

    def test_evaluation_counts_unique_sources(self):
        scores = retrieval_metrics(['a','b'], ['a','a','x','b'], 3)
        self.assertEqual(scores['recall'], 1)
        self.assertEqual(scores['precision'], 2/3)
        self.assertEqual(scores['mrr'], 1)
