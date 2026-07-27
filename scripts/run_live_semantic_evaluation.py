"""Explicit CLI for confirmed live Granite semantic evaluation."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Callable, Sequence


_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(_REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPOSITORY_ROOT))

from app.evaluation import load_semantic_scenarios
from app.evaluation_runner import (
    SemanticEvaluationArtifactError,
    SemanticEvaluationRunnerExecutionError,
    SemanticEvaluationRunnerInputError,
    run_live_semantic_evaluation,
    select_semantic_evaluation_scenarios,
    write_live_semantic_evaluation_artifacts,
)
from app.semantic_risk_reviewer import SemanticRiskProvider


def _parser() -> argparse.ArgumentParser:
    """Build the command-line parser without reading credentials."""
    parser = argparse.ArgumentParser(
        description=(
            "Run the fixed RoleLens semantic evaluation against a live "
            "Granite provider."
        )
    )
    parser.add_argument(
        "--scenario",
        action="append",
        dest="scenario_ids",
        metavar="ID",
        help="Scenario ID to run; repeat to select multiple scenarios.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts/evaluation"),
        help="Artifact directory (default: artifacts/evaluation).",
    )
    parser.add_argument(
        "--confirm-live",
        action="store_true",
        help="Explicitly permit provider construction and live calls.",
    )
    return parser


def _default_provider_factory() -> SemanticRiskProvider:
    """Construct Granite only after explicit CLI confirmation."""
    from app.granite_semantic_risk_provider import (
        GraniteSemanticRiskProvider,
    )

    return GraniteSemanticRiskProvider.from_env()


def _model_id(provider: SemanticRiskProvider) -> str:
    """Read the configured model label without exposing other settings."""
    value = getattr(provider, "_model_id", None)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return "<model ID unavailable>"


def main(
    argv: Sequence[str] | None = None,
    *,
    provider_factory: Callable[[], SemanticRiskProvider] | None = None,
) -> int:
    """Run the confirmed CLI path and return a process status code."""
    args = _parser().parse_args(argv)
    try:
        scenarios = load_semantic_scenarios()
        selected = select_semantic_evaluation_scenarios(
            scenarios,
            args.scenario_ids,
        )
    except (SemanticEvaluationRunnerInputError, ValueError):
        print("Invalid semantic evaluation scenario selection.", file=sys.stderr)
        return 2

    if not args.confirm_live:
        print(
            "Live semantic evaluation was not confirmed. "
            "Re-run with --confirm-live; zero provider calls were made.",
            file=sys.stderr,
        )
        return 2

    selected_ids = [scenario.scenario_id for scenario in selected]
    print("Selected scenario IDs: " + ", ".join(selected_ids))
    print(f"Expected provider call count: {len(selected)}")
    print(
        "NOTICE: All outputs remain pending human review and are "
        "non-authoritative."
    )

    factory = provider_factory or _default_provider_factory
    try:
        provider = factory()
    except Exception:
        print(
            "Live semantic evaluation provider setup failed.",
            file=sys.stderr,
        )
        return 1
    print(f"Model ID: {_model_id(provider)}")

    try:
        run = run_live_semantic_evaluation(provider, selected)
        json_path, markdown_path = write_live_semantic_evaluation_artifacts(
            run,
            selected,
            args.output_dir,
        )
    except (
        SemanticEvaluationRunnerExecutionError,
        SemanticEvaluationArtifactError,
        SemanticEvaluationRunnerInputError,
    ):
        print(
            "Live semantic evaluation failed; no completed summary should "
            "be reported.",
            file=sys.stderr,
        )
        return 1

    print(f"JSON artifact: {json_path}")
    print(f"Markdown artifact: {markdown_path}")
    print("Human review status: pending_human_review")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
