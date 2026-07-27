# Granite 4 H Small Semantic Holdout v1 — Human Review

## Frozen run

- Run ID: `sem-20260727t050716864886z-75993803fc18`
- Reviewer model: `ibm/granite-4-h-small`
- Provider calls: 8
- Strict pass: 5 / 8
- Pass rate: 0.625
- Required detection recall: 0.5
- False-positive scenario count: 0
- Citation-only baseline: 2 / 8, pass rate 0.25
- Review status: `human_reviewed_holdout`
- Holdout status: consumed; must not be reused for prompt tuning

## Human review

- H1: correct supported-control result; no candidate.
- H2: correct supported-control result; no candidate.
- H3: correct unsupported ROI/payback classification.
- H4: false negative; observational association was promoted to causation.
- H5: correct unsupported company-specific classification.
- H6: false negative; Data Engineer directed cross-functional customer action without approval.
- H7: correct unsupported completion/validation classification.
- H8: false negative; support-response evidence was unrelated to contract preference.

## Interpretation

- This non-blinded, one-time holdout produced 5/8 strict passes.
- Both supported controls passed, with zero evaluated false-positive scenarios.
- Generalization remained weak for unseen causation, role-boundary, and citation-mismatch wording.
- The semantic reviewer remains probabilistic and non-authoritative.
- Human review remains required.
- These results must not be used to tune the frozen v2 prompt.
- This is not statistical proof of production reliability.
