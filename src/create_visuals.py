#!/usr/bin/env python3
"""Create portfolio-ready PNG charts from the generated score outputs."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "outputs"
NAVY = "#173B57"
BLUE = "#3478A5"
LIGHT_BLUE = "#A9C8DA"
GRID = "#DDE5EA"
TEXT = "#24313A"
MUTED = "#5D6B74"
WHITE = "#FFFFFF"


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Helvetica.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size=size)
    return ImageFont.load_default()


def draw_header(draw: ImageDraw.ImageDraw, title: str, subtitle: str) -> None:
    draw.text((80, 54), title, fill=NAVY, font=font(38, bold=True))
    draw.text((80, 108), subtitle, fill=MUTED, font=font(20))


def fit_label(value: str, limit: int) -> str:
    return value if len(value) <= limit else value[: limit - 1].rstrip() + "…"


def create_top_scores(scores: pd.DataFrame) -> None:
    ranked = (
        scores.loc[scores["ranking_status"].eq("ranked")]
        .sort_values(["total_score", "platform_name"], ascending=[False, True])
        .head(15)
        .sort_values("total_score")
    )
    width, height = 1600, 1080
    image = Image.new("RGB", (width, height), WHITE)
    draw = ImageDraw.Draw(image)
    draw_header(
        draw,
        "Top scored financial platforms",
        "Public-source reach, institution coverage, product breadth, and evidence quality",
    )
    left, right, top, bottom = 480, 1450, 190, 995
    chart_width = right - left
    for tick in range(6):
        x = left + chart_width * tick / 5
        draw.line((x, top, x, bottom), fill=GRID, width=2)
        draw.text((x - 7, bottom + 16), str(tick), fill=MUTED, font=font(18))
    draw.text((left, bottom + 52), "Weighted score (1–5)", fill=TEXT, font=font(19))

    row_height = (bottom - top) / max(len(ranked), 1)
    for index, (_, row) in enumerate(ranked.reset_index(drop=True).iterrows()):
        center_y = top + index * row_height + row_height / 2
        score = float(row["total_score"])
        bar_width = chart_width * score / 5
        label = fit_label(str(row["platform_name"]), 39)
        draw.text((80, center_y - 12), label, fill=TEXT, font=font(19))
        draw.rounded_rectangle(
            (left, center_y - 15, left + bar_width, center_y + 15),
            radius=8,
            fill=BLUE,
        )
        draw.text(
            (min(left + bar_width + 12, right - 52), center_y - 12),
            f"{score:.2f}",
            fill=TEXT,
            font=font(18, bold=True),
        )
    image.save(OUTPUT_DIR / "top_platform_scores.png", format="PNG", optimize=True)


def create_segment_coverage(summary: pd.DataFrame) -> None:
    plot_data = summary.sort_values("platform_count")
    width, height = 1600, 900
    image = Image.new("RGB", (width, height), WHITE)
    draw = ImageDraw.Draw(image)
    draw_header(
        draw,
        "Coverage by market segment",
        "Ranked platforms have measurable reach and at least one product observation",
    )
    left, right, top, bottom = 540, 1450, 205, 785
    chart_width = right - left
    max_count = max(int(plot_data["platform_count"].max()), 1)
    tick_step = 5 if max_count <= 35 else 10
    for tick in range(0, max_count + tick_step, tick_step):
        x = left + chart_width * tick / max_count
        draw.line((x, top, x, bottom), fill=GRID, width=2)
        draw.text((x - 6, bottom + 14), str(tick), fill=MUTED, font=font(18))

    row_height = (bottom - top) / max(len(plot_data), 1)
    for index, (_, row) in enumerate(plot_data.reset_index(drop=True).iterrows()):
        center_y = top + index * row_height + row_height / 2
        inventory = int(row["platform_count"])
        ranked = int(row["ranked_platform_count"])
        draw.text((80, center_y - 13), fit_label(str(row["segment"]), 44), fill=TEXT, font=font(20))
        inventory_width = chart_width * inventory / max_count
        ranked_width = chart_width * ranked / max_count
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

    legend_y = 825
    draw.rounded_rectangle((80, legend_y, 112, legend_y + 24), radius=5, fill=NAVY)
    draw.text((124, legend_y - 1), "Ranked", fill=TEXT, font=font(18))
    draw.rounded_rectangle((250, legend_y, 282, legend_y + 24), radius=5, fill=LIGHT_BLUE)
    draw.text((294, legend_y - 1), "Inventory", fill=TEXT, font=font(18))
    draw.text((left, bottom + 52), "Number of platforms", fill=TEXT, font=font(19))
    image.save(OUTPUT_DIR / "segment_coverage.png", format="PNG", optimize=True)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    scores = pd.read_csv(OUTPUT_DIR / "platform_scores.csv")
    summary = pd.read_csv(OUTPUT_DIR / "segment_summary.csv")
    create_top_scores(scores)
    create_segment_coverage(summary)
    print("Created top_platform_scores.png and segment_coverage.png.")


if __name__ == "__main__":
    main()
