# AGENTS.md

This file provides guidance to agents when working with code in this repository.

## Project Status

At initialization this was a pre-prototype repository with no source code — only planning and architecture documentation. **Always inspect the current repository state before describing what is or is not implemented.** The intended layout places all code under `app/`, with `requirements.txt` and `tests/` at the root.

## Stack

- **Language:** Python
- **UI:** Streamlit
- **Data:** pandas, openpyxl
- **Schema validation:** Pydantic
- **Testing:** pytest
- **Build tool / dev assistant:** IBM Bob (required by competition rules)

## Commands (once prototype exists)

```bash
streamlit run app/main.py          # run the app
pytest tests/                      # run all tests
pytest tests/test_role_policy.py   # run a single test file
```

## Architecture

All code lives under `app/`. Entry point is `app/main.py` (Streamlit). The pipeline is:

```
file_intake → data_parser / text_parser → data_health → evidence_builder
→ role_engine → risk_checker → workflow_planner
→ draft memo or proposed decision state → human review action
→ revised final memo (memo_generator)
```

## Critical Constraints

- **Evidence Objects are the mandatory grounding layer.** Role views, risk warnings, workflow steps, and final memo claims must each cite at least one `evidence_id`. The rule is: *no evidence ID, no decision claim.* Downstream modules may also receive validated structured context (e.g. `business_question`, `strategy_profile`, `data_health_summary`, `risk_results`, `role_views`, `human_review_actions`) but raw files, raw dataframes, and unparsed text must not bypass the intake, validation, and evidence-building layers.
- **Three distinct ID concepts are in play:**
  - `source_id` — identifies an uploaded dataset, report, or user-provided source
  - `evidence_id` — identifies one specific Evidence Object; this is what role views, risk warnings, workflow steps, and memo claims must cite
  - `source_locator` — records provenance within a source (sheet, column, row range, field name, or text span)
  - The generation algorithms for both `source_id` and `evidence_id` are open decisions to be resolved during the first schema task.
- **`config/role_policy.json` is the machine-readable authority** for all five role boundaries (allowed inputs, required outputs, forbidden actions, must-flag conditions). The role engine must enforce it, not work around it.
- **Roles are policy-constrained views over shared evidence** — not five independent AI agents. Do not add new user-facing roles.
- **Internal components** (Evidence Builder, Risk Reviewer, Workflow Planner, Decision Memo Composer) must not be presented as extra AI coworkers in the UI.
- V1 explicitly excludes: MCP servers, LangGraph/CrewAI, vector DB, email sending, real approval permissions, multi-user auth, and PDF OCR.

## Code Style

- Type hints and docstrings are required on all modules.
- Use Pydantic models for all structured outputs (defined in `app/schemas.py`).
- LLM output must be validated through Pydantic before rendering in the UI.
- Keep modules small and single-purpose (one file per pipeline stage as shown in the module map).
- `app/utils.py` is for shared helpers only — do not put business logic there.
- Decision trajectories (run logs) are saved as JSON to `outputs/run_logs/`.

## Canonical Files

`FILE_INDEX.md` defines the full 15-file canonical active set. All 15 files may define current product truth and must be kept consistent.

The subset below carries primary engineering authority:

| File | Authority |
|------|-----------|
| `00_CORE_CONTEXT.md` | Current phase, locked decisions, open questions |
| `05_PRODUCT_SPEC.md` | V1 product scope |
| `06_ARCHITECTURE_CODE_MAP.md` | Module map and schemas |
| `config/role_policy.json` | Role boundaries (runtime authority) |
| `reference_to_product_decisions.md` | Adopted/rejected design decisions |
| `docs/evaluation.md` | 8 evaluation scenarios with expected behavior and hard-fail conditions |

## IBM Bob Build Log

Every real Bob task must be logged in `docs/bob_build_log.md` and `07_IBM_BOB_USAGE_LOG.md` with: prompt → output summary → human changes → verification. Template-only entries do not count as competition evidence.
