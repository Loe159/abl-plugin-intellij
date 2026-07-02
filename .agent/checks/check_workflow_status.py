#!/usr/bin/env python3
"""Report the current local workflow capability status without authorizing anything."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Callable

import assess_runner_readiness
import diff_policy


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / ".agent" / "policies" / "workflow-status.json"
FALSE_AUTHORIZATION_FIELDS = (
    "authorized",
    "agent_invocation_authorized",
    "implementation_authorized",
    "repository_mutation_authorized",
    "network_authorized",
    "publication_authorized",
    "runner_selected",
    "session_start_authorized",
)

EXPECTED_POLICY: dict[str, Any] = {
    "version": 1,
    "purpose": "agentic_workflow_capability_status",
    "mode": "status-only",
    "capabilities": [
        {
            "id": "local_patch_guardrails",
            "status": "verified_non_authorizing",
            "implemented": True,
            "required_for_pilot": True,
            "evidence": [
                ".agent/checks/diff_policy.py",
                ".agent/checks/generate_complete_patch.py",
                ".agent/checks/classify_patch_risk.py",
                ".agent/checks/validate_implementation_patch.py",
                ".agent/checks/validate_implementation_patch_receipt.py",
            ],
        },
        {
            "id": "portable_phase_artifacts",
            "status": "verified_non_authorizing",
            "implemented": True,
            "required_for_pilot": True,
            "evidence": [
                ".agent/checks/validate_artifacts.py",
                ".agent/checks/initialize_portable_run.py",
            ],
        },
        {
            "id": "read_only_research_and_plan",
            "status": "manual_rehearsal_only",
            "implemented": True,
            "required_for_pilot": True,
            "evidence": [
                ".agent/adapters/manual_read_only.py",
                ".agent/checks/build_stage_context.py",
                ".agent/checks/validate_stage_output.py",
            ],
        },
        {
            "id": "supervised_implementation_contract",
            "status": "post_consumption_readiness_only",
            "implemented": True,
            "required_for_pilot": True,
            "evidence": [
                ".agent/checks/build_implementation_session.py",
                ".agent/checks/check_implementation_invocation_readiness.py",
                ".agent/checks/check_implementation_session_start.py",
                ".agent/checks/check_implementation_launch_readiness.py",
                ".agent/checks/run_implementation_quality_gate.py",
                ".agent/checks/validate_implementation_quality_gate.py",
                ".agent/policies/implementation-launch-readiness.json",
            ],
        },
        {
            "id": "enforced_implementation_runner",
            "status": "functional_supervised_runner_controls_incomplete",
            "implemented": True,
            "required_for_pilot": True,
            "evidence": [
                ".agent/checks/assess_runner_readiness.py",
                ".agent/checks/prove_runner_tool_allowlist.py",
                ".agent/checks/prove_local_adapter_environment_filter.py",
                ".agent/checks/build_supervised_runner_invocation.py",
                ".agent/checks/run_supervised_implementation.py",
                ".agent/adapters/local_implementation_adapter.py",
                ".agent/policies/runner-tool-allowlist-proof.json",
                ".agent/policies/local-adapter-environment-filter-proof.json",
                ".agent/policies/supervised-runner-invocation.json",
                ".agent/policies/supervised-implementation-runner.json",
                ".agent/policies/local-implementation-adapter.json",
            ],
        },
        {
            "id": "explicit_session_start_authorization",
            "status": "validated_exclusive_local_consumption",
            "implemented": True,
            "required_for_pilot": True,
            "evidence": [
                ".agent/checks/authorize_implementation_session_start.py",
                ".agent/checks/validate_implementation_session_start_authorization.py",
                ".agent/checks/consume_implementation_session_start_authorization.py",
                ".agent/checks/validate_implementation_session_start_consumption.py",
                ".agent/policies/implementation-session-start-authorization.json",
                ".agent/policies/implementation-session-start-authorization-validation.json",
                ".agent/policies/implementation-session-start-consumption.json",
                ".agent/policies/implementation-session-start-consumption-validation.json",
            ],
        },
        {
            "id": "approved_github_issue_ingestion",
            "status": "manual_snapshot_approval_only",
            "implemented": True,
            "required_for_pilot": True,
            "evidence": [
                ".agent/checks/approve_github_issue_snapshot.py",
                ".agent/policies/github-issue-ingestion.json",
            ],
        },
        {
            "id": "deterministic_draft_pr_publisher",
            "status": "explicit_request_only_not_authorized_by_status",
            "implemented": True,
            "required_for_pilot": True,
            "evidence": [
                ".agent/checks/check_draft_pr_publication_readiness.py",
                ".agent/checks/publish_draft_pr.py",
                ".agent/policies/draft-pr-publication-readiness.json",
                ".agent/policies/draft-pr-publisher.json",
            ],
        },
        {
            "id": "run_metrics",
            "status": "receipt_derived_observation_and_manual_recording",
            "implemented": True,
            "required_for_pilot": True,
            "evidence": [
                ".agent/checks/build_runner_metrics_observation.py",
                ".agent/policies/runner-metrics-observation.json",
                ".agent/checks/record_run_metrics.py",
                ".agent/policies/run-metrics.json",
            ],
        },
        {
            "id": "historical_golden_set",
            "status": "local_preflight_only",
            "implemented": False,
            "required_for_pilot": True,
            "evidence": [
                ".agent/checks/check_historical_golden_set_readiness.py",
                ".agent/policies/historical-golden-set-readiness.json",
                ".agent/checks/assess_golden_set_readiness.py",
                ".agent/policies/golden-set-readiness.json",
                ".agent/checks/draft_golden_set_manifest.py",
                ".agent/policies/golden-set-draft.json",
                ".agent/checks/draft_pr_golden_set_manifest.py",
                ".agent/policies/golden-set-pr-draft.json",
                ".agent/checks/approve_golden_set.py",
                ".agent/policies/golden-set-adoption.json",
                "evals/golden-set.yaml",
            ],
        },
        {
            "id": "multi_adapter_comparison",
            "status": "local_artifact_comparison_available_not_invoking",
            "implemented": True,
            "required_for_pilot": True,
            "evidence": [
                ".agent/checks/check_multi_adapter_comparison_readiness.py",
                ".agent/checks/validate_multi_adapter_comparison.py",
                ".agent/policies/multi-adapter-comparison-readiness.json",
                ".agent/policies/multi-adapter-comparison.json",
            ],
        },
    ],
    "bindings": [
        ".agent/checks/check_workflow_status.py",
        ".agent/policies/workflow-status.json",
        ".agent/checks/assess_runner_readiness.py",
        ".agent/policies/runner-readiness.json",
    ],
}


def load_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    policy = json.loads(path.read_text(encoding="utf-8"))
    if policy != EXPECTED_POLICY:
        raise ValueError("Workflow status policy does not match")
    return policy


def binding_records(repo: Path, paths: list[str]) -> list[dict[str, Any]]:
    records = []
    for name in paths:
        path = repo / name
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"Workflow status binding must be an existing regular file: {name}")
        content = path.read_bytes()
        records.append(
            {
                "name": name,
                "sha256": hashlib.sha256(content).hexdigest(),
                "size_bytes": len(content),
            }
        )
    return records


def evidence_records(repo: Path, capabilities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    paths = [path for capability in capabilities for path in capability["evidence"]]
    if len(paths) != len(set(paths)):
        raise ValueError("Workflow status evidence paths must be unique")
    return binding_records(repo, paths)


def runner_unready_controls(runner: dict[str, Any]) -> list[dict[str, str]]:
    controls = runner.get("controls", [])
    if not isinstance(controls, list):
        raise ValueError("Runner readiness controls must be a list when present")
    unready = []
    for control in controls:
        if not isinstance(control, dict):
            raise ValueError("Runner readiness control entries must be objects")
        control_id = control.get("id")
        status = control.get("status")
        if not isinstance(control_id, str) or not isinstance(status, str):
            raise ValueError("Runner readiness controls must include string id and status")
        if status != "satisfied":
            unready.append({"id": control_id, "status": status})
    return unready


def check_status(
    repo: Path,
    policy: dict[str, Any],
    readiness_runner: Callable[[Path, dict[str, Any]], dict[str, Any]] = (
        assess_runner_readiness.assess
    ),
) -> dict[str, Any]:
    repo_root = Path(
        diff_policy.run_git(repo, "rev-parse", "--show-toplevel").decode("utf-8").strip()
    ).resolve()
    evidence = evidence_records(repo_root, policy["capabilities"])
    bindings = binding_records(repo_root, policy["bindings"])
    runner = readiness_runner(repo_root, assess_runner_readiness.load_policy())
    if runner.get("assessment_complete") is not True:
        raise ValueError("Runner readiness assessment is incomplete")
    if any(runner.get(field) is not False for field in assess_runner_readiness.FALSE_FIELDS):
        raise ValueError("Runner readiness assessment overclaims authorization")
    unready_controls = runner_unready_controls(runner)

    capabilities = [dict(capability) for capability in policy["capabilities"]]
    runner_capability = next(
        capability for capability in capabilities if capability["id"] == "enforced_implementation_runner"
    )
    if runner.get("controls_ready") is True:
        runner_capability.update(status="controls_ready_not_authorized", implemented=True)

    missing = [
        capability["id"]
        for capability in capabilities
        if capability["required_for_pilot"] and not capability["implemented"]
    ]
    pilot_ready = not missing
    return {
        "status_version": policy["version"],
        "purpose": policy["purpose"],
        "mode": policy["mode"],
        "pilot_ready": pilot_ready,
        **{field: False for field in FALSE_AUTHORIZATION_FIELDS},
        "capabilities": capabilities,
        "missing_required_capabilities": missing,
        "runner_controls_ready": runner["controls_ready"],
        "runner_unready_controls": unready_controls,
        "runner_assessment": runner,
        "evidence_bindings": evidence,
        "status_bindings": bindings,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def format_text(result: dict[str, Any]) -> str:
    status = "READY" if result["pilot_ready"] else "INCOMPLETE"
    lines = [
        f"agentic-workflow-status: {status}",
        "agent_invocation_authorized=false",
        "publication_authorized=false",
    ]
    lines.extend(
        f"- {capability['id']}: {capability['status']}"
        for capability in result["capabilities"]
    )
    lines.extend(
        f"- runner-control {control['id']}: {control['status']}"
        for control in result["runner_unready_controls"]
    )
    return "\n".join(lines)


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = check_status(args.repo, load_policy())
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        print(f"agentic-workflow-status: ERROR\n- {error}", file=sys.stderr)
        return 1
    if args.format == "json":
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(format_text(result))
    return 0 if result["pilot_ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
