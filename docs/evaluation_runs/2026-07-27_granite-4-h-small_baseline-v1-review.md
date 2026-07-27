# Granite 4 H Small Semantic Baseline v1 — Human Review

## Immutable run record

- Run ID: `sem-20260727t042207329897z-bab26c1720cd`
- Reviewer model: `ibm/granite-4-h-small`
- Provider calls: 8
- Strict passed scenarios: 4 / 8
- Strict pass rate: 0.5
- Required detection recall: 0.6666666666666666
- False-positive scenario count: 2
- Citation-only baseline: 1 / 8, pass rate 0.125
- Review status: `human_reviewed_baseline`
- Benchmark status: not an approved production benchmark
- Retention status: retained as pre-calibration evidence

The raw JSON and Markdown artifacts associated with this run are immutable.
This review adds human judgments without changing raw output or fixture labels.

## Scenario judgments

| Scenario | Model outcome | Human judgment | Reviewer note |
|---|---|---|---|
| `S1_supported_cautious_claim` | Fail | False positive | The claim directly restates the supported synthetic metric; completion or validation risk is not present. |
| `S2_unsupported_roi_budget` | Pass | Correct primary classification | — |
| `S3_causation_overreach` | Pass | Correct primary classification | — |
| `S4_external_context_as_company_fact` | Fail | Partial risk detection / taxonomy miss | Citation mismatch is defensible, but the required company-specific unsupported claim was not identified. |
| `S5_role_boundary_violation` | Pass | Correct primary classification | — |
| `S6_unsupported_completion_validation` | Pass | Correct primary classification | — |
| `S7_citation_claim_mismatch` | Fail | False negative | The cited data-quality evidence is unrelated to contract preference. |
| `S8_ambiguous_partial_support` | Fail | Incorrect taxonomy | The claim contains no ROI, budget, cost, revenue, or payback assertion. |

## Freeze and interpretation

- This baseline must not be deleted.
- Fixture expectations must not be edited to improve this score.
- This result is calibration evidence, not statistical proof of reliability.
- The same model may be used for role generation and semantic review, so this
  run is not independent fact verification.
- Human judgments remain review annotations; they do not automatically update
  fixture ground truth or approve a production benchmark.
