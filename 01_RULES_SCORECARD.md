# 01_RULES_SCORECARD.md — RoleLens

> Updated: 2026-07-11  
> Purpose: Single tracking surface for competition eligibility, submission readiness, judging readiness, and internal scoring discipline.  
> Status legend: `DONE`, `IN PROGRESS`, `NOT STARTED`, `NEEDS VERIFICATION`.

## Competition Identity

| Item | Current value | Status | Evidence / next action |
|---|---|---|---|
| Competition | IBM AI Builders Challenge — July 2026 | DONE | `docs/official/官方规则.txt` |
| Track | Wild Card — Build Intelligent Systems for the Future of Work | DONE | RoleLens is a decision-support workflow for future work |
| Participant mode | Solo student participant | NEEDS VERIFICATION | Confirm challenge-platform eligibility profile |
| Submission deadline | July 31, 2026 | NEEDS VERIFICATION | Recheck the live challenge page before submission; local official-rules capture states July 31 |
| Monthly submission limit | One project per month | NOT STARTED | Do not submit another July project |

## Hard Requirements

| Requirement | Status | Completion evidence | Next gate |
|---|---|---|---|
| Working prototype or proof of concept | NOT STARTED | — | Build and run the first vertical slice |
| IBM Bob used as primary development tool | IN PROGRESS | `07_IBM_BOB_USAGE_LOG.md`; `docs/bob_build_log.md` | Replace planned/template entries with actual prompts, outputs, human changes, tests, and dates |
| AI is a core functional component | IN PROGRESS | `05_PRODUCT_SPEC.md`; `06_ARCHITECTURE_CODE_MAP.md` | Demonstrate structured AI output inside the running prototype |
| Required IBM SkillsBuild activity completed | NEEDS VERIFICATION | `docs/official/官方资料.txt` contains study material only | Record completion/certificate evidence |
| Public GitHub repository | NOT STARTED | — | Create repo, add license/setup, confirm logged-out public access |
| Clear README with required sections | IN PROGRESS | `README_outline_latest.md` | Replace outline with final `README.md` after prototype exists |
| Challenge-platform project page | NOT STARTED | — | Draft and publish final submission page |
| Public demo/presentation video ≤ 3 minutes | NOT STARTED | — | Script, record, time, publish, test logged-out access |
| No exposed credentials or private data | IN PROGRESS | No runtime repository yet | Add `.gitignore`, scan history, use environment variables |

## Required README Coverage

| Section | Status | Current source |
|---|---|---|
| Selected challenge theme | DONE | `README_outline_latest.md` |
| Problem statement and target users | DONE | `02_PROBLEM_BANK.md`; `05_PRODUCT_SPEC.md` |
| Solution and core workflow | DONE | `05_PRODUCT_SPEC.md` |
| AI approach and architecture | IN PROGRESS | `06_ARCHITECTURE_CODE_MAP.md` |
| How IBM Bob was used | IN PROGRESS | Logs are templates/plans until actual build entries exist |
| Setup and run instructions | NOT STARTED | Requires working prototype |
| Evaluation and limitations | IN PROGRESS | `docs/evaluation.md`; requires prototype results |
| Screenshots/demo link | NOT STARTED | Requires working prototype and public video |

## Official Judging Readiness

The local official-rules capture names Technical Execution, Innovation, Challenge Fit, Implementation/Feasibility, and real-world impact language. These are readiness judgments, not invented final judge scores.

| Criterion | Current readiness | Evidence | Main gap |
|---|---|---|---|
| Technical execution | NOT STARTED | Architecture and evaluation plan only | No runnable prototype or test results |
| Innovation | IN PROGRESS | Evidence Objects, role boundaries, trajectory/evaluation decisions | Must prove differentiation in UI and behavior |
| Challenge fit | IN PROGRESS | Future-of-work decision workflow is well aligned | Must make user outcome visible in demo |
| Implementation / feasibility | IN PROGRESS | Scoped Streamlit/Python design | Validate parsing, structured output, latency, and failure handling |
| Real-world impact | IN PROGRESS | Problem/research evidence exists | Needs concrete before/after scenario and measurable outcome |

## Internal 80-Point Score Discipline

The **69/80** recorded in `02_PROBLEM_BANK.md` is frozen as the **2026-07-08 idea-selection prior**. It does not measure the current build and must not be described as a final score or first-place readiness.

Re-score only after a prototype can be run end-to-end. The evidence package must include:

1. A reproducible run on the chosen sample dataset
2. Evaluation results for the scenario set in `docs/evaluation.md`
3. At least one failure, human rejection, and revision trajectory
4. Actual IBM Bob build evidence
5. A timed evaluator path and draft three-minute demo

Until then, the product-completion score is **not assessed**.

## Immediate Build Gates

| Gate | Pass condition | Status |
|---|---|---|
| G1 — Intake | Sample CSV and context load with explicit validation errors | NOT STARTED |
| G2 — Evidence | Stable evidence IDs and source spans are visible | NOT STARTED |
| G3 — Roles | All five views obey `role_policy.json` and cite evidence IDs | NOT STARTED |
| G4 — Risk/workflow | Missing evidence blocks or qualifies downstream actions | NOT STARTED |
| G5 — Human review | A user can accept, edit, or reject before memo generation | NOT STARTED |
| G6 — Evaluation | At least one scenario produces a saved, repeatable result | NOT STARTED |
| G7 — Bob proof | At least one real Bob task links prompt → output → human change → verification | NOT STARTED |

## Source Hierarchy

1. Live challenge platform and official rules control if they conflict with local notes.
2. `docs/official/官方规则.txt` is the local rules capture.
3. `docs/official/IBM-AI-Builders-Challenge-2026-年-7-月执行手册.txt` is an internal execution guide, not an official rule source.
4. Reference notes and competitor repositories provide design inspiration only.
