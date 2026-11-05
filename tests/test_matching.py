import unittest

from app.matching import cosine_similarity, validated_embedding
from app.observability import request_id_from_header, trace_context


class MatchingTests(unittest.TestCase):
    def test_same_embedding_has_full_similarity(self):
        self.assertAlmostEqual(cosine_similarity((0.2, 0.8), (0.2, 0.8)), 1.0)

    def test_orthogonal_embeddings_are_not_similar(self):
        self.assertAlmostEqual(cosine_similarity((1.0, 0.0), (0.0, 1.0)), 0.0)

    def test_embedding_validation_rejects_wrong_dimension(self):
        with self.assertRaisesRegex(ValueError, "dimension"):
            validated_embedding((1.0,), 2)


class ObservabilityTests(unittest.TestCase):
    def test_request_id_rejects_log_injection(self):
        self.assertNotEqual(request_id_from_header("bad\nvalue"), "bad\nvalue")

    def test_traceparent_preserves_trace_id(self):
        trace_id, outgoing = trace_context("00-0123456789abcdef0123456789abcdef-0123456789abcdef-01")
        self.assertEqual(trace_id, "0123456789abcdef0123456789abcdef")
        self.assertTrue(outgoing.startswith(f"00-{trace_id}-"))


if __name__ == "__main__":
    unittest.main()
