# Granite 4 H Small Semantic Calibration v2 — Human Review

## Frozen run

- Run ID: `sem-20260727t050305292079z-0d9abcdc596d`
- Reviewer model: `ibm/granite-4-h-small`
- Provider calls: 8
- Prompt SHA-256: `325AA3E20EB8CA0D2435B08D93D928F96ECDE2036ED59464BA911F4C76E4EC1C`
- Strict pass: 8 / 8
- Pass rate: 1.0
- Required detection recall: 1.0
- False-positive scenario count: 0
- Review status: `human_reviewed_calibration_regression`

## Human review

All eight model classifications agree with the pre-existing calibration
expectations:

- S1 returned no candidate for the supported bounded observation.
- S2 identified unsupported ROI or budget.
- S3 identified causation overreach.
- S4 identified unsupported company-specific scope.
- S5 identified role-boundary violation.
- S6 identified unsupported completion or validation.
- S7 identified citation-claim mismatch.
- S8 identified an unsupported company-specific claim without producing an
  ROI or budget label.

## Interpretation

- This is a calibration regression result, not an independent benchmark.
- The S1-S8 failures were used to calibrate the prompt.
- The original 4/8 pre-calibration baseline remains immutable.
- This result does not establish production reliability.
- Holdout v1 is non-blinded but was not run during calibration.
- Holdout results must not be used for further prompt tuning.
