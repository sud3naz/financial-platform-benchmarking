import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "src" / "score_platforms.py"
SPEC = importlib.util.spec_from_file_location("score_platforms", MODULE_PATH)
score_platforms = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(score_platforms)


class ScoringBoundaryTests(unittest.TestCase):
    def test_market_reach_thresholds(self):
        self.assertEqual(score_platforms.score_market_reach(9_999), 1.0)
        self.assertEqual(score_platforms.score_market_reach(10_000), 2.0)
        self.assertEqual(score_platforms.score_market_reach(100_000), 3.0)
        self.assertEqual(score_platforms.score_market_reach(1_000_000), 4.0)
        self.assertEqual(score_platforms.score_market_reach(5_000_000), 5.0)

    def test_institution_thresholds(self):
        self.assertEqual(score_platforms.score_institution_coverage(1), 1.0)
        self.assertEqual(score_platforms.score_institution_coverage(2), 2.0)
        self.assertEqual(score_platforms.score_institution_coverage(5), 3.0)
        self.assertEqual(score_platforms.score_institution_coverage(10), 4.0)
        self.assertEqual(score_platforms.score_institution_coverage(15), 5.0)

    def test_evidence_completeness_thresholds(self):
        self.assertEqual(score_platforms.score_evidence_completeness(0.49), 1.0)
        self.assertEqual(score_platforms.score_evidence_completeness(0.50), 2.0)
        self.assertEqual(score_platforms.score_evidence_completeness(0.70), 3.0)
        self.assertEqual(score_platforms.score_evidence_completeness(0.85), 4.0)
        self.assertEqual(score_platforms.score_evidence_completeness(0.95), 5.0)


if __name__ == "__main__":
    unittest.main()
