# RoleLens Project File Index

> Updated: 2026-07-11  
> Purpose: Explain which files are canonical, supporting, or historical.

## Canonical Active Set

These files may define current product truth:

| File | Authority |
|---|---|
| `00_CORE_CONTEXT.md` | Current phase, boundaries, locked decisions, open questions |
| `01_RULES_SCORECARD.md` | Competition and submission readiness |
| `02_PROBLEM_BANK.md` | Selected problem and idea-selection prior |
| `03_RESEARCH_EVIDENCE.md` | Curated problem evidence |
| `04_DECISION_LOG.md` | Major decisions and alternatives |
| `05_PRODUCT_SPEC.md` | V1 product behavior and scope |
| `06_ARCHITECTURE_CODE_MAP.md` | Technical architecture and module ownership |
| `07_IBM_BOB_USAGE_LOG.md` | Detailed IBM Bob usage evidence |
| `08_CRITIQUE_TEST_LOG.md` | Red-team risks and tests |
| `09_PROMPT_KNOWLEDGE_BASE.md` | Prompt drafts subject to evaluation |
| `role_policy.json` | Machine-readable five-role boundaries |
| `reference_to_product_decisions.md` | Adopted/rejected ideas from references |
| `README_outline_latest.md` | Only active README outline; becomes `README.md` after implementation |
| `docs/evaluation.md` | Evaluation scenarios and rubric |
| `docs/bob_build_log.md` | Public-facing Bob build evidence |

This is the 15-file active truth set. Official captures and reference notes below are supporting evidence, not co-equal product specifications.

## Official / Competition Sources

`docs/official/` contains four local captures. Rules outrank the internal execution guide when they differ. Recheck time-sensitive requirements on the live challenge platform before submission.

## Reference Layer

`docs/references/` contains exactly one copy of each curated reference note:

- `official_hands_on_labs_notes.md`
- `onbrief_pattern_analysis.md`
- `assetopsbench_agent_architecture_notes.md`
- `repo_reference_index.md`

Reference-derived roles and architecture patterns are not product requirements unless adopted in `reference_to_product_decisions.md` and reflected in a canonical file.

## Historical Archive

`docs/archive/historical/` preserves superseded drafts for provenance. They are not active context and must not be supplied to an AI as current product truth without an explicit historical-analysis task.

## Naming Policy

- Canonical active files have stable names without dates or `(1)` suffixes.
- Only one active README outline is allowed.
- Dated drafts belong in the historical archive.
- When the repository implementation starts, the final public entry point is `README.md`.
