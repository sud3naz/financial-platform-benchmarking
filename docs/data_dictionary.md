# Data dictionary

## `data/platforms.csv`

| Field | Definition |
| --- | --- |
| `platform_id` | Stable, URL-safe identifier used across datasets |
| `platform_name` | Public-facing platform name |
| `country` | Primary country or market |
| `category` | One or more platform categories |
| `products` | Publicly observed product coverage |
| `standout_feature` | Short factual description of the platform |
| `bank_model` | Institution-model classification from the research |
| `website` | Main public website |
| `source_reference` | Supporting public source reference |
| `segment` | Analysis segment |

## `data/platform_observations.csv`

| Field | Definition |
| --- | --- |
| `platform_id` | Join key to the platform inventory |
| `platform_name` | Canonical platform label |
| `category` | Category observed for the record |
| `product` | Product type observed |
| `institution` | Institution shown on the platform, or an explicit not-observed marker |
| `institution_type` | Conventional, participation, digital/other, or another observed type |
| `visibility_note` | Short observation describing visibility |
| `source_url` | Public page used for the observation |
| `observed_date` | Observation date as recorded during research |
| `research_method` | Collection method recorded during research |

## `data/reach_metrics.csv`

| Field | Definition |
| --- | --- |
| `estimated_monthly_visits` | Directional monthly website-visit estimate |
| `data_date` | Date or reporting period associated with the estimate |
| `research_source` | Short provenance label |
| `website` | Platform website used as the entity reference |

## Generated outputs

`outputs/platform_scores.csv` contains the aggregated counts, four component scores, weighted total, eligibility status, and ranks. `outputs/segment_summary.csv` contains inventory size, measured coverage, ranked coverage, total measured visits, and the leading scored platform for each segment.
