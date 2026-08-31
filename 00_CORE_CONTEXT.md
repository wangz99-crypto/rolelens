# 00_CORE_CONTEXT.md — RoleLens

> Updated: 2026-08-30
> Status: Canonical final-submission context
> Purpose: Shared source of truth for IBM Bob, Codex, and human review.

## Project

**IBM AI Builders Challenge with IBM Bob — August 2026**

**Wildcard Challenge — Build Intelligent Systems for the Future of Work**

Participant: Zhe Wang — University of Dayton — M.S. Business Analytics — solo participant

## Selected Direction

**RoleLens — evidence-controlled, role-aware decision change workspace**

**Know what must change when the decision changes.**

RoleLens addresses decision state drift: a business decision can change when an accepted Assumption changes while the observed Evidence remains valid. The product rebuilds the accepted scenario deterministically, propagates dependency-aware role impact, shows a Decision Diff, and marks an earlier fingerprint-bound Granite brief STALE until it is regenerated from the new accepted state.

Primary user: Business Analyst, Strategy & Operations professional, or cross-functional decision owner.

## Product Boundary

RoleLens is a decision-support prototype, not a generic chatbot, generic BI platform, production approval system, or autonomous execution system.

### User-visible business roles

1. Executive
2. Data Analyst / Data Scientist
3. Data Engineer
4. Sales / Marketing
5. Project Manager

These are governed functional views over shared Evidence and accepted Decision state. They are not five independent agents. Runtime boundaries remain defined by `config/role_policy.json`.

### Final Hero Interaction

```text
Human changes an accepted business Assumption as a draft
→ draft remains UNSAVED until Recalculate
→ accepted recalculation rebuilds trusted scenario state
→ deterministic dependency propagation computes role impact
→ Decision Diff shows changed and unchanged outputs
→ prior fingerprint-bound AI brief becomes STALE
→ one governed IBM Granite call realizes five refreshed Role Impact Briefs
→ deterministic validation runs before display
```

Observed Evidence does not change merely because a scenario Assumption changes. A scenario clearing modeled break-even establishes eligibility for pilot review only; it does not approve or authorize execution.

## Implemented Competition Surface

- React / TypeScript / Vite Decision Room with Impact Map, Evidence depth, role drawers, and revision history
- FastAPI product API with stateless trusted-state reconstruction
- Decimal-based break-even scenario calculation
- Deterministic Decision Diff and dependency-aware role impact propagation
- Stable Evidence identity, source provenance, exact locators, and scope separation
- Accepted-state SHA-256 fingerprint and NOT_GENERATED / CURRENT / STALE AI lifecycle
- Deterministic `RoleBriefPlanSet` containing five roles × three SemanticAtoms
- One structured IBM watsonx.ai Granite 4-H Small call for all five role briefs
- Deterministic final refs, handoffs, and policy/safety validation
- Frozen semantic-review calibration and holdout evidence with human review
- Licensed, reproducible public IBM-hosted sample data

Historical Streamlit, workflow-planning, memo, and simulated-review modules remain in the repository, but they are not the final evaluator Hero path.

## Current Phase

**Final Submission / Submission Freeze**

The working prototype and final Hero are implemented. Current work is limited to submission documentation consistency, link accessibility, evidence truthfulness, and final package verification. Product behavior is frozen for this documentation closeout.

## Current Top Risks

1. Final README, canonical documents, demo narration, and challenge-platform copy must describe the same implemented Decision Diff Hero.
2. The public repository, demo video, and challenge-platform URLs must be checked from a logged-out session before submission.
3. IBM Bob claims must remain limited to activities supported by the two Bob logs; later commits cannot be attributed from commit existence alone.
4. IBM SkillsBuild completion and challenge-platform submission still require external verification.
5. The small semantic evaluation packs must not be presented as statistical or production reliability evidence.

## Locked Decisions That Remain Active

1. Evidence Objects are the mandatory grounding layer: no Evidence ID, no evidence-backed decision claim.
2. `source_id`, `evidence_id`, and exact `source_locator` serve distinct identity and provenance purposes.
3. Internal observations, external context, user Assumptions, stated priorities, and decision-only context remain epistemically distinct.
4. `app/identity.py` computes deterministic identities; `app/evidence_builder.py` is the Evidence Object minting boundary.
5. The five business roles are policy-constrained views over shared Evidence, not separate AI workers.
6. Human acceptance is required to change trusted Decision state; an unsaved draft cannot propagate impact.
7. Scenario arithmetic, break-even status, accepted-state transitions, role posture, refs, and handoffs are deterministic.
8. IBM Granite performs bounded language realization over a deterministic semantic plan. It does not invent financial math, choose Evidence, assign approval, or authorize execution.
9. Atom IDs provide governed semantic source binding, not formal proof of semantic equivalence.
10. Probabilistic semantic review is non-authoritative; human review remains required.
11. V1 excludes individual customer targeting, automatic outreach, real approval permissions, multi-user authentication, enterprise integrations, long-term memory, vector databases, and complex multi-agent infrastructure.
12. The historical **69/80** value is a July idea-selection prior, not a product-completion score or judge outcome.

## Historical Development Context

RoleLens development and project records began in July 2026. Decisions 001–003, July IBM Bob entries, architecture research, calibration work, and dated evaluation artifacts remain historically accurate and are preserved in their original records.

The final Hero emerged through the August 26–30 implementation sequence:

- `f02b62d` — metadata-driven Decision Diff engine
- `ddc680b` — Decision Diff bridge to RoleLens Evidence
- `c798107` — human decision-revision experience spike
- `79f8959` — React Decision Room and real baseline
- `b74b953` — trusted decision-impact propagation
- `689e96a` — Evidence, role, and revision depth
- `1d8c863` — licensed demo data and clone-ready setup
- `ca6191a` — governed IBM Granite role-impact briefs

These commits are implementation history. They are not, by themselves, evidence that IBM Bob performed each task.

## Remaining External Verification

- IBM SkillsBuild completion evidence
- Public demo-video URL and logged-out accessibility
- Challenge-platform project page and final submission state
- Logged-out public GitHub accessibility immediately before submission
- Historical-secret scan if required for the final security checklist

## Next Deliverable

**Final submission package verification**

Verify:

1. README, canonical documents, final demo narration, and platform copy are consistent.
2. Public repository and video links work without authentication.
3. Video duration is no longer than three minutes.
4. Bob claims map to actual logged prompts, outputs, human changes, and verification.
5. Frozen evaluation results are reported with their calibration/holdout limitations.
6. No credentials, private data, unsupported outcome claims, or production-readiness claims appear.

## Non-Negotiable Competition Rules

- IBM Bob is the primary development tool only to the extent evidenced by actual logs.
- AI is a core functional component.
- The prototype runs from documented setup instructions.
- The GitHub repository and final demo video must be publicly accessible.
- The demo video must be no longer than three minutes.
- Required IBM SkillsBuild activity must be completed and verified.
- Only one project may be submitted for the August monthly competition.

See `01_RULES_SCORECARD.md` for current readiness status.
