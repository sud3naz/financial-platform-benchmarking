#!/usr/bin/env python3
"""Aggregate public platform observations and calculate segment-specific scores."""

from __future__ import annotations

import argparse
import math
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
PLACEHOLDER_INSTITUTIONS = {"", "-", "—", "görünmüyor", "bulunamadı", "bilinmiyor"}
OUT_OF_SCOPE_SEGMENTS = {"kapsam dışı", "out of scope", "out_of_scope"}
TARGET_COUNTRY_KEYS = {"türkiye", "turkiye", "turkey"}
SCORING_CRITERIA = (
    "institution_coverage",
    "product_breadth",
    "source_diversity",
)
SUMMARY_COLUMNS = [
    "segment",
    "platform_count",
    "ranked_platform_count",
    "coverage_pct",
    "top_platforms",
    "top_score",
    "average_ranked_score",
]


def score_institution_coverage(value: int) -> float:
    if value >= 15:
        return 5.0
    if value >= 10:
        return 4.0
    if value >= 5:
        return 3.0
    if value >= 2:
        return 2.0
    return 1.0


def score_product_breadth(value: int) -> float:
    return float(max(1, min(5, value)))


def score_source_diversity(value: int) -> float:
    """Convert the number of distinct valid sources to a one-to-five score."""
    return float(max(1, min(5, value)))


def normalize_http_url(value: object) -> str | None:
    """Return a minimally normalized HTTP(S) URL, or ``None`` when invalid."""
    if pd.isna(value):
        return None
    candidate = str(value).strip()
    if not candidate or any(character.isspace() for character in candidate):
        return None
    try:
        parsed = urlsplit(candidate)
        # Accessing hostname also validates malformed IPv6-style netloc values.
        hostname = parsed.hostname
        _ = parsed.port
    except ValueError:
        return None
    if parsed.scheme.casefold() not in {"http", "https"} or not parsed.netloc or not hostname:
        return None
    normalized_path = "" if parsed.path == "/" else parsed.path
    return urlunsplit(
        (
            parsed.scheme.casefold(),
            parsed.netloc.casefold(),
            normalized_path,
            parsed.query,
            "",
        )
    )


def _load_weights(data_dir: Path) -> dict[str, float]:
    weights_frame = pd.read_csv(data_dir / "scoring_weights.csv")
    if weights_frame["criterion"].duplicated().any():
        raise ValueError("scoring_weights.csv contains duplicate criteria")

    raw_weights = dict(
        zip(
            weights_frame["criterion"],
            pd.to_numeric(weights_frame["weight"], errors="raise"),
        )
    )
    missing = [criterion for criterion in SCORING_CRITERIA if criterion not in raw_weights]
    if missing:
        raise ValueError(f"Missing scoring weights: {', '.join(missing)}")

    selected = {criterion: float(raw_weights[criterion]) for criterion in SCORING_CRITERIA}
    if any(weight < 0 for weight in selected.values()):
        raise ValueError("Scoring weights cannot be negative")
    if not math.isclose(sum(selected.values()), 100.0, abs_tol=1e-9):
        raise ValueError("Scoring weights must sum to 100")
    return {criterion: weight / 100.0 for criterion, weight in selected.items()}


def _source_counts(observations: pd.DataFrame, sources: pd.DataFrame) -> pd.Series:
    source_rows = pd.concat(
        [
            observations[["platform_id", "source_url"]],
            sources[["platform_id", "source_url"]],
        ],
        ignore_index=True,
    )
    source_rows["normalized_source_url"] = source_rows["source_url"].map(normalize_http_url)
    return (
        source_rows.dropna(subset=["normalized_source_url"])
        .groupby("platform_id", dropna=False)["normalized_source_url"]
        .nunique()
        .rename("distinct_source_count")
    )


def _add_optional_reach_columns(results: pd.DataFrame, data_dir: Path) -> pd.DataFrame:
    """Add supplementary reach data without making it part of ranking eligibility."""
    reach_path = data_dir / "reach_metrics.csv"
    if not reach_path.exists():
        results["estimated_monthly_visits"] = pd.NA
        results["measurement_note"] = pd.NA
        return results

    reach = pd.read_csv(reach_path)
    if "measurement_note" not in reach.columns and "data_date" in reach.columns:
        reach = reach.rename(columns={"data_date": "measurement_note"})
    for column in ("estimated_monthly_visits", "measurement_note"):
        if column not in reach.columns:
            reach[column] = pd.NA
    reach = reach[["platform_id", "estimated_monthly_visits", "measurement_note"]]
    return results.merge(reach.drop_duplicates("platform_id"), how="left", on="platform_id")


def build_scores(data_dir: Path) -> pd.DataFrame:
    platforms = pd.read_csv(data_dir / "platforms.csv")
    observations = pd.read_csv(data_dir / "platform_observations.csv")
    sources = pd.read_csv(data_dir / "sources.csv")
    weights = _load_weights(data_dir)

    observations["product_key"] = (
        observations["product"].fillna("").astype(str).str.strip().str.casefold()
    )
    observations["institution_key"] = (
        observations["institution"].fillna("").astype(str).str.strip().str.casefold()
    )
    institution_type_key = (
        observations["institution_type"].fillna("").astype(str).str.strip().str.casefold()
        if "institution_type" in observations.columns
        else pd.Series("", index=observations.index)
    )
    observations["valid_institution"] = (
        ~observations["institution_key"].isin(PLACEHOLDER_INSTITUTIONS)
        & ~observations["institution_key"].str.startswith(
            ("tanımlanamayan banka", "unidentified bank")
        )
        & ~institution_type_key.isin({"bilinmiyor", "unknown", "unidentified"})
    )

    grouped = observations.groupby("platform_id", dropna=False)
    stats = grouped.agg(
        observation_count=("platform_id", "size"),
        product_count=("product_key", lambda values: values.loc[values.ne("")].nunique()),
    )
    institution_counts = (
        observations.loc[observations["valid_institution"]]
        .groupby("platform_id", dropna=False)["institution_key"]
        .nunique()
        .rename("institution_count")
    )
    stats = stats.join(institution_counts, how="outer").join(
        _source_counts(observations, sources), how="outer"
    )

    results = platforms.merge(stats, how="left", left_on="platform_id", right_index=True)
    results = _add_optional_reach_columns(results, data_dir)
    for column in (
        "observation_count",
        "product_count",
        "institution_count",
        "distinct_source_count",
    ):
        results[column] = results[column].fillna(0).astype(int)

    results["institution_coverage_score"] = results["institution_count"].map(
        score_institution_coverage
    )
    results["product_breadth_score"] = results["product_count"].map(score_product_breadth)
    results["source_diversity_score"] = results["distinct_source_count"].map(
        score_source_diversity
    )

    segment_key = results["segment"].fillna("").astype(str).str.strip().str.casefold()
    country_key = results["country"].fillna("").astype(str).str.strip().str.casefold()
    is_international_benchmark = ~country_key.isin(TARGET_COUNTRY_KEYS)
    is_segment_out_of_scope = segment_key.isin(OUT_OF_SCOPE_SEGMENTS)
    in_scope = ~is_international_benchmark & ~is_segment_out_of_scope
    has_product_data = results["product_count"].gt(0)
    has_source_data = results["distinct_source_count"].gt(0)
    eligible = in_scope & has_product_data & has_source_data

    results["ranking_status"] = "ranked"
    results.loc[is_segment_out_of_scope, "ranking_status"] = "out_of_scope"
    results.loc[is_international_benchmark, "ranking_status"] = (
        "international_benchmark"
    )
    results.loc[in_scope & ~has_product_data & has_source_data, "ranking_status"] = (
        "needs_product_data"
    )
    results.loc[in_scope & has_product_data & ~has_source_data, "ranking_status"] = (
        "needs_source_data"
    )
    results.loc[in_scope & ~has_product_data & ~has_source_data, "ranking_status"] = (
        "needs_product_and_source_data"
    )

    weighted_total = (
        results["institution_coverage_score"] * weights["institution_coverage"]
        + results["product_breadth_score"] * weights["product_breadth"]
        + results["source_diversity_score"] * weights["source_diversity"]
    )
    results["total_score"] = weighted_total.where(eligible).round(2)
    results["segment_rank"] = pd.Series(pd.NA, index=results.index, dtype="Int64")
    segment_ranks = (
        results.loc[eligible]
        .groupby("segment", dropna=False)["total_score"]
        .rank(method="min", ascending=False)
        .astype("Int64")
    )
    results.loc[eligible, "segment_rank"] = segment_ranks

    ordered_columns = [
        "platform_id",
        "platform_name",
        "country",
        "segment",
        "category",
        "estimated_monthly_visits",
        "measurement_note",
        "observation_count",
        "institution_count",
        "product_count",
        "distinct_source_count",
        "institution_coverage_score",
        "product_breadth_score",
        "source_diversity_score",
        "total_score",
        "segment_rank",
        "ranking_status",
        "website",
    ]
    ordered = results[ordered_columns].copy()
    ordered["_status_order"] = pd.Categorical(
        ordered["ranking_status"],
        categories=[
            "ranked",
            "needs_product_data",
            "needs_source_data",
            "needs_product_and_source_data",
            "international_benchmark",
            "out_of_scope",
        ],
        ordered=True,
    )
    return ordered.sort_values(
        ["_status_order", "segment", "total_score", "platform_name"],
        ascending=[True, True, False, True],
        na_position="last",
    ).drop(columns="_status_order")


def build_segment_summary(scores: pd.DataFrame) -> pd.DataFrame:
    in_scope = scores.loc[
        ~scores["ranking_status"].isin(
            {"out_of_scope", "international_benchmark"}
        )
    ].copy()
    summaries: list[dict[str, object]] = []
    for segment, group in in_scope.groupby("segment", dropna=False):
        ranked = group.loc[group["ranking_status"].eq("ranked")].sort_values(
            ["total_score", "platform_name"], ascending=[False, True]
        )
        top_score = pd.NA if ranked.empty else ranked["total_score"].max()
        top_platforms = (
            pd.NA
            if ranked.empty
            else " | ".join(
                sorted(
                    ranked.loc[
                        ranked["total_score"].eq(top_score), "platform_name"
                    ].astype(str)
                )
            )
        )
        summaries.append(
            {
                "segment": segment,
                "platform_count": len(group),
                "ranked_platform_count": len(ranked),
                "coverage_pct": round(len(ranked) / len(group) * 100, 2),
                "top_platforms": top_platforms,
                "top_score": top_score,
                "average_ranked_score": (
                    pd.NA if ranked.empty else round(ranked["total_score"].mean(), 2)
                ),
            }
        )
    if not summaries:
        return pd.DataFrame(columns=SUMMARY_COLUMNS)
    return pd.DataFrame(summaries, columns=SUMMARY_COLUMNS).sort_values(
        "segment", na_position="last"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "outputs")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    scores = build_scores(args.data_dir)
    summary = build_segment_summary(scores)
    scores.to_csv(args.output_dir / "platform_scores.csv", index=False)
    summary.to_csv(args.output_dir / "segment_summary.csv", index=False)
    print(
        f"Wrote {len(scores)} platform rows and {len(summary)} segment rows to {args.output_dir}."
    )


if __name__ == "__main__":
    main()
