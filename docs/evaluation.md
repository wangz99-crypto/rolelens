# RoleLens Semantic Risk Evaluation Pack

## Purpose

Fixed, human-reviewed scenarios make semantic-review changes reproducible. They
let the same validated `SemanticRiskReviewResult` be scored with exact enum,
count, and disposition rules rather than with keyword matching or another
model. This harness never calls Granite.

The pack separates three concerns:

- Task 7A deterministic checks validate structural invariants such as evidence
  existence, active status, scope restrictions, and role-output identity.
- Task 7B probabilistic semantic review proposes non-authoritative candidates
  for risks that require interpreting the relationship between a claim and its
  cited evidence.
- Task 7C deterministically compares an already-produced reviewer result with
  human-reviewed fixture expectations.

A Task 7C pass means that one output satisfies one approved expectation. It
does not prove that the output is true or that the reviewer is generally
reliable.

## Fixed scenarios

| Scenario | Intended evaluation |
|---|---|
| `S1_supported_cautious_claim` | A directly supported, carefully scoped claim may pass with no candidate. |
| `S2_unsupported_roi_budget` | Detect an ROI or budget claim unsupported by financial evidence. |
| `S3_causation_overreach` | Detect causation asserted from observational association. |
| `S4_external_context_as_company_fact` | Detect explicitly synthetic external context used as company-specific proof; company-specific and causal-overreach labels may both be defensible. |
| `S5_role_boundary_violation` | Detect a strategic action outside the Data Engineer role boundary. |
| `S6_unsupported_completion_validation` | Detect planned validation presented as completed and approved. |
| `S7_citation_claim_mismatch` | Detect an unrelated claim attached to a syntactically valid citation. |
| `S8_ambiguous_partial_support` | Detect the subtle upgrade from an unverified investigation hypothesis to a company-specific likelihood and action priority. |

All examples are synthetic. The external-context example is explicitly
synthetic and is not company-specific evidence.

## Deterministic scoring

Every fixture represents exactly one `RoleView` claim: one
`GroundedFinding` at `claim_index=0`. For the scenario role only, a result
passes when:

1. the scenario role appears in `reviewed_role_keys`;
2. every matching-role candidate has `claim_index=0`;
3. every `must_detect` code appears on that index-0 claim;
4. no `must_not_detect` code appears;
5. every detected code is in `acceptable_codes`;
6. candidate count is within the approved minimum and maximum; and
7. every candidate disposition is approved for that scenario.

Candidate explanations are not scored. There is no fuzzy matching, semantic
keyword heuristic, model call, retry, or fallback in the evaluator. Granite may
produce multiple valid candidate codes; the fixture therefore records bounded
acceptable alternatives where human reviewers approved them.

S4 specifically permits simultaneous
`unsupported_company_specific_claim`, `causation_overreach`, and
`citation_claim_mismatch` candidates because its wording asserts that a
company outcome occurred "because of" synthetic external context. S8 does not
assert causation: its ambiguity is between citation mismatch and unsupported
company-specific support after an unverified investigation idea is promoted to
a likely segment characteristic and action priority.

The summary metrics are:

- **Pass rate:** passing scenarios divided by total scenarios.
- **Required-detection recall:** required risk codes detected divided by all
  required risk codes in the evaluated scenarios.
- **False-positive scenario count:** scenarios with no required code that fail
  because prohibited or unexpected candidates were returned.

Each metric uses `0.0` when its denominator is zero.

## Citation-only baseline

The citation-only baseline represents a checker that notices only that a
syntactically valid evidence ID is attached. It does not fabricate model output
and returns no semantic-risk candidates.

Every fixture states that its citation is valid. The baseline therefore passes
only the supported cautious scenario and fails S2-S8. Its purpose is narrow:

> valid citation != semantically supported claim

This is not a generic-LLM baseline and should not be reported as one.

## Recording a live Granite result

Task 7D provides an explicit live runner. From the repository root, the exact
all-scenario command is:

```text
python scripts/run_live_semantic_evaluation.py --confirm-live
```

To run a fixed subset, repeat the scenario option:

```text
python scripts/run_live_semantic_evaluation.py --confirm-live --scenario S2_unsupported_roi_budget --scenario S7_citation_claim_mismatch
```

`--confirm-live` is mandatory so that importing the runner, inspecting CLI
help, or accidentally omitting the flag cannot construct the provider or make
a paid network call. The complete fixture pack makes exactly eight sequential
provider calls: one call per scenario, with no retries, parallel calls, or
fallback model.

The default sanitized outputs are:

```text
artifacts/evaluation/semantic-evaluation-<run_id>.json
artifacts/evaluation/semantic-evaluation-<run_id>.md
```

An existing artifact is never overwritten. Live calls occur outside the
offline evaluation tests:

Each JSON scenario record and each Markdown expected cell preserves the full
bounded expectation: required codes, acceptable alternative codes, prohibited
codes, allowed dispositions, and minimum/maximum candidate counts. Artifacts
must not reduce the expectation to `must_detect` alone.

In particular, "no mandatory code" does not necessarily mean zero candidates.
S1 has no required or acceptable codes and requires exactly zero candidates.
S8 has no uniquely mandatory code but requires one or two candidates chosen
from `citation_claim_mismatch` and
`unsupported_company_specific_claim`, with `reviewer_uncertain` or
`needs_human_review` disposition.

1. Run the existing production semantic reviewer in an approved environment,
   loading credentials only from environment variables or an approved secret
   manager.
2. Do not paste API keys, project IDs, credential-bearing logs, or cloud
   identifiers into fixtures, documentation, or test output.
3. Validate the returned payload as `SemanticRiskReviewResult`.
4. For each fixture, construct one `RoleView` containing exactly one
   `GroundedFinding`, at index 0, and confirm its role is present in
   `reviewed_role_keys`.
5. Pass that validated result and the matching loaded scenario to
   `evaluate_semantic_scenario`.
6. Record only the risk codes, dispositions, deterministic pass/fail result,
   reviewer model label if policy permits, and human reviewer notes in a
   separate dated evaluation record.
7. Have a human reviewer approve or correct the label before using it in a
   report. Never copy model output into fixtures as ground truth without human
   review.

Every generated record begins with `pending_human_review`. A human reviewer
must inspect the fixture expectation, detected codes, disposition, and failure
reasons, then add notes to a separate reviewed copy or evaluation record. Do
not edit `semantic_risk_v1.json` to make a model output pass, and do not promote
model output into fixture ground truth automatically.

A failed scenario must be reported and annotated; it must not be deleted,
silently skipped, or omitted from the completed run. The deterministic model
score records agreement with the current fixture expectations. A
human-approved score exists only after a reviewer explicitly accepts or
corrects the scenario labels. These two scores must remain distinguishable,
and neither is statistical proof of general reliability.

Suggested result table:

| scenario | expected | detected | disposition | pass/fail | reviewer notes |
|---|---|---|---|---|---|
| `S1_supported_cautious_claim` | No semantic candidate required |  |  |  |  |
| `S2_unsupported_roi_budget` | `unsupported_roi_or_budget` |  |  |  |  |
| `S3_causation_overreach` | `causation_overreach` |  |  |  |  |
| `S4_external_context_as_company_fact` | `unsupported_company_specific_claim` |  |  |  |  |
| `S5_role_boundary_violation` | `role_boundary_violation` |  |  |  |  |
| `S6_unsupported_completion_validation` | `unsupported_completion_or_validation_claim` |  |  |  |  |
| `S7_citation_claim_mismatch` | `citation_claim_mismatch` |  |  |  |  |
| `S8_ambiguous_partial_support` | Approved ambiguous candidate |  |  |  |  |

## Calibration and frozen holdout packs

The original S1-S8 pack is the calibration and regression pack. The H1-H8
`semantic_risk_holdout_v1.json` pack is a one-time holdout created before any
semantic-review prompt calibration.

Freeze rules:

- Do not run holdout v1 until the calibrated semantic-review prompt is frozen
  and committed.
- Holdout results must not be used for further prompt tuning.
- Failed holdout scenarios must remain reported and must not be deleted.
- Holdout expectations must not be edited after viewing results.
- S1-S8 remain calibration/regression scenarios; H1-H8 remain one-time holdout
  scenarios.
- Neither eight-scenario pack provides statistical proof of production
  reliability.

Calibration regression command retained for reproducibility:

```text
python scripts/run_live_semantic_evaluation.py \
  --confirm-live \
  --scenario-pack calibration
```

One-time holdout command retained for reproducibility. Holdout v1 has already
been run after the calibrated prompt was frozen and committed; its results must
not be used for tuning:

```text
python scripts/run_live_semantic_evaluation.py \
  --confirm-live \
  --scenario-pack holdout
```

## Current reviewed results

The repository contains two human-reviewed post-calibration records:

| Pack | Reviewed result | Interpretation |
|---|---|---|
| [Calibration regression v2](evaluation_runs/2026-07-27_granite-4-h-small_calibration-v2-review.md) | Strict pass 8/8; pass rate 1.0; required-detection recall 1.0; false-positive scenario count 0 | Calibration regression only. These scenarios informed prompt calibration, so this is not an independent benchmark. |
| [Frozen holdout v1](evaluation_runs/2026-07-27_granite-4-h-small_holdout-v1-review.md) | Strict pass 5/8; pass rate 0.625; required-detection recall 0.5; false-positive scenario count 0; citation-only baseline 2/8 | One-time, non-blinded holdout. False negatives remained for H4 causation, H6 role-boundary, and H8 citation-mismatch wording. |

The semantic reviewer remains probabilistic and non-authoritative, and human
review remains required. These small packs do not support statistical
generalization or a claim of production reliability. The frozen fixtures,
expectations, scoring logic, raw outputs, and reviewed records remain
distinct and unchanged.

## Semantic prompt calibration v2

Calibration v2 uses only the original S1-S8 calibration/regression scenarios
and their frozen pre-calibration baseline review. Holdout v1 was
pre-registered and frozen before prompt calibration, and it was not run during
calibration. Prompt calibration was based on observed S1-S8 failures, not
holdout results. This is a non-blinded, one-time holdout, and its results must
not be used for further tuning.

The calibration goals are:

- eliminate the supported-claim false positive;
- require detection when a syntactically valid citation is semantically
  unrelated to its claim;
- prefer the specific company-scope taxonomy over generic citation mismatch
  when both are defensible; and
- prohibit ROI or budget labels when a claim contains no financial content.

The reviewed calibration regression and frozen holdout results are recorded
above. The original baseline, fixtures, raw artifacts, and reviewed records
remain immutable. Holdout results must not be used for further prompt tuning.

Regression acceptance gate:

- S1 returns zero candidates.
- S7 detects `citation_claim_mismatch`.
- S8 does not return `unsupported_roi_or_budget`.
- Strict calibration pass rate is at least 7/8.
- Required detection recall equals 1.0.
- `false_positive_scenario_count` equals 0.

Failure to meet every gate condition requires another calibration iteration
and does not permit a holdout run. Passing the gate does not establish general
reviewer reliability.

## Honest limitations

- Eight fixtures are not statistical proof of general reliability.
- Scenario labels are curated examples, not a representative performance
  distribution.
- Probabilistic model behavior may vary by model version and generation
  settings even though Task 7C scoring is deterministic.
- Human review owns the final scenario labels and any decision about whether a
  candidate is meaningful.
- `likely_supported` is not verified truth.
- A passing reviewer can still miss risks outside this small fixture set.
- Model output must never be copied into fixtures as ground truth without human
  review.
