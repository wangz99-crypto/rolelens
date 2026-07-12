# AGENTS.md — Ask Mode

This file provides guidance to agents when working with code in this repository.

## Non-Obvious Documentation Context

- **Always inspect the current repository before describing implementation status.** At initialization there was no source code — only planning and architecture documentation. The intended layout is documented in `06_ARCHITECTURE_CODE_MAP.md`, but actual file existence must be checked at the time of the query.
- **`FILE_INDEX.md` defines the canonical truth set.** When answering questions about product decisions or architecture, use only the 15 canonical files listed there. `docs/archive/historical/` contains superseded drafts — do not treat them as current.
- **`reference_to_product_decisions.md` is the filter.** Ideas from `docs/references/` are research inspiration only; they become product requirements only if explicitly adopted in `reference_to_product_decisions.md`.
- **The 69/80 score in `02_PROBLEM_BANK.md` is a frozen idea-selection prior from 2026-07-08**, not a progress or quality score. Do not quote it as a measure of completion.
- **`config/role_policy.json` is the authoritative source for role behavior.** When answering questions about what each role can or cannot do, read the JSON — the markdown docs are summaries only.
- **Evaluation rubric and hard-fail conditions live in `docs/evaluation.md`**, not in the product spec. Eight fixed scenarios each have explicit expected behavior and applicable hard-fail conditions — not every scenario triggers every hard-fail.
- **Two separate IBM Bob logs exist:** `docs/bob_build_log.md` is the public-facing log; `07_IBM_BOB_USAGE_LOG.md` is the internal evidence log. Inspect both logs before claiming whether they contain real evidence — at initialization they were empty templates, but entries may have been added since.
