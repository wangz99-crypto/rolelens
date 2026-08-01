# Dataset Primer and Granite Orientation Brief

Task 10C-2A adds a backend-only orientation layer for the explicitly selected
`ibm_telco_churn_v1` playbook. It is not generic CSV interpretation and does
not accept arbitrary datasets.

## Two distinct orientation artifacts

The `DatasetPrimer` is deterministic controlled text. It combines the typed
business profile with the frozen IBM fictional Telco context, glossary, and
provenance metadata. It contains the exact dataset counts, ten-field glossary,
unknown-currency notice, fictional-sample disclosure, and four fixed
guardrails. It remains available if Granite is unavailable.

The `DatasetOrientationBrief` is one optional Granite interpretation of that
primer and approved aggregate Evidence. Granite selects exactly four glossary
terms and explains exactly three aggregate patterns in plain business
language. It cannot replace or modify the deterministic primer guardrails.

## Provider data boundary

The orientation provider receives only:

- all controlled `DatasetPrimer` fields;
- seven minimal `OrientationEvidenceSnapshot` values; and
- the same seven Evidence IDs as a sorted allowlist.

The Evidence snapshots appear in this fixed order:

1. `business_overall_churn`
2. `business_contract_churn`
3. `business_support_churn`
4. `business_internet_churn`
5. `business_payment_churn`
6. `business_churn_medians`
7. `business_parseability`

No raw rows, individual customer IDs, supporting-evidence payloads, source
locators, source manifests, identity digests, dataframe previews, health
Evidence, industry context, strategy priority, or user assumptions are sent.
Every pattern citation is checked against the seven-ID allowlist after model
output is parsed.

## Interpretation boundaries

Observed differences are associations, not causal conclusions. The brief may
not estimate individual churn probability, identify or recommend customers,
authorize targeting or outreach, claim completed validation, or invent
currency, ROI, financial return, owners, deadlines, or completed work. The
currency used by `MonthlyCharges` and `TotalCharges` is unspecified.

The output validator intentionally uses a narrow controlled-language policy.
Granite is instructed to copy approved negative boundary sentences verbatim
as separate sentences rather than freely paraphrasing them. It may use only
the approved sentences needed for a response. Positive or ambiguous causal,
predictive, targeting, outreach, ROI, financial-return, and completion claims
fail output validation.

## Failure and runtime behavior

Orientation uses one synchronous Granite chat call with temperature zero and a
structured JSON schema. There is no retry, fallback model, cache, parallel
call, mock substitution, or manufactured successful brief. Provider,
structure, glossary-reference, and Evidence-reference failures become typed
`DatasetOrientationFailure` values with controlled reasons.

An orientation failure does not block or erase the existing five role views,
deterministic risk review, semantic review, workflow planning, human review,
or memo path. Live use adds one Granite call, so it also adds one call's
latency. The Streamlit Decision Brief and Role Comparison redesign are
deferred to Task 10C-2B.

## Future of Work value

Nontechnical employees receive a fast shared orientation before each function
applies its own governed perspective. Everyone starts from the same
deterministic facts, while role-specific interpretation remains constrained by
the existing Evidence and policy boundaries.
