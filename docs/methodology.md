# Methodology

## Purpose and research design

This project is a reproducible map of financial-product platforms operating in the Turkish market, supported by a separately classified international benchmark set. It uses a structured platform inventory plus public, date-limited observations. Each observation links a platform, product, institution, public URL, observation date, and research method.

The unit of analysis is a platform. Observation records are aggregated to the stable `platform_id` before scoring. The model supports exploratory market mapping; it does not evaluate creditworthiness, product suitability, service quality, conversion, or commercial returns.

## Scope and comparison rule

Platforms are assigned a country and market segment in `data/platforms.csv`. Scoring scope requires the country to be Türkiye and the segment not to be `Kapsam dışı`. International platforms remain visible with `international_benchmark` status but do not enter Turkish coverage denominators or ranks.

Eligible platforms receive a weighted score and a rank only among eligible peers in the same segment. The project intentionally does not calculate or publish a global rank: the segments represent materially different products and business models.

## Aggregated measures

### Institution coverage

`institution_count` is the number of distinct, non-placeholder institution or financial-brand labels observed for a platform. Blank values, explicit not-observed markers such as `Görünmüyor`, `Bulunamadı`, or `Bilinmiyor`, and unidentified-bank placeholders are excluded. The measure is label based: a bank and a separately branded digital proposition can count as two observed labels; it should not be interpreted as a count of legal entities.

| Distinct institutions | Component score |
| ---: | ---: |
| 15 or more | 5 |
| 10-14 | 4 |
| 5-9 | 3 |
| 2-4 | 2 |
| 0-1 | 1 |

### Product breadth

`product_count` is the number of distinct, non-empty product labels observed for a platform.

| Distinct products | Component score |
| ---: | ---: |
| 5 or more | 5 |
| 4 | 4 |
| 3 | 3 |
| 2 | 2 |
| 0-1 | 1 |

### Source diversity

`distinct_source_count` is the deduplicated count of valid HTTP(S) public-source URLs associated with a platform across both `data/platform_observations.csv` and `data/sources.csv`. The pipeline trims values and applies basic URL normalization before deduplication. Repeated use of the same normalized URL counts once.

| Distinct public-source URLs | Component score |
| ---: | ---: |
| 5 or more | 5 |
| 4 | 4 |
| 3 | 3 |
| 2 | 2 |
| 1 | 1 |

Source diversity measures the breadth of documented public evidence, not the authority, independence, or truth of every source.

## Weighted segment score

The score is calculated on a 1-5 scale:

```text
0.45 × institution_coverage_score
+ 0.35 × product_breadth_score
+ 0.20 × source_diversity_score
```

The configured weights in `data/scoring_weights.csv` must contain exactly these three criteria and sum to 100. The public-release validator enforces that contract.

The weights are an explicit descriptive-design choice rather than statistically estimated coefficients: observed institution/brand breadth receives the largest share, product breadth the second largest, and source diversity acts as a smaller documentation signal. They should be revisited for a different research question.

`segment_rank` uses the weighted score in descending order within each segment. Ties receive the same minimum rank. A score or segment rank is published only for an eligible platform.

## Eligibility and data-readiness statuses

A platform is eligible when all of the following are true:

- its country is Türkiye;
- its segment is in scope;
- `product_count` is greater than zero; and
- `distinct_source_count` is greater than zero.

`ranking_status` records the result:

| Status | Meaning |
| --- | --- |
| `ranked` | In scope with usable product and source data |
| `out_of_scope` | Retained in the inventory but excluded by the scope definition |
| `international_benchmark` | Non-Turkish comparator retained for research context but excluded from Turkish scores and coverage |
| `needs_product_data` | In scope and sourced, but no usable product observation is available |
| `needs_source_data` | In scope with product data, but no valid public source is available |
| `needs_product_and_source_data` | In scope with neither usable product nor source data |

Missing evidence is not converted to a zero. The platform remains visible in the generated output with its status.

## Market reach

`data/reach_metrics.csv` is supplementary and experimental. It retains an estimated monthly-visit value, a free-text `measurement_note`, and a `verification_note` for exploratory context.

Market-reach data is excluded from:

- the weighted score;
- scoring eligibility; and
- segment rank.

These values are directional rather than audited and may mix measurement periods or estimation methods. They must not be read as directly comparable performance figures.

## Evidence and release controls

- Observation URLs must use HTTP or HTTPS.
- `observed_date` must use ISO `YYYY-MM-DD` format and represent a valid calendar date.
- Platform identifiers must be unique.
- Exact duplicate observation rows are rejected.
- The release validator checks the weight contract, core files, expected visuals, and restricted confidential references.

## Limitations

- Public pages, URLs, institution coverage, and product availability can change after the recorded observation date.
- The inventory is broad but not guaranteed to include every platform in Turkey.
- A public listing does not prove an active integration, uniform user availability, approval probability, or conversion.
- Distinct product and institution labels depend on the public evidence available at collection time.
- Institution/brand labels are not consolidated to ultimate legal entities; branded digital propositions can remain separate.
- URL diversity is only a documentation signal; multiple URLs may rely on the same underlying claim.
- Segment scores are model-dependent and should not be interpreted as financial, credit, investment, or partnership advice.
