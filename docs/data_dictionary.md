# Data dictionary

## Source datasets

### `data/platforms.csv`

One row per mapped platform.

| Field | Definition |
| --- | --- |
| `platform_id` | Stable, non-empty identifier used across datasets; unique in this table |
| `platform_name` | Public-facing platform name |
| `country` | Primary country or market; only Türkiye records can enter the scoring scope |
| `category` | One or more observed platform categories |
| `products` | Human-readable summary of publicly observed product coverage |
| `standout_feature` | Short factual description of the platform |
| `bank_model` | Institution-model classification from the research |
| `website` | Main public website |
| `source_reference` | Supporting public source reference |
| `segment` | Analysis segment; `Kapsam dışı` marks an inventory row outside scoring scope |

### `data/platform_observations.csv`

One public observation of a platform-product-institution combination. Exact duplicate rows are not allowed.

| Field | Definition |
| --- | --- |
| `platform_id` | Join key to the platform inventory |
| `platform_name` | Canonical platform label recorded with the observation |
| `category` | Category observed for the record |
| `product` | Product type observed; distinct non-empty values contribute to `product_count` |
| `institution` | Institution shown on the platform, or an explicit not-observed marker |
| `institution_type` | Conventional, participation, digital/other, or another observed type |
| `visibility_note` | Short factual note about what was publicly visible |
| `source_url` | Public HTTP(S) page used for the observation |
| `observed_date` | Valid calendar date in ISO `YYYY-MM-DD` format |
| `research_method` | Collection method recorded during research |

### `data/sources.csv`

Structured public-source records associated with mapped platforms. Multiple rows may point to the same URL; source diversity uses distinct normalized URLs per platform.

| Field | Definition |
| --- | --- |
| `platform_id` | Join key to the platform inventory |
| `platform_name` | Canonical platform label |
| `source_type` | Source role, such as the platform website or a supporting reference |
| `source_url` | Public source URL |

### `data/reach_metrics.csv`

Supplementary, experimental reach context. These fields do not affect score, eligibility, or segment rank.

| Field | Definition |
| --- | --- |
| `platform_id` | Join key to the platform inventory |
| `platform_name` | Canonical platform label |
| `estimated_monthly_visits` | Directional, unaudited monthly website-visit estimate |
| `measurement_note` | Free-text measurement period, method, or provenance note |
| `verification_note` | Free-text note about the public-data verification step |
| `website` | Platform website used as the entity reference |

### `data/scoring_weights.csv`

| Field | Definition |
| --- | --- |
| `criterion` | One of `institution_coverage`, `product_breadth`, or `source_diversity` |
| `weight` | Percentage weight; the three configured values must sum to 100 |
| `description` | Human-readable description of the criterion |

The expected weights are 45, 35, and 20 respectively.

## Generated datasets

### `outputs/platform_scores.csv`

One row per platform in the inventory.

| Field | Definition |
| --- | --- |
| `platform_id` | Stable platform identifier |
| `platform_name` | Public-facing platform name |
| `country` | Primary country or market |
| `segment` | Segment used for scope and peer ranking |
| `category` | Platform category copied from the inventory |
| `estimated_monthly_visits` | Optional supplementary reach estimate; excluded from scoring |
| `measurement_note` | Optional context for the reach estimate; excluded from scoring |
| `observation_count` | Number of observation rows associated with the platform |
| `institution_count` | Number of distinct, non-placeholder institution or financial-brand labels observed; not a legal-entity count |
| `product_count` | Number of distinct, non-empty product labels observed |
| `distinct_source_count` | Number of distinct valid normalized public URLs across observations and source records |
| `institution_coverage_score` | Institution-count component score from 1 to 5 |
| `product_breadth_score` | Product-count component score from 1 to 5 |
| `source_diversity_score` | Source-count component score from 1 to 5 |
| `total_score` | Weighted score on a 1-5 scale for eligible platforms; empty otherwise |
| `segment_rank` | Rank among eligible platforms in the same segment; empty otherwise |
| `ranking_status` | Eligibility/data-readiness status defined below |
| `website` | Main public platform website |

The allowed `ranking_status` values are:

| Status | Definition |
| --- | --- |
| `ranked` | In scope with at least one product and one valid public source |
| `out_of_scope` | Inventory row excluded from the scoring scope |
| `international_benchmark` | Non-Turkish comparator excluded from Turkish scoring and coverage denominators |
| `needs_product_data` | In scope but missing usable product evidence |
| `needs_source_data` | In scope but missing a valid public source |
| `needs_product_and_source_data` | In scope but missing both product and source evidence |

There is intentionally no global-rank field.

### `outputs/segment_summary.csv`

One row per in-scope segment.

| Field | Definition |
| --- | --- |
| `segment` | Market segment |
| `platform_count` | Mapped in-scope platforms in the segment |
| `ranked_platform_count` | Platforms with `ranking_status=ranked` |
| `coverage_pct` | Ranked platforms as a percentage of mapped platforms in the segment |
| `top_platforms` | All highest-scoring eligible platforms in the segment, alphabetically joined with ` | ` when tied |
| `top_score` | Score of the segment leader, if any |
| `average_ranked_score` | Mean score among eligible platforms in the segment, if any |

## Generated visuals

| File | Definition |
| --- | --- |
| `outputs/credit_comparison_scores.png` | 1600×1080 RGB chart of eligible platforms in the credit-comparison segment |
| `outputs/segment_coverage.png` | 1600×960 RGB comparison of Turkish in-scope and ranked platform counts by segment |
| `outputs/visual_manifest.json` | Hashes of the visualization source and input CSVs plus chart specifications; its digest is embedded in both PNGs so CI can detect stale committed visuals without requiring cross-platform PNG byte equality |
