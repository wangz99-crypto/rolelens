# AGENTS.md — Agent (Coding) Mode

This file provides guidance to agents when working with code in this repository.

## Non-Obvious Coding Rules

- **Pydantic is the output contract, not a convenience.** Every LLM call must return a validated Pydantic model (defined in `app/schemas.py`). Never render free-form LLM text directly to the UI.
- **`role_policy.json` must be loaded at runtime** by `app/role_engine.py` — role constraints are not hardcoded. Changes to the policy file must be reflected without code changes.
- **Three distinct ID concepts — do not conflate them:**
  - `source_id` identifies an uploaded source (dataset, report, strategy profile)
  - `evidence_id` identifies one Evidence Object; role views, risk warnings, workflow steps, and memo claims must always cite an `evidence_id` — *no evidence ID, no decision claim*
  - `source_locator` records provenance within a source (sheet, column, row range, text span)
  - The generation algorithms for both `source_id` and `evidence_id` are open decisions for the first schema task; do not select or lock any format yet.
- **Decision trajectory persistence must go through a controlled boundary function**, not scattered file writes. `app/utils.py` may contain a small trajectory serialization helper, but it must not become a general file-writing dumping ground or hold business logic. Pipeline modules return validated Pydantic models; they do not write files.
- **Risk checker is not optional.** It must run before the workflow planner and produce validated risk results. Critical risks and unmet prerequisites must block or qualify affected execution actions; the planner must still generate remediation steps and prerequisite tasks for those gaps. Risk checker output is not a global stop — it is structured input that shapes the plan.
- **`data_health.py` warnings must propagate forward.** Downstream modules (role engine, risk checker) receive the `data_health_summary` dict — do not discard warnings after the health tab renders.
- **Evidence Objects are grounding inputs, not the only inputs.** Downstream modules may also receive validated structured context such as `business_question`, `strategy_profile`, `data_health_summary`, `risk_results`, `role_views`, and `human_review_actions`. Raw files, raw dataframes, and unparsed text must not bypass intake, validation, and evidence-building layers.
- **Test files go in `tests/`**, not alongside the source files. Test naming: `test_<module_name>.py`. Evaluation scenario tests go in `tests/test_scenarios.py`.
- **V1 excludes LangGraph, CrewAI, vector DB, and MCP** — do not add those imports even if they seem convenient.
- **The current planned Streamlit tabs are:** Intake, Data Health, Evidence Board, Role Views, Workflow Plan, Decision Memo. Do not add or remove tabs without updating `06_ARCHITECTURE_CODE_MAP.md` and confirming the change supports the demo and product scope.
