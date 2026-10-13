#!/usr/bin/env python3
"""Create portfolio-ready PNG charts from the generated score outputs."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
from PIL import Image, ImageDraw, ImageFont
from PIL.PngImagePlugin import PngInfo


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "outputs"
TARGET_SEGMENT = "1 Kredi karşılaştırma"
DATA_SNAPSHOT = "September 2026"
SCORE_MAX = 5.0
MANIFEST_PATH = OUTPUT_DIR / "visual_manifest.json"

NAVY = "#173B57"
BLUE = "#3478A5"
LIGHT_BLUE = "#A9C8DA"
GRID = "#DDE5EA"
TEXT = "#24313A"
MUTED = "#5D6B74"
WHITE = "#FFFFFF"


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    filenames = (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf"
        if bold
        else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
        if bold
        else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
    )
    for candidate in filenames:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size=size)
    return ImageFont.load_default()


def draw_header(draw: ImageDraw.ImageDraw, title: str, subtitle: str) -> None:
    draw.text((80, 54), title, fill=NAVY, font=font(38, bold=True))
    draw.text((80, 108), subtitle, fill=MUTED, font=font(20))


def fit_label(value: str, limit: int) -> str:
    return value if len(value) <= limit else value[: limit - 1].rstrip() + "…"


def require_columns(frame: pd.DataFrame, columns: set[str], frame_name: str) -> None:
    missing = sorted(columns.difference(frame.columns))
    if missing:
        raise ValueError(f"{frame_name} is missing required columns: {', '.join(missing)}")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_visual_manifest(scores: pd.DataFrame, summary: pd.DataFrame) -> bytes:
    credit_rows = scores.loc[
        scores["segment"].eq(TARGET_SEGMENT) & scores["ranking_status"].eq("ranked")
    ]
    payload = {
        "manifest_version": 1,
        "renderer_source_sha256": sha256_file(Path(__file__)),
        "inputs": {
            "platform_scores.csv": sha256_file(OUTPUT_DIR / "platform_scores.csv"),
            "segment_summary.csv": sha256_file(OUTPUT_DIR / "segment_summary.csv"),
        },
        "charts": {
            "credit_comparison_scores.png": {
                "size": [1600, 1080],
                "target_segment": TARGET_SEGMENT,
                "ranked_rows": int(len(credit_rows)),
                "maximum_rows_shown": 15,
            },
            "segment_coverage.png": {
                "size": [1600, 960],
                "segments": int(len(summary)),
            },
        },
    }
    return (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )


def png_metadata(manifest_digest: str) -> PngInfo:
    metadata = PngInfo()
    metadata.add_text("visual_manifest_sha256", manifest_digest)
    return metadata


def create_credit_comparison_scores(
    scores: pd.DataFrame,
    manifest_digest: str,
) -> None:
    """Chart ranked credit-comparison platforms without implying a global ranking."""
    require_columns(
        scores,
        {
            "platform_name",
            "segment",
            "segment_rank",
            "ranking_status",
            "total_score",
        },
        "platform_scores.csv",
    )
    segment_scores = scores.loc[
        scores["segment"].eq(TARGET_SEGMENT) & scores["ranking_status"].eq("ranked")
    ].copy()
    segment_scores["segment_rank"] = pd.to_numeric(
        segment_scores["segment_rank"], errors="coerce"
    )
    segment_scores["total_score"] = pd.to_numeric(
        segment_scores["total_score"], errors="coerce"
    )
    ranked = (
        segment_scores.dropna(subset=["segment_rank", "total_score"])
        .sort_values(
            ["segment_rank", "total_score", "platform_name"],
            ascending=[True, False, True],
        )
        .head(15)
        .reset_index(drop=True)
    )

    width, height = 1600, 1080
    image = Image.new("RGB", (width, height), WHITE)
    draw = ImageDraw.Draw(image)
    draw_header(
        draw,
        "Credit comparison platform scores",
        "Descriptive model: institution/brand coverage · product breadth · source diversity",
    )
    left, right, top, bottom = 500, 1450, 200, 915
    chart_width = right - left
    for tick in range(6):
        x = left + chart_width * tick / SCORE_MAX
        draw.line((x, top, x, bottom), fill=GRID, width=2)
        draw.text((x - 7, bottom + 14), str(tick), fill=MUTED, font=font(18))
    draw.text(
        (left, bottom + 50),
        "Descriptive weighted score (1–5)",
        fill=TEXT,
        font=font(19),
    )

    if ranked.empty:
        draw.text(
            (80, top + 40),
            "No ranked platforms are available for this segment.",
            fill=MUTED,
            font=font(22),
        )
    else:
        row_height = (bottom - top) / len(ranked)
        for index, row in ranked.iterrows():
            center_y = top + index * row_height + row_height / 2
            score = max(0.0, min(float(row["total_score"]), SCORE_MAX))
            rank = int(row["segment_rank"])
            bar_width = chart_width * score / SCORE_MAX
            label = fit_label(f"#{rank}  {row['platform_name']}", 42)
            draw.text((80, center_y - 12), label, fill=TEXT, font=font(19))
            draw.rounded_rectangle(
                (left, center_y - 15, left + bar_width, center_y + 15),
                radius=8,
                fill=BLUE,
            )
            score_x = min(left + bar_width + 12, right - 52)
            draw.text(
                (score_x, center_y - 12),
                f"{score:.2f}",
                fill=TEXT,
                font=font(18, bold=True),
            )

    disclaimer = (
        f"Scope: Türkiye · Segment: {TARGET_SEGMENT} · Snapshot: {DATA_SNAPSHOT} · "
        "Public-source descriptive analysis; not financial advice."
    )
    draw.text((80, 1030), disclaimer, fill=MUTED, font=font(15))
    image.save(
        OUTPUT_DIR / "credit_comparison_scores.png",
        format="PNG",
        optimize=True,
        pnginfo=png_metadata(manifest_digest),
    )


def create_segment_coverage(summary: pd.DataFrame, manifest_digest: str) -> None:
    """Compare in-scope inventory with platforms eligible for descriptive scoring."""
    require_columns(
        summary,
        {"segment", "platform_count", "ranked_platform_count"},
        "segment_summary.csv",
    )
    plot_data = summary[["segment", "platform_count", "ranked_platform_count"]].copy()
    plot_data["platform_count"] = pd.to_numeric(
        plot_data["platform_count"], errors="coerce"
    )
    plot_data["ranked_platform_count"] = pd.to_numeric(
        plot_data["ranked_platform_count"], errors="coerce"
    )
    plot_data = plot_data.dropna(subset=["platform_count", "ranked_platform_count"])
    plot_data = plot_data.sort_values(["platform_count", "segment"])

    width, height = 1600, 960
    image = Image.new("RGB", (width, height), WHITE)
    draw = ImageDraw.Draw(image)
    draw_header(
        draw,
        "Coverage by market segment",
        "Türkiye inventory and local platforms eligible for the descriptive scoring model",
    )
    left, right, top, bottom = 540, 1450, 205, 755
    chart_width = right - left
    max_count = (
        max(int(plot_data["platform_count"].max()), 1) if not plot_data.empty else 1
    )
    tick_step = 5 if max_count <= 35 else 10
    tick_max = ((max_count + tick_step - 1) // tick_step) * tick_step
    for tick in range(0, tick_max + 1, tick_step):
        x = left + chart_width * tick / tick_max
        draw.line((x, top, x, bottom), fill=GRID, width=2)
        draw.text((x - 6, bottom + 14), str(tick), fill=MUTED, font=font(18))

    row_height = (bottom - top) / max(len(plot_data), 1)
    for index, (_, row) in enumerate(plot_data.reset_index(drop=True).iterrows()):
        center_y = top + index * row_height + row_height / 2
        inventory = max(int(row["platform_count"]), 0)
        ranked = max(min(int(row["ranked_platform_count"]), inventory), 0)
        draw.text(
            (80, center_y - 13),
            fit_label(str(row["segment"]), 44),
            fill=TEXT,
            font=font(20),
        )
        inventory_width = chart_width * inventory / tick_max
        ranked_width = chart_width * ranked / tick_max
        draw.rounded_rectangle(
            (left, center_y - 20, left + inventory_width, center_y + 20),
            radius=8,
            fill=LIGHT_BLUE,
        )
        if ranked > 0:
            draw.rounded_rectangle(
                (left, center_y - 20, left + ranked_width, center_y + 20),
                radius=8,
                fill=NAVY,
            )
        draw.text(
            (min(left + inventory_width + 12, right - 76), center_y - 13),
            f"{ranked}/{inventory}",
            fill=TEXT,
            font=font(18, bold=True),
        )

    legend_y = 820
    draw.rounded_rectangle((80, legend_y, 112, legend_y + 24), radius=5, fill=NAVY)
    draw.text((124, legend_y - 1), "Eligible and ranked", fill=TEXT, font=font(18))
    draw.rounded_rectangle(
        (330, legend_y, 362, legend_y + 24), radius=5, fill=LIGHT_BLUE
    )
    draw.text((374, legend_y - 1), "In-scope inventory", fill=TEXT, font=font(18))
    draw.text((left, bottom + 50), "Number of platforms", fill=TEXT, font=font(19))
    footnote = (
        "International benchmarks are excluded. Eligibility also requires product observations "
        f"and a cited source. Counts are not market share. Snapshot: {DATA_SNAPSHOT}."
    )
    draw.text((80, 900), footnote, fill=MUTED, font=font(15))
    image.save(
        OUTPUT_DIR / "segment_coverage.png",
        format="PNG",
        optimize=True,
        pnginfo=png_metadata(manifest_digest),
    )


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    scores = pd.read_csv(OUTPUT_DIR / "platform_scores.csv")
    summary = pd.read_csv(OUTPUT_DIR / "segment_summary.csv")
    manifest = build_visual_manifest(scores, summary)
    manifest_digest = hashlib.sha256(manifest).hexdigest()
    create_credit_comparison_scores(scores, manifest_digest)
    create_segment_coverage(summary, manifest_digest)
    MANIFEST_PATH.write_bytes(manifest)
    print(
        "Created credit_comparison_scores.png, segment_coverage.png, and "
        "visual_manifest.json."
    )


if __name__ == "__main__":
    main()
