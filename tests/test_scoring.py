import csv
import importlib.util
import tempfile
import unittest
from pathlib import Path

import pandas as pd


MODULE_PATH = Path(__file__).resolve().parents[1] / "src" / "score_platforms.py"
SPEC = importlib.util.spec_from_file_location("score_platforms", MODULE_PATH)
score_platforms = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(score_platforms)


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


class ScoringBoundaryTests(unittest.TestCase):
    def test_institution_thresholds(self):
        expected = {1: 1.0, 2: 2.0, 5: 3.0, 10: 4.0, 15: 5.0}
        for value, score in expected.items():
            with self.subTest(value=value):
                self.assertEqual(score_platforms.score_institution_coverage(value), score)

    def test_product_breadth_is_capped_at_five(self):
        self.assertEqual(score_platforms.score_product_breadth(1), 1.0)
        self.assertEqual(score_platforms.score_product_breadth(4), 4.0)
        self.assertEqual(score_platforms.score_product_breadth(8), 5.0)

    def test_source_diversity_thresholds(self):
        expected = {1: 1.0, 2: 2.0, 3: 3.0, 4: 4.0, 5: 5.0, 20: 5.0}
        for value, score in expected.items():
            with self.subTest(value=value):
                self.assertEqual(score_platforms.score_source_diversity(value), score)

    def test_only_valid_http_urls_are_accepted(self):
        self.assertEqual(
            score_platforms.normalize_http_url(" HTTPS://Example.COM/source "),
            "https://example.com/source",
        )
        self.assertEqual(
            score_platforms.normalize_http_url("https://example.com/#overview"),
            "https://example.com",
        )
        for invalid in ("", "example.com", "ftp://example.com", "https://", "not a url"):
            with self.subTest(value=invalid):
                self.assertIsNone(score_platforms.normalize_http_url(invalid))


class ScoreAggregationTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temporary_directory.name)
        self._write_fixture()

    def tearDown(self):
        self.temporary_directory.cleanup()

    def _write_fixture(self):
        platforms = [
            ("alpha", "Alpha", "Lending"),
            ("beta", "Beta", "Lending"),
            ("gamma", "Gamma", "Insurance"),
            ("need-product", "Needs Product", "Lending"),
            ("need-source", "Needs Source", "Insurance"),
            ("need-both", "Needs Both", "Insurance"),
            ("outside", "Outside", "Kapsam dışı"),
            ("benchmark", "International Benchmark", "Lending"),
        ]
        write_csv(
            self.data_dir / "platforms.csv",
            ["platform_id", "platform_name", "country", "segment", "category", "website"],
            [
                {
                    "platform_id": platform_id,
                    "platform_name": name,
                    "country": "ABD" if platform_id == "benchmark" else "Türkiye",
                    "segment": segment,
                    "category": "Test",
                    "website": f"https://{platform_id}.example",
                }
                for platform_id, name, segment in platforms
            ],
        )

        observations = [
            ("alpha", "Loan", "Bank A", "HTTPS://ALPHA.EXAMPLE/one"),
            ("alpha", "Card", "Bank B", "https://alpha.example/two"),
            ("alpha", " card ", " bank b ", ""),
            (
                "alpha",
                "Loan",
                "Tanımlanamayan banka (kod 1)",
                "",
            ),
            ("beta", "Loan", "Bank A", "https://beta.example/one"),
            ("gamma", "Loan", "Bank A", "https://gamma.example/one"),
            ("gamma", "Card", "Bank B", ""),
            ("gamma", "Deposit", "Bank C", ""),
            ("gamma", "Loan", "Bank D", ""),
            ("gamma", "Card", "Bank E", ""),
            ("need-source", "Loan", "Bank A", "ftp://need-source.example/source"),
            ("outside", "Loan", "Bank A", "https://outside.example/source"),
            ("benchmark", "Loan", "Bank A", "https://benchmark.example/source"),
        ]
        write_csv(
            self.data_dir / "platform_observations.csv",
            ["platform_id", "product", "institution", "source_url"],
            [
                {
                    "platform_id": platform_id,
                    "product": product,
                    "institution": institution,
                    "source_url": source_url,
                }
                for platform_id, product, institution, source_url in observations
            ],
        )

        sources = [
            ("alpha", "https://alpha.example/one"),
            ("alpha", "https://alpha.example/three"),
            ("alpha", "mailto:research@example.com"),
            ("beta", "https://beta.example/two"),
            ("beta", "https://beta.example/three"),
            ("beta", "https://beta.example/four"),
            ("beta", "https://beta.example/five"),
            ("need-product", "https://need-product.example/source"),
            ("need-source", "not-a-url"),
            ("outside", "https://outside.example/source"),
            ("benchmark", "https://benchmark.example/source"),
        ]
        write_csv(
            self.data_dir / "sources.csv",
            ["platform_id", "source_url"],
            [
                {"platform_id": platform_id, "source_url": source_url}
                for platform_id, source_url in sources
            ],
        )
        self._write_weights(45, 35, 20)

    def _write_weights(self, institution: int, product: int, sources: int):
        write_csv(
            self.data_dir / "scoring_weights.csv",
            ["criterion", "weight", "description"],
            [
                {
                    "criterion": "institution_coverage",
                    "weight": institution,
                    "description": "test",
                },
                {
                    "criterion": "product_breadth",
                    "weight": product,
                    "description": "test",
                },
                {
                    "criterion": "source_diversity",
                    "weight": sources,
                    "description": "test",
                },
            ],
        )

    def _scores_by_id(self):
        return score_platforms.build_scores(self.data_dir).set_index("platform_id")

    def test_aggregates_products_institutions_and_sources(self):
        scores = self._scores_by_id()
        alpha = scores.loc["alpha"]
        self.assertEqual(alpha["observation_count"], 4)
        self.assertEqual(alpha["product_count"], 2)
        self.assertEqual(alpha["institution_count"], 2)
        self.assertEqual(alpha["distinct_source_count"], 3)
        self.assertEqual(alpha["institution_coverage_score"], 2.0)
        self.assertEqual(alpha["product_breadth_score"], 2.0)
        self.assertEqual(alpha["source_diversity_score"], 3.0)
        self.assertAlmostEqual(alpha["total_score"], 2.2)

    def test_assigns_mutually_exclusive_data_statuses(self):
        scores = self._scores_by_id()
        expected = {
            "alpha": "ranked",
            "need-product": "needs_product_data",
            "need-source": "needs_source_data",
            "need-both": "needs_product_and_source_data",
            "outside": "out_of_scope",
            "benchmark": "international_benchmark",
        }
        self.assertEqual(scores.loc[list(expected), "ranking_status"].to_dict(), expected)
        self.assertEqual(scores.loc["need-product", "observation_count"], 0)
        self.assertEqual(scores.loc["need-product", "distinct_source_count"], 1)
        self.assertTrue(pd.isna(scores.loc["need-product", "total_score"]))
        self.assertTrue(pd.isna(scores.loc["outside", "segment_rank"]))
        self.assertTrue(pd.isna(scores.loc["benchmark", "segment_rank"]))

    def test_ranks_only_within_each_segment_and_has_no_global_rank(self):
        scores = self._scores_by_id()
        self.assertEqual(scores.loc["alpha", "segment_rank"], 1)
        self.assertEqual(scores.loc["beta", "segment_rank"], 2)
        self.assertEqual(scores.loc["gamma", "segment_rank"], 1)
        self.assertEqual(scores["segment_rank"].dtype.name, "Int64")
        self.assertNotIn("global_rank", scores.columns)

    def test_weights_are_loaded_from_csv(self):
        self._write_weights(0, 0, 100)
        scores = self._scores_by_id()
        self.assertEqual(scores.loc["alpha", "total_score"], 3.0)
        self.assertEqual(scores.loc["beta", "total_score"], 5.0)
        self.assertEqual(scores.loc["beta", "segment_rank"], 1)

    def test_reach_is_not_an_eligibility_requirement(self):
        scores = self._scores_by_id()
        self.assertEqual(scores.loc["alpha", "ranking_status"], "ranked")
        self.assertTrue(pd.isna(scores.loc["alpha", "estimated_monthly_visits"]))

    def test_segment_summary_uses_ranked_coverage(self):
        summary = score_platforms.build_segment_summary(
            score_platforms.build_scores(self.data_dir)
        ).set_index("segment")
        self.assertEqual(list(summary.columns), score_platforms.SUMMARY_COLUMNS[1:])
        self.assertNotIn("Kapsam dışı", summary.index)

        lending = summary.loc["Lending"]
        self.assertEqual(lending["platform_count"], 3)
        self.assertEqual(lending["ranked_platform_count"], 2)
        self.assertEqual(lending["coverage_pct"], 66.67)
        self.assertEqual(lending["top_platforms"], "Alpha")
        self.assertEqual(lending["top_score"], 2.2)
        self.assertEqual(lending["average_ranked_score"], 2.0)

    def test_segment_summary_preserves_all_tied_leaders(self):
        scores = score_platforms.build_scores(self.data_dir)
        alpha_score = scores.loc[scores["platform_id"].eq("alpha"), "total_score"].iloc[0]
        scores.loc[scores["platform_id"].eq("beta"), "total_score"] = alpha_score
        summary = score_platforms.build_segment_summary(scores).set_index("segment")
        self.assertEqual(summary.loc["Lending", "top_platforms"], "Alpha | Beta")


if __name__ == "__main__":
    unittest.main()
