# 01_RULES_SCORECARD.md — RoleLens

> Updated: 2026-08-30
> Purpose: Final competition eligibility, submission readiness, and evidence-truthfulness tracker.
> Status legend: `DONE`, `IN PROGRESS`, `NEEDS VERIFICATION`.

## Competition Identity

| Item | Current value | Status | Evidence / remaining action |
|---|---|---|---|
| Competition | IBM AI Builders Challenge with IBM Bob — August 2026 | DONE | Local official-rules capture covers the August monthly competition |
| Theme | Wildcard Challenge — Build Intelligent Systems for the Future of Work | DONE | Active README and Decision 004 |
| Participant mode | Zhe Wang, solo participant | DONE | Active project documents |
| Submission deadline | August 31, 2026 | DONE | Local official-rules capture |
| Monthly submission limit | One project for the August monthly competition | DONE | Do not submit another August project |

## Hard Requirements

| Requirement | Status | Current evidence | Remaining gate |
|---|---|---|---|
| Working prototype / proof of concept | DONE | React Decision Room, FastAPI product API, deterministic Decision Diff, and repository tests | Preserve behavior during submission freeze |
| AI is a core functional component | DONE | Governed Granite role-impact path in `app/granite_role_brief_provider.py` and `app/product_api.py` | Describe its bounded role accurately |
| Public GitHub repository | DONE | `https://github.com/wangz99-crypto/rolelens` | Recheck logged-out access immediately before submission |
| Competition README | DONE | `README.md` contains current product, evaluation, setup, limitations, and provenance | Add public demo-video URL before submission |
| IBM Bob used as primary development tool | IN PROGRESS | Real architecture and Tasks 1–5 evidence in `07_IBM_BOB_USAGE_LOG.md` and `docs/bob_build_log.md` | Do not attribute later August commits without missing session evidence |
| Required IBM SkillsBuild activity | NEEDS VERIFICATION | Repository contains study material but no completion/certificate evidence | Verify completion externally |
| Challenge-platform project page | NEEDS VERIFICATION | No repository evidence of a submitted public page | Publish and verify before deadline |
| Public demo video ≤ 3 minutes | NEEDS VERIFICATION | No local media file or public URL was found during documentation audit | Add and test the final 2:57 public URL |
| No exposed credentials or private data | IN PROGRESS | Runtime secrets are environment-only; `.env` and Streamlit secrets are ignored; current tracked snapshot was reviewed | Complete any required Git-history secret scan |

## README Coverage

| Section | Status | Evidence |
|---|---|---|
| Selected challenge theme | DONE | `README.md` |
| Stale-decision problem and target user | DONE | `README.md` |
| Final Decision Diff solution and Hero | DONE | `README.md` |
| Current React/FastAPI/Granite architecture | DONE | `README.md` |
| Deterministic vs AI responsibility boundary | DONE | `README.md` |
| Evidence, provenance, and limitations | DONE | `README.md`; `sample_data/public/README.md` |
| Reviewed evaluation results | DONE | `README.md`; `docs/evaluation_runs/` |
| IBM Bob evidence boundary | DONE | `README.md`; both Bob logs |
| Setup and verification commands | DONE | `README.md` |
| Public demo-video link | NEEDS VERIFICATION | Placeholder remains until a public URL is supplied |

## Implemented Build Gates

| Gate | Repository evidence | Status |
|---|---|---|
| G1 — Intake | Validated CSV/text/form intake and explicit failures | DONE |
| G2 — Evidence | Stable Evidence IDs, scopes, exact locators, and provenance tests | DONE |
| G3 — Roles | Five policy-constrained roles with grounded references and final Role Impact Briefs | DONE |
| G4 — Risk and dependency control | Deterministic risk/workflow modules, semantic review, and Decision Diff propagation | DONE |
| G5 — Human revision | Accepted Assumption recalculation, revision history, and stale/current lifecycle | DONE |
| G6 — Evaluation | Frozen calibration and holdout packs with human-reviewed run artifacts | DONE |
| G7 — Bob proof | At least one real prompt → output → human correction → verification chain | DONE |

## Evaluation Evidence

| Pack | Reviewed result | Interpretation |
|---|---|---|
| Calibration regression | 8/8 strict; required detection recall 1.0; zero false-positive scenarios | Calibration regression only, not an independent benchmark |
| Frozen one-time holdout | 5/8 strict; required detection recall 0.5; zero evaluated false-positive scenarios | False negatives remained for unseen causation, role-boundary, and citation-mismatch wording |

The semantic reviewer remains probabilistic and non-authoritative. Human review remains required. Neither eight-scenario pack proves production reliability.

## Submission Readiness

| Area | Readiness | Evidence / remaining action |
|---|---|---|
| Technical execution | DONE | Runnable React/FastAPI prototype, deterministic domain logic, and repository test coverage |
| Challenge fit | DONE | Future-of-work decision coordination is visible in the final Hero and README |
| Implementation / feasibility | DONE | Clone/run commands, licensed demo assets, stateless backend, and bounded Granite path |
| Evaluation honesty | DONE | Calibration and holdout failures are disclosed without a reliability claim |
| Public-link package | IN PROGRESS | GitHub exists; public video and challenge-platform links still require verification |
| Submission action | NEEDS VERIFICATION | Do not mark complete until the platform confirms submission |

## Frozen Score Discipline

The **69/80** value in `02_PROBLEM_BANK.md` remains the historical **2026-07-08 idea-selection prior**. It is not a current product score, judge score, award claim, or completion assessment. No new judge score is asserted here.

## Source Hierarchy

1. Live challenge platform and official rules control time-sensitive submission requirements.
2. `docs/official/官方规则.txt` is the local official-rules capture.
3. The July execution guide is a historical internal guide, not an official rule source.
4. Current production code, reviewed test/evaluation artifacts, and the final React UI control present product truth.
5. Historical architecture and reference notes remain provenance, not current product positioning.
