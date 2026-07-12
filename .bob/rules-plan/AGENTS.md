# AGENTS.md — Plan Mode

This file provides guidance to agents when working with code in this repository.

## Non-Obvious Architectural Constraints

- **Evidence Objects are the mandatory grounding layer, not the only inputs.** The invariant is *no evidence ID, no decision claim*: every role view, risk warning, workflow step, and memo claim must cite an `evidence_id`. Downstream modules may also receive validated structured context such as `business_question`, `strategy_profile`, `data_health_summary`, `risk_results`, `role_views`, and `human_review_actions`. Raw files, raw dataframes, and unparsed text must not bypass the intake, validation, and evidence-building layers. The generation algorithms for both `source_id` and `evidence_id` are open decisions for the first schema task.
- **`role_policy.json` must remain machine-readable and runtime-loaded.** Do not bake role permissions into module logic. Future role changes must require only JSON edits.
- **The workflow planner is downstream of the risk checker, not parallel.** The planner must consume validated risk results. Critical risks and unmet prerequisites must block or qualify affected execution actions, but the planner must still generate remediation steps and prerequisite tasks for those gaps. Do not plan an architecture where all risks halt the planner completely.
- **Human review is a visible UI action with a defined lifecycle, not a logging step.** The required sequence is: workflow plan → draft memo or proposed decision state → human review action (Approve / Request changes / Add context / Mark not ready) → revised final memo. The final memo must reflect the human review action — a review step that only logs passively fails the product contract.
- **`docs/evaluation.md` defines 8 fixed evaluation scenarios**, each with explicit expected behavior and applicable hard-fail conditions. Any architecture that cannot satisfy the expected behavior of scenarios 1–8 (especially role dependency ordering) is not viable for V1.
- **Decision trajectory minimum fields are required** (see `reference_to_product_decisions.md` D3). Any plan for persistence or export must include those fields; the schema is extensible and additional fields may be added, but the required minimum fields must not be dropped.
- **Streamlit is the only UI framework in scope.** Any plan involving React, Next.js, or a separate frontend service is out of scope for V1.
- **LangGraph and CrewAI are explicitly delayed to post-V1** (decision D7). Do not plan architecture that requires them to function.
