#!/usr/bin/env python3
"""Aggregate public platform observations and calculate transparent scores."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
PLACEHOLDER_INSTITUTIONS = {"", "-", "—", "görünmüyor", "bulunamadı", "bilinmiyor"}


def score_market_reach(value: float | int | None) -> float:
    if pd.isna(value):
        return float("nan")
    if value >= 5_000_000:
        return 5.0
    if value >= 1_000_000:
        return 4.0
    if value >= 100_000:
        return 3.0
    if value >= 10_000:
        return 2.0
    return 1.0


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


def score_evidence_completeness(value: float) -> float:
    if value >= 0.95:
        return 5.0
    if value >= 0.85:
        return 4.0
    if value >= 0.70:
        return 3.0
    if value >= 0.50:
        return 2.0
    return 1.0


def has_text(series: pd.Series) -> pd.Series:
    return series.fillna("").astype(str).str.strip().ne("")


def build_scores(data_dir: Path) -> pd.DataFrame:
    platforms = pd.read_csv(data_dir / "platforms.csv")
    observations = pd.read_csv(data_dir / "platform_observations.csv")
    reach = pd.read_csv(data_dir / "reach_metrics.csv")
    weights_frame = pd.read_csv(data_dir / "scoring_weights.csv")
    weights = dict(zip(weights_frame["criterion"], weights_frame["weight"] / 100.0))

    observations["institution_clean"] = observations["institution"].fillna("").astype(str).str.strip()
    observations["institution_key"] = observations["institution_clean"].str.casefold()
    observations["valid_institution"] = ~observations["institution_key"].isin(PLACEHOLDER_INSTITUTIONS)
    observations["complete_evidence"] = has_text(observations["source_url"]) & has_text(
        observations["observed_date"]
    )

    grouped = observations.groupby("platform_id", dropna=False)
    stats = grouped.agg(
        observation_count=("platform_id", "size"),
        product_count=("product", lambda values: values.dropna().astype(str).str.strip().replace("", pd.NA).nunique()),
        evidence_completeness=("complete_evidence", "mean"),
    )

    institution_counts = (
        observations.loc[observations["valid_institution"]]
        .groupby("platform_id")["institution_clean"]
        .nunique()
        .rename("institution_count")
    )
    stats = stats.join(institution_counts).fillna({"institution_count": 0})

    results = platforms.merge(stats, how="left", left_on="platform_id", right_index=True)
    results = results.merge(
        reach[["platform_id", "estimated_monthly_visits", "data_date"]],
        how="left",
        on="platform_id",
    )
    for column in [
        "observation_count",
        "product_count",
        "institution_count",
    ]:
        results[column] = results[column].fillna(0).astype(int)
    results["evidence_completeness"] = results["evidence_completeness"].fillna(0.0)

    results["market_reach_score"] = results["estimated_monthly_visits"].map(score_market_reach)
    results["institution_coverage_score"] = results["institution_count"].map(score_institution_coverage)
    results["product_breadth_score"] = results["product_count"].map(score_product_breadth)
    results["evidence_completeness_score"] = results["evidence_completeness"].map(
        score_evidence_completeness
    )

    in_scope = ~results["segment"].fillna("").str.casefold().eq("kapsam dışı")
    eligible = (
        in_scope
        & results["estimated_monthly_visits"].notna()
        & results["product_count"].gt(0)
    )
    results["ranking_status"] = "ranked"
    results.loc[~in_scope, "ranking_status"] = "out_of_scope"
    results.loc[in_scope & results["estimated_monthly_visits"].isna(), "ranking_status"] = "needs_reach_data"
    results.loc[in_scope & results["product_count"].eq(0), "ranking_status"] = "needs_product_data"

    weighted_total = (
        results["market_reach_score"] * weights["market_reach"]
        + results["institution_coverage_score"] * weights["institution_coverage"]
        + results["product_breadth_score"] * weights["product_breadth"]
        + results["evidence_completeness_score"] * weights["evidence_completeness"]
    )
    results["total_score"] = weighted_total.where(eligible).round(2)
    results["global_rank"] = pd.NA
    results.loc[eligible, "global_rank"] = (
        results.loc[eligible, "total_score"].rank(method="min", ascending=False).astype("Int64")
    )
    results["segment_rank"] = pd.NA
    results.loc[eligible, "segment_rank"] = (
        results.loc[eligible]
        .groupby("segment")["total_score"]
        .rank(method="min", ascending=False)
        .astype("Int64")
    )

    ordered_columns = [
        "platform_id",
        "platform_name",
        "country",
        "segment",
        "category",
        "estimated_monthly_visits",
        "observation_count",
        "institution_count",
        "product_count",
        "evidence_completeness",
        "market_reach_score",
        "institution_coverage_score",
        "product_breadth_score",
        "evidence_completeness_score",
        "total_score",
        "segment_rank",
        "global_rank",
        "ranking_status",
        "data_date",
        "website",
    ]
    ordered = results[ordered_columns].copy()
    ordered["_status_order"] = pd.Categorical(
        ordered["ranking_status"],
        categories=["ranked", "needs_reach_data", "needs_product_data", "out_of_scope"],
        ordered=True,
    )
    return ordered.sort_values(
        ["_status_order", "total_score", "platform_name"],
        ascending=[True, False, True],
        na_position="last",
    ).drop(columns="_status_order")


def build_segment_summary(scores: pd.DataFrame) -> pd.DataFrame:
    in_scope = scores.loc[~scores["segment"].fillna("").str.casefold().eq("kapsam dışı")].copy()
    summaries: list[dict[str, object]] = []
    for segment, group in in_scope.groupby("segment", dropna=False):
        ranked = group.loc[group["ranking_status"].eq("ranked")].sort_values(
            ["total_score", "platform_name"], ascending=[False, True]
        )
        top = ranked.iloc[0] if not ranked.empty else None
        summaries.append(
            {
                "segment": segment,
                "platform_count": len(group),
                "measured_reach_count": int(group["estimated_monthly_visits"].notna().sum()),
                "ranked_platform_count": len(ranked),
                "estimated_monthly_visits_total": group["estimated_monthly_visits"].sum(min_count=1),
                "top_platform": "" if top is None else top["platform_name"],
                "top_score": "" if top is None else top["total_score"],
                "average_ranked_score": "" if ranked.empty else round(ranked["total_score"].mean(), 2),
            }
        )
    return pd.DataFrame(summaries).sort_values("segment")


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
