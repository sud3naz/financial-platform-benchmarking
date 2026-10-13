#!/usr/bin/env python3
"""Validate the public portfolio's data contract and release safety."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urlparse

from PIL import Image, UnidentifiedImageError


ROOT = Path(__file__).resolve().parents[1]
RESTRICTED_TOKENS = [("alba" + "raka").casefold()]
TEXT_SUFFIXES = {".csv", ".md", ".py", ".txt", ".toml", ".json", ".yml", ".yaml"}
SKIP_PARTS = {".git", ".venv", "venv", "__pycache__", ".pytest_cache"}
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TARGET_COUNTRY_KEYS = {"türkiye", "turkiye", "turkey"}
OUT_OF_SCOPE_SEGMENTS = {"kapsam dışı", "out of scope", "out_of_scope"}

EXPECTED_WEIGHTS = {
    "institution_coverage": Decimal("45"),
    "product_breadth": Decimal("35"),
    "source_diversity": Decimal("20"),
}
EXPECTED_IMAGES = {
    "outputs/credit_comparison_scores.png": ((1600, 1080), "RGB"),
    "outputs/segment_coverage.png": ((1600, 960), "RGB"),
}
ALLOWED_STATUSES = {
    "ranked",
    "out_of_scope",
    "international_benchmark",
    "needs_product_data",
    "needs_source_data",
    "needs_product_and_source_data",
}


def read_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def clean_cell(row: dict[str, str], field: str) -> str:
    value = row.get(field)
    return "" if value is None else str(value).strip()


def require_columns(
    path: Path,
    fieldnames: list[str],
    required: set[str],
    errors: list[str],
) -> bool:
    missing = sorted(required.difference(fieldnames))
    if missing:
        errors.append(
            f"{path.relative_to(ROOT)} is missing required columns: {', '.join(missing)}"
        )
        return False
    return True


def is_http_url(value: str) -> bool:
    candidate = value.strip()
    if not candidate or any(character.isspace() for character in candidate):
        return False
    try:
        parsed = urlparse(candidate)
        hostname = parsed.hostname
        _ = parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme.casefold() in {"http", "https"}
        and bool(parsed.netloc)
        and bool(hostname)
    )


def add_bounded_row_errors(
    errors: list[str],
    label: str,
    failures: list[tuple[int, str]],
) -> None:
    if not failures:
        return
    examples = "; ".join(f"row {row}: {value!r}" for row, value in failures[:10])
    remainder = len(failures) - 10
    suffix = f"; plus {remainder} more" if remainder > 0 else ""
    errors.append(f"{label} ({len(failures)}): {examples}{suffix}")


def validate_weights(path: Path, errors: list[str]) -> None:
    if not path.exists():
        return
    fieldnames, rows = read_rows(path)
    if not require_columns(path, fieldnames, {"criterion", "weight"}, errors):
        return

    criteria = [clean_cell(row, "criterion") for row in rows]
    duplicates = sorted(name for name, count in Counter(criteria).items() if count > 1)
    if duplicates:
        errors.append(f"Duplicate scoring criteria found: {', '.join(duplicates)}")

    actual: dict[str, Decimal] = {}
    invalid_weights: list[tuple[int, str]] = []
    for row_number, row in enumerate(rows, start=2):
        criterion = clean_cell(row, "criterion")
        raw_weight = clean_cell(row, "weight")
        try:
            actual[criterion] = Decimal(raw_weight)
        except InvalidOperation:
            invalid_weights.append((row_number, raw_weight))
    add_bounded_row_errors(errors, "Invalid scoring weight values", invalid_weights)
    if invalid_weights:
        return

    actual_criteria = set(actual)
    expected_criteria = set(EXPECTED_WEIGHTS)
    if actual_criteria != expected_criteria:
        missing = sorted(expected_criteria - actual_criteria)
        unexpected = sorted(actual_criteria - expected_criteria)
        details = []
        if missing:
            details.append(f"missing {', '.join(missing)}")
        if unexpected:
            details.append(f"unexpected {', '.join(unexpected)}")
        errors.append(f"Scoring criteria do not match v2 contract: {'; '.join(details)}")

    total = sum(actual.values(), Decimal("0"))
    if total != Decimal("100"):
        errors.append(f"Scoring weights must sum to 100; found {total}")

    for criterion, expected in EXPECTED_WEIGHTS.items():
        if criterion in actual and actual[criterion] != expected:
            errors.append(
                f"Weight for {criterion} must be {expected}; found {actual[criterion]}"
            )


def validate_platforms(
    path: Path,
    errors: list[str],
) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    fieldnames, rows = read_rows(path)
    if not require_columns(
        path,
        fieldnames,
        {"platform_id", "platform_name", "country", "segment"},
        errors,
    ):
        return {}

    identifiers = [clean_cell(row, "platform_id") for row in rows]
    blank_rows = [(index, "") for index, value in enumerate(identifiers, start=2) if not value]
    add_bounded_row_errors(errors, "Blank platform_id values", blank_rows)
    duplicates = sorted(name for name, count in Counter(identifiers).items() if name and count > 1)
    if duplicates:
        errors.append(f"Duplicate platform_id values found: {', '.join(duplicates)}")
    if len(rows) < 50:
        errors.append("Platform inventory is unexpectedly small")
    return {
        clean_cell(row, "platform_id"): row
        for row in rows
        if clean_cell(row, "platform_id")
    }


def validate_observations(
    path: Path,
    platform_ids: set[str],
    errors: list[str],
) -> None:
    if not path.exists():
        return
    fieldnames, rows = read_rows(path)
    required = {"platform_id", "product", "source_url", "observed_date"}
    if not require_columns(path, fieldnames, required, errors):
        return

    if len(rows) < 500:
        errors.append("Observation dataset is unexpectedly small")

    invalid_urls: list[tuple[int, str]] = []
    invalid_dates: list[tuple[int, str]] = []
    unknown_platforms: list[tuple[int, str]] = []
    seen_rows: dict[tuple[str, ...], int] = {}
    duplicate_rows: list[tuple[int, str]] = []

    for row_number, row in enumerate(rows, start=2):
        source_url = clean_cell(row, "source_url")
        if not is_http_url(source_url):
            invalid_urls.append((row_number, source_url))

        observed_date = clean_cell(row, "observed_date")
        valid_date = bool(ISO_DATE.fullmatch(observed_date))
        if valid_date:
            try:
                datetime.strptime(observed_date, "%Y-%m-%d")
            except ValueError:
                valid_date = False
        if not valid_date:
            invalid_dates.append((row_number, observed_date))

        platform_id = clean_cell(row, "platform_id")
        if platform_ids and platform_id not in platform_ids:
            unknown_platforms.append((row_number, platform_id))

        signature = tuple(row.get(field, "") for field in fieldnames)
        if signature in seen_rows:
            duplicate_rows.append(
                (row_number, f"duplicates row {seen_rows[signature]}")
            )
        else:
            seen_rows[signature] = row_number

    add_bounded_row_errors(errors, "Observation URLs must be valid HTTP(S) URLs", invalid_urls)
    add_bounded_row_errors(
        errors,
        "Observation dates must be valid ISO YYYY-MM-DD dates",
        invalid_dates,
    )
    add_bounded_row_errors(
        errors,
        "Observations reference unknown platform_id values",
        unknown_platforms,
    )
    add_bounded_row_errors(errors, "Exact duplicate observations found", duplicate_rows)


def validate_sources(
    path: Path,
    platform_ids: set[str],
    errors: list[str],
) -> None:
    if not path.exists():
        return
    fieldnames, rows = read_rows(path)
    if not require_columns(path, fieldnames, {"platform_id", "source_url"}, errors):
        return
    invalid_urls: list[tuple[int, str]] = []
    unknown_platforms: list[tuple[int, str]] = []
    duplicate_rows: list[tuple[int, str]] = []
    seen: dict[tuple[str, ...], int] = {}
    for row_number, row in enumerate(rows, start=2):
        source_url = clean_cell(row, "source_url")
        if not is_http_url(source_url):
            invalid_urls.append((row_number, source_url))
        platform_id = clean_cell(row, "platform_id")
        if platform_ids and platform_id not in platform_ids:
            unknown_platforms.append((row_number, platform_id))
        signature = tuple(row.get(field, "") for field in fieldnames)
        if signature in seen:
            duplicate_rows.append((row_number, f"duplicates row {seen[signature]}"))
        else:
            seen[signature] = row_number
    add_bounded_row_errors(errors, "Source URLs must be valid HTTP(S) URLs", invalid_urls)
    add_bounded_row_errors(
        errors,
        "Sources reference unknown platform_id values",
        unknown_platforms,
    )
    add_bounded_row_errors(errors, "Exact duplicate source rows found", duplicate_rows)


def validate_reach_metrics(
    path: Path,
    platform_ids: set[str],
    errors: list[str],
) -> None:
    if not path.exists():
        return
    fieldnames, rows = read_rows(path)
    required = {
        "platform_id",
        "estimated_monthly_visits",
        "measurement_note",
        "verification_note",
        "website",
    }
    if not require_columns(path, fieldnames, required, errors):
        return
    identifiers = [clean_cell(row, "platform_id") for row in rows]
    duplicates = sorted(
        identifier
        for identifier, count in Counter(identifiers).items()
        if identifier and count > 1
    )
    if duplicates:
        errors.append(f"Duplicate reach platform_id values: {', '.join(duplicates)}")
    unknown_platforms: list[tuple[int, str]] = []
    invalid_websites: list[tuple[int, str]] = []
    invalid_visits: list[tuple[int, str]] = []
    for row_number, row in enumerate(rows, start=2):
        platform_id = clean_cell(row, "platform_id")
        if platform_ids and platform_id not in platform_ids:
            unknown_platforms.append((row_number, platform_id))
        website = clean_cell(row, "website")
        if not is_http_url(website):
            invalid_websites.append((row_number, website))
        raw_visits = clean_cell(row, "estimated_monthly_visits")
        if raw_visits:
            try:
                visits = Decimal(raw_visits)
            except InvalidOperation:
                visits = Decimal("-1")
            if not visits.is_finite() or visits < 0:
                invalid_visits.append((row_number, raw_visits))
    add_bounded_row_errors(
        errors,
        "Reach metrics reference unknown platform_id values",
        unknown_platforms,
    )
    add_bounded_row_errors(errors, "Reach websites must be valid HTTP(S) URLs", invalid_websites)
    add_bounded_row_errors(
        errors,
        "Reach estimates must be blank or non-negative numbers",
        invalid_visits,
    )


def expected_component_scores(
    institution_count: int,
    product_count: int,
    source_count: int,
) -> tuple[Decimal, Decimal, Decimal]:
    if institution_count >= 15:
        institution_score = 5
    elif institution_count >= 10:
        institution_score = 4
    elif institution_count >= 5:
        institution_score = 3
    elif institution_count >= 2:
        institution_score = 2
    else:
        institution_score = 1
    product_score = max(1, min(5, product_count))
    source_score = max(1, min(5, source_count))
    return tuple(
        Decimal(value) for value in (institution_score, product_score, source_score)
    )


def expected_status(
    platform: dict[str, str],
    product_count: int,
    source_count: int,
) -> str:
    country = clean_cell(platform, "country").casefold()
    segment = clean_cell(platform, "segment").casefold()
    if country not in TARGET_COUNTRY_KEYS:
        return "international_benchmark"
    if segment in OUT_OF_SCOPE_SEGMENTS:
        return "out_of_scope"
    if product_count <= 0 and source_count <= 0:
        return "needs_product_and_source_data"
    if product_count <= 0:
        return "needs_product_data"
    if source_count <= 0:
        return "needs_source_data"
    return "ranked"


def validate_generated_scores(
    path: Path,
    platforms: dict[str, dict[str, str]],
    errors: list[str],
) -> list[dict[str, str]]:
    if not path.exists():
        return []
    fieldnames, rows = read_rows(path)
    required = {
        "platform_id",
        "platform_name",
        "country",
        "segment",
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
    }
    if not require_columns(path, fieldnames, required, errors):
        return rows
    if "global_rank" in fieldnames:
        errors.append("outputs/platform_scores.csv must not publish a global_rank")

    invalid_statuses = sorted(
        {
            clean_cell(row, "ranking_status")
            for row in rows
            if clean_cell(row, "ranking_status") not in ALLOWED_STATUSES
        }
    )
    if invalid_statuses:
        errors.append(f"Unexpected ranking_status values: {', '.join(invalid_statuses)}")

    score_ids = [clean_cell(row, "platform_id") for row in rows]
    duplicate_ids = sorted(
        identifier
        for identifier, count in Counter(score_ids).items()
        if identifier and count > 1
    )
    if duplicate_ids:
        errors.append(
            f"Duplicate platform_id values in generated scores: {', '.join(duplicate_ids)}"
        )
    if platforms:
        missing = sorted(set(platforms) - set(score_ids))
        unexpected = sorted(set(score_ids) - set(platforms))
        if missing:
            errors.append(
                f"Generated scores are missing platform_id values: {', '.join(missing)}"
            )
        if unexpected:
            errors.append(
                f"Generated scores contain unknown platform_id values: {', '.join(unexpected)}"
            )

    ranked_by_segment: dict[str, list[tuple[int, Decimal, int]]] = defaultdict(list)
    for row_number, row in enumerate(rows, start=2):
        identifier = clean_cell(row, "platform_id")
        platform = platforms.get(identifier)
        if platform is None:
            continue
        for field in ("platform_name", "country", "segment"):
            if clean_cell(row, field) != clean_cell(platform, field):
                errors.append(
                    f"Generated score row {row_number} has a mismatched {field} for {identifier}"
                )

        counts: dict[str, int] = {}
        for field in (
            "observation_count",
            "institution_count",
            "product_count",
            "distinct_source_count",
        ):
            raw = clean_cell(row, field)
            try:
                value = int(raw)
            except ValueError:
                errors.append(
                    f"Generated score row {row_number} has a non-integer {field}: {raw!r}"
                )
                value = -1
            if value < 0:
                errors.append(
                    f"Generated score row {row_number} has a negative {field}: {raw!r}"
                )
            counts[field] = value

        expected_scores = expected_component_scores(
            counts["institution_count"],
            counts["product_count"],
            counts["distinct_source_count"],
        )
        component_fields = (
            "institution_coverage_score",
            "product_breadth_score",
            "source_diversity_score",
        )
        parsed_scores: list[Decimal] = []
        for field, expected in zip(component_fields, expected_scores):
            raw = clean_cell(row, field)
            try:
                actual = Decimal(raw)
            except InvalidOperation:
                errors.append(
                    f"Generated score row {row_number} has an invalid {field}: {raw!r}"
                )
                actual = Decimal("-1")
            parsed_scores.append(actual)
            if actual != expected:
                errors.append(
                    f"Generated score row {row_number} has {field}={actual}; expected {expected}"
                )

        wanted_status = expected_status(
            platform,
            counts["product_count"],
            counts["distinct_source_count"],
        )
        actual_status = clean_cell(row, "ranking_status")
        if actual_status != wanted_status:
            errors.append(
                f"Generated score row {row_number} has status {actual_status!r}; "
                f"expected {wanted_status!r}"
            )

        raw_total = clean_cell(row, "total_score")
        raw_rank = clean_cell(row, "segment_rank")
        if wanted_status != "ranked":
            if raw_total or raw_rank:
                errors.append(
                    f"Unranked score row {row_number} must have blank total_score and segment_rank"
                )
            continue

        try:
            total_score = Decimal(raw_total)
        except InvalidOperation:
            errors.append(
                f"Ranked score row {row_number} has an invalid total_score: {raw_total!r}"
            )
            continue
        expected_total = (
            parsed_scores[0] * EXPECTED_WEIGHTS["institution_coverage"]
            + parsed_scores[1] * EXPECTED_WEIGHTS["product_breadth"]
            + parsed_scores[2] * EXPECTED_WEIGHTS["source_diversity"]
        ) / Decimal("100")
        if total_score != expected_total.quantize(Decimal("0.01")):
            errors.append(
                f"Ranked score row {row_number} has total_score={total_score}; "
                f"expected {expected_total.quantize(Decimal('0.01'))}"
            )
        try:
            rank = int(raw_rank)
        except ValueError:
            errors.append(
                f"Ranked score row {row_number} has an invalid segment_rank: {raw_rank!r}"
            )
            continue
        if rank < 1:
            errors.append(
                f"Ranked score row {row_number} has a non-positive segment_rank: {rank}"
            )
        ranked_by_segment[clean_cell(row, "segment")].append(
            (row_number, total_score, rank)
        )

    for segment, entries in ranked_by_segment.items():
        ordered = sorted(entries, key=lambda item: item[1], reverse=True)
        score_to_rank: dict[Decimal, int] = {}
        for position, (_, score, _) in enumerate(ordered, start=1):
            score_to_rank.setdefault(score, position)
        for row_number, score, rank in entries:
            if rank != score_to_rank[score]:
                errors.append(
                    f"Generated score row {row_number} has segment_rank={rank}; "
                    f"expected {score_to_rank[score]} in {segment}"
                )
    return rows


def validate_segment_summary(
    path: Path,
    score_rows: list[dict[str, str]],
    errors: list[str],
) -> None:
    if not path.exists():
        return
    fieldnames, rows = read_rows(path)
    required = {
        "segment",
        "platform_count",
        "ranked_platform_count",
        "coverage_pct",
        "top_platforms",
        "top_score",
        "average_ranked_score",
    }
    if not require_columns(path, fieldnames, required, errors):
        return
    summary_by_segment = {clean_cell(row, "segment"): row for row in rows}
    if len(summary_by_segment) != len(rows):
        errors.append("outputs/segment_summary.csv contains duplicate segment rows")

    score_groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in score_rows:
        if clean_cell(row, "ranking_status") not in {
            "out_of_scope",
            "international_benchmark",
        }:
            score_groups[clean_cell(row, "segment")].append(row)
    missing = sorted(set(score_groups) - set(summary_by_segment))
    unexpected = sorted(set(summary_by_segment) - set(score_groups))
    if missing:
        errors.append(f"Segment summary is missing segments: {', '.join(missing)}")
    if unexpected:
        errors.append(f"Segment summary has unexpected segments: {', '.join(unexpected)}")

    for segment, group in score_groups.items():
        summary = summary_by_segment.get(segment)
        if summary is None:
            continue
        ranked = [row for row in group if clean_cell(row, "ranking_status") == "ranked"]
        expected_integers = {
            "platform_count": len(group),
            "ranked_platform_count": len(ranked),
        }
        for field, expected in expected_integers.items():
            try:
                actual = int(clean_cell(summary, field))
            except ValueError:
                actual = -1
            if actual != expected:
                errors.append(
                    f"Segment summary {segment!r} has {field}={clean_cell(summary, field)!r}; "
                    f"expected {expected}"
                )

        expected_coverage = (
            Decimal(len(ranked)) * Decimal("100") / Decimal(len(group))
        ).quantize(Decimal("0.01"))
        try:
            actual_coverage = Decimal(clean_cell(summary, "coverage_pct"))
        except InvalidOperation:
            actual_coverage = Decimal("-1")
        if actual_coverage != expected_coverage:
            errors.append(
                f"Segment summary {segment!r} has coverage_pct={actual_coverage}; "
                f"expected {expected_coverage}"
            )

        if ranked:
            totals = [Decimal(clean_cell(row, "total_score")) for row in ranked]
            top_score = max(totals)
            leaders = " | ".join(
                sorted(
                    clean_cell(row, "platform_name")
                    for row in ranked
                    if Decimal(clean_cell(row, "total_score")) == top_score
                )
            )
            average = (sum(totals, Decimal("0")) / Decimal(len(totals))).quantize(
                Decimal("0.01")
            )
            if clean_cell(summary, "top_platforms") != leaders:
                errors.append(
                    f"Segment summary {segment!r} has incorrect top_platforms"
                )
            for field, expected in (
                ("top_score", top_score),
                ("average_ranked_score", average),
            ):
                try:
                    actual = Decimal(clean_cell(summary, field))
                except InvalidOperation:
                    actual = Decimal("-1")
                if actual != expected:
                    errors.append(
                        f"Segment summary {segment!r} has {field}={actual}; expected {expected}"
                    )
        elif any(
            clean_cell(summary, field)
            for field in ("top_platforms", "top_score", "average_ranked_score")
        ):
            errors.append(
                f"Segment summary {segment!r} must leave leader fields blank when none are ranked"
            )


def validate_images(errors: list[str]) -> None:
    for relative_path, (expected_size, expected_mode) in EXPECTED_IMAGES.items():
        path = ROOT / relative_path
        if not path.exists():
            continue
        if path.stat().st_size == 0:
            errors.append(f"Generated visual is empty: {relative_path}")
            continue
        try:
            with Image.open(path) as image:
                image.load()
                if image.format != "PNG":
                    errors.append(f"{relative_path} must be a PNG; found {image.format}")
                if image.size != expected_size:
                    errors.append(
                        f"{relative_path} must be {expected_size[0]}x{expected_size[1]}; "
                        f"found {image.size[0]}x{image.size[1]}"
                    )
                if image.mode != expected_mode:
                    errors.append(
                        f"{relative_path} must use {expected_mode} mode; found {image.mode}"
                    )
        except (OSError, UnidentifiedImageError) as exc:
            errors.append(f"Could not read generated visual {relative_path}: {exc}")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_visual_manifest(errors: list[str]) -> None:
    manifest_path = ROOT / "outputs" / "visual_manifest.json"
    if not manifest_path.exists():
        return
    try:
        manifest_bytes = manifest_path.read_bytes()
        manifest = json.loads(manifest_bytes)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        errors.append(f"Could not read outputs/visual_manifest.json: {exc}")
        return

    if manifest.get("manifest_version") != 1:
        errors.append("outputs/visual_manifest.json must use manifest_version 1")
    renderer_path = ROOT / "src" / "create_visuals.py"
    if manifest.get("renderer_source_sha256") != sha256_file(renderer_path):
        errors.append("Visual manifest is stale relative to src/create_visuals.py")

    expected_inputs = {
        "platform_scores.csv": ROOT / "outputs" / "platform_scores.csv",
        "segment_summary.csv": ROOT / "outputs" / "segment_summary.csv",
    }
    recorded_inputs = manifest.get("inputs")
    if not isinstance(recorded_inputs, dict):
        errors.append("Visual manifest must contain an inputs object")
        recorded_inputs = {}
    for name, path in expected_inputs.items():
        if path.exists() and recorded_inputs.get(name) != sha256_file(path):
            errors.append(f"Visual manifest is stale relative to outputs/{name}")

    recorded_charts = manifest.get("charts")
    if not isinstance(recorded_charts, dict):
        errors.append("Visual manifest must contain a charts object")
        recorded_charts = {}
    manifest_digest = hashlib.sha256(manifest_bytes).hexdigest()
    for relative_path, (expected_size, _) in EXPECTED_IMAGES.items():
        name = Path(relative_path).name
        chart = recorded_charts.get(name)
        if not isinstance(chart, dict) or chart.get("size") != list(expected_size):
            errors.append(f"Visual manifest has an invalid specification for {name}")
        image_path = ROOT / relative_path
        if not image_path.exists():
            continue
        try:
            with Image.open(image_path) as image:
                if image.info.get("visual_manifest_sha256") != manifest_digest:
                    errors.append(
                        f"{relative_path} is stale relative to visual_manifest.json"
                    )
        except (OSError, UnidentifiedImageError):
            pass


def validate_restricted_content(errors: list[str]) -> None:
    for path in ROOT.rglob("*"):
        if not path.is_file() or any(part in SKIP_PARTS for part in path.parts):
            continue
        if path.suffix.casefold() in {".xlsx", ".xls", ".xlsm"}:
            errors.append(
                f"Original workbook format must not be published: {path.relative_to(ROOT)}"
            )
            continue
        if path.suffix.casefold() in TEXT_SUFFIXES or path.name in {"Makefile", ".gitignore"}:
            content = path.read_text(encoding="utf-8", errors="ignore").casefold()
            for token in RESTRICTED_TOKENS:
                if token in content:
                    errors.append(
                        f"Restricted company reference found in {path.relative_to(ROOT)}"
                    )


def main() -> None:
    errors: list[str] = []
    required_files = [
        ROOT / "README.md",
        ROOT / "LICENSE",
        ROOT / ".github" / "workflows" / "ci.yml",
        ROOT / "docs" / "methodology.md",
        ROOT / "docs" / "data_dictionary.md",
        ROOT / "data" / "platforms.csv",
        ROOT / "data" / "platform_observations.csv",
        ROOT / "data" / "reach_metrics.csv",
        ROOT / "data" / "scoring_weights.csv",
        ROOT / "data" / "sources.csv",
        ROOT / "src" / "score_platforms.py",
        ROOT / "src" / "create_visuals.py",
        ROOT / "src" / "validate_public_release.py",
        ROOT / "tests" / "test_scoring.py",
        ROOT / "outputs" / "platform_scores.csv",
        ROOT / "outputs" / "segment_summary.csv",
        ROOT / "outputs" / "visual_manifest.json",
        ROOT / "outputs" / "credit_comparison_scores.png",
        ROOT / "outputs" / "segment_coverage.png",
    ]
    for path in required_files:
        if not path.is_file():
            errors.append(f"Missing required file: {path.relative_to(ROOT)}")
        elif path.stat().st_size == 0:
            errors.append(f"Required file is empty: {path.relative_to(ROOT)}")

    platforms = validate_platforms(ROOT / "data" / "platforms.csv", errors)
    validate_observations(
        ROOT / "data" / "platform_observations.csv",
        set(platforms),
        errors,
    )
    validate_sources(ROOT / "data" / "sources.csv", set(platforms), errors)
    validate_reach_metrics(
        ROOT / "data" / "reach_metrics.csv",
        set(platforms),
        errors,
    )
    validate_weights(ROOT / "data" / "scoring_weights.csv", errors)
    score_rows = validate_generated_scores(
        ROOT / "outputs" / "platform_scores.csv",
        platforms,
        errors,
    )
    validate_segment_summary(
        ROOT / "outputs" / "segment_summary.csv",
        score_rows,
        errors,
    )
    validate_images(errors)
    validate_visual_manifest(errors)
    validate_restricted_content(errors)

    if errors:
        raise SystemExit("\n".join(f"- {error}" for error in errors))
    print(
        "Public-release validation passed: core files, scoring contract, data integrity, "
        "visuals, and release-safety checks."
    )


if __name__ == "__main__":
    main()
