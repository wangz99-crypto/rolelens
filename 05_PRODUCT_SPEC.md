# 05_PRODUCT_SPEC.md — RoleLens

> Updated: 2026-08-30
> Status: Product Spec v2.0 — final submission version
> Competition: IBM AI Builders Challenge with IBM Bob — August 2026
> Theme: Wildcard Challenge — Build Intelligent Systems for the Future of Work

## 1. Product Definition

**RoleLens is a role-aware, evidence-controlled decision change workspace.**

**Know what must change when the decision changes.**

RoleLens keeps a business Decision tied to accepted Evidence and explicit scenario Assumptions. When a human accepts an Assumption change, deterministic logic recomputes the modeled scenario, propagates role impact, produces a Decision Diff, and marks an older Granite brief STALE until it is refreshed from the new accepted state.

RoleLens is a bounded decision-support prototype. It is not a generic chatbot, generic BI copilot, autonomous workflow, or production approval system.

## 2. Problem Statement

Business decisions, source Evidence, human Assumptions, and AI interpretations do not change at the same time. A recommendation or role action that was reasonable for one accepted state can become invalid when a dependent Assumption changes—even though the underlying observed Evidence remains valid.

Without explicit dependency and lifecycle controls, teams can treat stale AI output as current. RoleLens makes the state transition and its cross-functional consequences visible.

## 3. Primary User and User Story

Primary user:

- Business Analyst
- Strategy & Operations professional
- Cross-functional decision owner

Core user story:

> As an analyst or decision owner, I want to understand how a change in an accepted business Assumption affects the current Decision and each function's next review action, so that stale Evidence interpretations, recommendations, and AI outputs are not accidentally treated as current.

## 4. Role Framework

The five user-visible role lenses are:

1. Executive
2. Data Analyst / Data Scientist
3. Data Engineer
4. Sales / Marketing
5. Project Manager

They are governed functional views over shared Evidence and accepted state, not five independent agents. Canonical machine keys and runtime boundaries remain controlled by `config/role_policy.json`:

```text
executive
data_analyst
data_engineer
sales_marketing
project_manager
```

Role relevance is a routing constraint, not proof that an Evidence item supports a particular claim. Role outputs remain subject to grounding and safety validation.

## 5. Final Evaluator Inputs

The competition demo uses a frozen public IBM-hosted Telco Customer Churn CSV plus RoleLens-authored context.

Accepted scenario Assumptions:

- Pilot population
- Expected incremental lift
- Cost per intervention
- Retained customer value
- Scenario currency (`USD`, explicitly supplied by RoleLens demo context)

The scenario fields are human-authored what-if Assumptions. They are not observed facts from the IBM-hosted dataset.

The wider evidence pipeline also supports validated CSV, pasted-text, and structured form-input sources with explicit semantic categories and scopes. Those capabilities do not turn the final evaluator path into an upload-and-chat product.

## 6. MVP Outputs

The final product surface includes:

1. Evidence Foundation summary and Evidence detail drawer
2. Accepted scenario Assumptions and UNSAVED draft state
3. Deterministic modeled scenario result and break-even status
4. Five-role Impact Map and role detail drawers
5. Accepted human revision and browser-session revision history
6. Decision Diff showing changed Assumptions, modeled value changes, and organizational impact
7. Changed, unchanged, recomputed, blocked, and stale dependency outcomes where applicable
8. Accepted-state SHA-256 fingerprint
9. IBM Granite Role Impact Brief with NOT_GENERATED / CURRENT / STALE lifecycle
10. Deterministically reconstructed Evidence refs, Assumption refs, and role-bounded handoff

## 7. Final Workflow

```text
1. FastAPI rebuilds the frozen Decision from governed public Evidence.
2. The Decision Room displays the accepted scenario, role posture, and Evidence foundation.
3. A human edits a scenario Assumption.
4. The draft becomes UNSAVED; trusted Decision state and any current Granite brief do not change.
5. The human selects Recalculate.
6. Decimal-based scenario logic rebuilds modeled economics and break-even status.
7. Decision Diff propagates dependency-aware role impact while unchanged Evidence remains locked.
8. The accepted-state fingerprint changes when the trusted state changes.
9. A brief generated for the prior fingerprint becomes STALE.
10. The human explicitly selects Generate Role Brief or Refresh Role Brief.
11. RoleLens builds and validates one deterministic RoleBriefPlanSet.
12. One IBM Granite call realizes all five role briefs.
13. Deterministic final validation runs before the briefs render.
```

Only accepted recalculation changes trusted state. Granite does not create or accept a Decision revision.

## 8. Signature Demo

Modeled scenario constants:

- Pilot population: 500
- Cost per intervention: 30 USD
- Retained customer value: 500 USD

Accepted 3% lift:

- Modeled net scenario value: −7,500 USD
- Status: `DOES_NOT_CLEAR_BREAK_EVEN`
- Sales / Marketing: blocked from pilot review

Draft 7% lift without Recalculate:

- Draft: UNSAVED
- Trusted state: remains at accepted 3%
- Existing 3% Granite brief: remains CURRENT

Accepted 7% lift through Recalculate:

- Modeled net scenario value: +2,500 USD
- Status: `CLEARS_BREAK_EVEN`
- Sales / Marketing: eligible for pilot review
- Previous 3% Granite brief: STALE

Refresh produces a new brief for the accepted 7% fingerprint and returns the lifecycle to CURRENT.

These are modeled scenario economics, not observed ROI. `CLEARS_BREAK_EVEN` is not approval, authorization, outreach permission, targeting permission, or execution authority.

## 9. Decision Diff and Accepted-State Contract

Scenario arithmetic uses Python `Decimal` values and validated Assumption contracts. Dependency metadata determines which downstream outputs are unchanged, recomputed, blocked, changed, or stale.

An accepted-state fingerprint binds canonical Decision identity, accepted Assumptions, modeled scenario results, role state, and governed Evidence identity. The frontend derives AI brief lifecycle as:

```text
no generated brief                         → NOT_GENERATED
brief fingerprint == accepted fingerprint → CURRENT
brief fingerprint != accepted fingerprint → STALE
```

An UNSAVED draft does not change the accepted fingerprint.

## 10. Governed Granite Contract

RoleLens uses this internal generation path:

```text
Trusted Decision
→ deterministic Decision Diff and role state
→ deterministic RoleBriefPlanSet
→ exactly 15 SemanticAtoms (5 roles × 3 sections)
→ one IBM Granite 4-H Small structured chat call
→ bounded role-readable language realization
→ deterministic whole-set safety validation
→ five existing RoleImpactBrief records
```

RoleLens determines the trusted scenario state and governed meaning available to each role. Granite expresses that meaning clearly.

Granite does not choose:

- Financial calculations or break-even status
- Role state or impact kind
- Evidence or Assumption references
- Handoff target or action
- Approval, authorization, outreach, targeting, or execution

Atom IDs bind provider output to the assigned governed semantic source. They do not prove formal semantic equivalence. Evidence refs, Assumption refs, and handoffs are deterministic ordered reconstructions from the validated plan. Malformed or policy-invalid output fails closed, with no retry or silent mock substitution.

## 11. Evidence and Provenance Contract

Every Evidence Object has stable identity and exact provenance:

```text
source_id      identifies a registered input source
evidence_id    identifies one governed Evidence Object
source_locator identifies the exact sheet, field, row range, or text span
```

Core rule:

```text
No evidence ID, no evidence-backed decision claim.
```

Identity boundaries:

- `app/identity.py` owns deterministic source and Evidence identity algorithms.
- `app/evidence_builder.py` is the only production boundary that mints `EvidenceObject` records from approved candidates.
- Full identity digests are stored separately from shortened display IDs.
- Identity generation uses canonical serialization, not timestamps, randomness, or Python `hash()`.

Source and Evidence scopes preserve epistemic meaning:

| Source scope | Resulting Evidence scope | Business meaning |
|---|---|---|
| `internal_observation` | `internal_observation` | May be presented as an observed dataset finding within its limitations |
| `external_context` | `external_context` | Context only; not company-specific proof |
| `user_assertion` | `assumption` | Human-supplied Assumption; not an observed fact |
| structured strategy assertion | `stated_priority` | Confirmed user intent; not measured performance |
| `decision_context` | no Evidence Object | Business question or goal controls trajectory but is not Evidence |

Health findings and exact-source text/context candidates remain distinct typed pre-minting contracts. Candidate, manifest, locator, semantic category, format, scope, and algorithm version must agree before minting.

## 12. Safety and Human Authority

- Role policies constrain allowed inputs, required outputs, forbidden actions, and must-flag conditions.
- Claim-level grounding remains required for evidence-backed role claims.
- External context cannot be promoted to internal proof.
- Assumptions cannot be presented as observed company performance.
- Probabilistic semantic review is non-authoritative and can miss unsupported wording.
- Deterministic validators reject malformed refs, unsafe authority claims, unsupported causal/predictive language, role-boundary violations, and unapproved handoffs where covered.
- Human review remains required for interpretation and final business action.
- The demo performs no individual customer targeting.

## 13. Implemented Must-Haves

1. Frozen public demo data with byte-level provenance and licensing
2. Deterministic source/Evidence identity and exact source locators
3. Evidence Foundation with explicit scope and limitations
4. Decimal-based scenario engine and break-even state
5. Human draft versus accepted revision boundary
6. Decision Diff and dependency-aware role impact propagation
7. React Decision Room with role, Evidence, and revision depth
8. Accepted-state fingerprint and CURRENT / STALE AI lifecycle
9. Deterministic five-role / 15-atom Role Brief plan
10. One governed watsonx.ai Granite call for five role briefs
11. Deterministic refs, handoffs, and safety validation
12. Frozen calibration and holdout evaluation artifacts with human review
13. Clone/run and frontend/backend verification commands

## 14. Technical Stack

```text
Frontend: React, TypeScript, Vite, Tailwind CSS, React Flow
Backend: FastAPI, Python
Contracts: Pydantic
Data processing: pandas
Runtime AI: IBM watsonx.ai, ibm/granite-4-h-small
Testing: pytest, Vitest, Testing Library, TypeScript build
Development tool: IBM Bob, only as evidenced in the Bob logs
```

The final evaluator surface is React/FastAPI. The repository also preserves earlier Streamlit and legacy pipeline modules as implementation history, not as the primary competition experience.

## 15. Out of Scope

- Production deployment or production approval system
- Real enterprise approvals, permissions, or execution
- Multi-user authentication or persistent enterprise Decision store
- Automatic customer outreach or individual targeting
- Predictive churn modeling or causal inference
- Guaranteed ROI, savings, or business outcomes
- Live web research or warehouse advisory
- Power BI / Tableau replacement
- Complex multi-agent framework, vector database, or long-term memory
- Automatic retries that hide an unsafe Granite realization
- Silent mock substitution for unavailable live credentials

## 16. Success Criteria

- A first-time evaluator can identify the stale-decision problem and Decision Diff Hero.
- An UNSAVED draft cannot alter trusted state or stale a current brief.
- Accepted 3% and 7% scenarios reproduce their exact modeled states.
- Observed Evidence remains unchanged across scenario-only revisions.
- Role impact changes are dependency-aware and visible.
- A prior fingerprint-bound brief becomes STALE after accepted state changes.
- Granite receives only the deterministic semantic plan and returns all five briefs in one call.
- Unsafe or malformed provider output fails closed.
- Demo-data provenance, licensing, Assumption boundaries, and limitations are visible.
- IBM Bob claims map to actual log evidence.
- The evaluator path can be completed within the required demo duration.

## 17. Limitations

- One competition demo Decision
- Browser-session revision history and stateless backend
- Public sample data, not production company data
- User-supplied what-if financial Assumptions
- No production customer targeting or execution authority
- Live Granite credentials required for explicit brief generation
- Granite latency and probabilistic output can vary
- Small evaluation packs do not establish general reliability
- Semantic source binding is not proof of semantic equivalence

## 18. IBM Bob Evidence Boundary

The two Bob logs contain real evidence for architecture planning and the first Tasks 1–5 implementation, including prompts, output summaries, human corrections, verification, and commit references. Later August product commits are not attributed to Bob without corresponding session evidence.

See `07_IBM_BOB_USAGE_LOG.md` and `docs/bob_build_log.md`.
