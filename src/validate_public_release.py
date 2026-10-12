#!/usr/bin/env python3
"""Validate that the public portfolio is complete and company-neutral."""

from __future__ import annotations

import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RESTRICTED_TOKENS = [("alba" + "raka").casefold()]
TEXT_SUFFIXES = {".csv", ".md", ".py", ".txt", ".toml", ".json", ".yml", ".yaml"}


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> None:
    errors: list[str] = []
    required_files = [
        ROOT / "README.md",
        ROOT / "data" / "platforms.csv",
        ROOT / "data" / "platform_observations.csv",
        ROOT / "data" / "reach_metrics.csv",
        ROOT / "data" / "scoring_weights.csv",
        ROOT / "data" / "sources.csv",
        ROOT / "outputs" / "platform_scores.csv",
        ROOT / "outputs" / "segment_summary.csv",
        ROOT / "outputs" / "top_platform_scores.png",
        ROOT / "outputs" / "segment_coverage.png",
    ]
    for path in required_files:
        if not path.exists():
            errors.append(f"Missing required file: {path.relative_to(ROOT)}")

    for path in ROOT.rglob("*"):
        if not path.is_file() or ".git" in path.parts:
            continue
        if path.suffix.casefold() in {".xlsx", ".xls", ".xlsm"}:
            errors.append(f"Original workbook format must not be published: {path.relative_to(ROOT)}")
            continue
        if path.suffix.casefold() in TEXT_SUFFIXES or path.name in {"Makefile", ".gitignore"}:
            content = path.read_text(encoding="utf-8", errors="ignore").casefold()
            for token in RESTRICTED_TOKENS:
                if token in content:
                    errors.append(f"Restricted company reference found in {path.relative_to(ROOT)}")

    platforms_path = ROOT / "data" / "platforms.csv"
    observations_path = ROOT / "data" / "platform_observations.csv"
    if platforms_path.exists():
        platforms = read_rows(platforms_path)
        ids = [row["platform_id"] for row in platforms]
        if len(ids) != len(set(ids)):
            errors.append("Duplicate platform_id values found in data/platforms.csv")
        if len(platforms) < 50:
            errors.append("Platform inventory is unexpectedly small")
    if observations_path.exists():
        observations = read_rows(observations_path)
        if len(observations) < 500:
            errors.append("Observation dataset is unexpectedly small")

    if errors:
        raise SystemExit("\n".join(errors))
    print("Public-release validation passed.")


if __name__ == "__main__":
    main()

