# Methodology

## Research design

The project uses a structured market inventory and platform-level observations. Each observation links a platform, financial product, institution, source, date, and research method. The analysis aggregates those records to a common platform identifier before scoring.

The model is designed for market mapping. It does not evaluate creditworthiness, recommend a financial product, or estimate commercial returns.

## Eligibility

A platform is ranked when all of the following are true:

- its segment is within the defined project scope;
- an estimated monthly-visit value is available;
- at least one product observation is available.

Platforms with missing reach data remain in the output with `needs_reach_data` status. This keeps missing evidence distinct from a real zero.

## Scoring thresholds

### Market reach

| Estimated monthly visits | Score |
| ---: | ---: |
| 5,000,000 or more | 5 |
| 1,000,000–4,999,999 | 4 |
| 100,000–999,999 | 3 |
| 10,000–99,999 | 2 |
| Below 10,000 | 1 |

### Institution coverage

| Distinct institutions | Score |
| ---: | ---: |
| 15 or more | 5 |
| 10–14 | 4 |
| 5–9 | 3 |
| 2–4 | 2 |
| 0–1 | 1 |

### Product breadth

One distinct product receives 1 point. Two, three, and four products receive 2, 3, and 4 points. Five or more receive 5 points.

### Evidence completeness

Completeness is the share of a platform's observation records containing both a source and an observation date.

| Complete-record share | Score |
| ---: | ---: |
| 95% or more | 5 |
| 85%–94.9% | 4 |
| 70%–84.9% | 3 |
| 50%–69.9% | 2 |
| Below 50% | 1 |

## Weighted score

The total score is calculated as:

```text
0.35 × market reach
+ 0.30 × institution coverage
+ 0.25 × product breadth
+ 0.10 × evidence completeness
```

The result is reported on a 1–5 scale. Global rank is descriptive. Segment rank is the preferred comparison because platform business models differ materially across segments.

## Limitations

- Public pages can change after the recorded observation date.
- Traffic estimates are directional rather than audited.
- An institution may be available only for a subset of products.
- A listing does not prove active commercial integration or user conversion.
- The model intentionally favors transparent, reproducible measures over private commercial assumptions.
