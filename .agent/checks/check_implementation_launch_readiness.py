#!/usr/bin/env python3
"""Check post-consumption implementation launch readiness without launching."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable

import approve_implementation_session
import check_implementation_invocation_readiness
import initialize_portable_run
import validate_implementation_session_start_consumption


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = (
    REPO_ROOT / ".agent" / "policies" / "implementation-launch-readiness.json"
)
FALSE_FIELDS = approve_implementation_session.FALSE_AUTHORIZATION_FIELDS

EXPECTED_POLICY: dict[str, Any] = {
    "version": 1,
    "purpose": "implementation_launch_readiness_check",
    "mode": "post-consumption-readiness-only",
    "require_invocation_ready": True,
    "require_valid_consumption_marker": True,
    "bindings": [
        ".agent/checks/check_implementation_launch_readiness.py",
        ".agent/policies/implementation-launch-readiness.json",
        ".agent/checks/check_implementation_invocation_readiness.py",
        ".agent/policies/implementation-invocation-readiness.json",
        ".agent/checks/validate_implementation_session_start_consumption.py",
        ".agent/policies/implementation-session-start-consumption-validation.json",
    ],
}


def load_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    policy = json.loads(path.read_text(encoding="utf-8"))
    if policy != EXPECTED_POLICY:
        raise ValueError("Implementation launch-readiness policy does not match")
    return policy


def load_policies() -> dict[str, Any]:
    return {
        **validate_implementation_session_start_consumption.load_policies(),
        "invocation_readiness": (
            check_implementation_invocation_readiness.load_policy()
        ),
        "launch_readiness": load_policy(),
    }


def failure(rule: str, message: str, **details: Any) -> dict[str, Any]:
    return {"rule": rule, "message": message, **details}


def base_result() -> dict[str, Any]:
    return {
        "launch_ready": False,
        "invocation_ready": False,
        "consumption_marker_valid": False,
        "session_start_authorization_consumed": False,
        **{field: False for field in FALSE_FIELDS},
        "issue": None,
        "risk": None,
        "base_commit": None,
        "workspace": None,
        "candidate_runner": None,
        "invocation_readiness": None,
        "consumption_validation": None,
        "failures": [],
    }


def check_launch(
    repo: Path,
    proposal: Path,
    proposal_sha256: str,
    workspace: Path,
    worktree_receipt: Path,
    worktree_receipt_sha256: str,
    approval_receipt: Path,
    approval_receipt_sha256: str,
    preflight: Path,
    preflight_sha256: str,
    authorization_receipt: Path,
    authorization_receipt_sha256: str,
    consumption_marker: Path,
    consumption_marker_sha256: str,
    policies: dict[str, Any],
    readiness_runner: Callable[[Path, dict[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    result = base_result()
    policy = policies["launch_readiness"]
    invocation = check_implementation_invocation_readiness.check_readiness(
        repo,
        proposal,
        proposal_sha256,
        workspace,
        worktree_receipt,
        worktree_receipt_sha256,
        approval_receipt,
        approval_receipt_sha256,
        preflight,
        preflight_sha256,
        policies,
        readiness_runner,
        authorization_receipt,
        authorization_receipt_sha256,
    )
    result.update(
        invocation_readiness=invocation,
        invocation_ready=invocation.get("invocation_ready") is True,
        issue=invocation.get("issue"),
        risk=invocation.get("risk"),
        base_commit=invocation.get("base_commit"),
    )
    if policy["require_invocation_ready"] and result["invocation_ready"] is not True:
        result["failures"].append(
            failure(
                "invocation_readiness",
                "Launch readiness requires current invocation readiness.",
                readiness=invocation,
            )
        )

    consumption = validate_implementation_session_start_consumption.validate(
        repo,
        proposal,
        proposal_sha256,
        workspace,
        worktree_receipt,
        worktree_receipt_sha256,
        approval_receipt,
        approval_receipt_sha256,
        preflight,
        preflight_sha256,
        authorization_receipt,
        authorization_receipt_sha256,
        consumption_marker,
        consumption_marker_sha256,
        policies,
        readiness_runner,
    )
    result.update(
        consumption_validation=consumption,
        consumption_marker_valid=consumption.get("valid") is True,
        session_start_authorization_consumed=(
            consumption.get("session_start_authorization_consumed") is True
        ),
        workspace=consumption.get("workspace"),
        candidate_runner=consumption.get("candidate_runner"),
    )
    if (
        policy["require_valid_consumption_marker"]
        and result["consumption_marker_valid"] is not True
    ):
        result["failures"].append(
            failure(
                "consumption_marker_validation",
                "Launch readiness requires a valid consumption marker.",
                validation=consumption,
            )
        )

    bindings = initialize_portable_run.binding_records(policy["bindings"])
    refreshed_bindings = initialize_portable_run.binding_records(policy["bindings"])
    if not validate_implementation_session_start_consumption.validate_implementation_session_start_authorization.exact_equal(
        refreshed_bindings,
        bindings,
    ):
        result["failures"].append(
            failure("state_changed", "Launch-readiness bindings changed.")
        )
    result["bindings"] = bindings
    result["launch_ready"] = not result["failures"]
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--proposal", type=Path, required=True)
    parser.add_argument("--proposal-sha256", required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--worktree-receipt", type=Path, required=True)
    parser.add_argument("--worktree-receipt-sha256", required=True)
    parser.add_argument("--approval-receipt", type=Path, required=True)
    parser.add_argument("--approval-receipt-sha256", required=True)
    parser.add_argument("--preflight", type=Path, required=True)
    parser.add_argument("--preflight-sha256", required=True)
    parser.add_argument("--authorization-receipt", type=Path, required=True)
    parser.add_argument("--authorization-receipt-sha256", required=True)
    parser.add_argument("--consumption-marker", type=Path, required=True)
    parser.add_argument("--consumption-marker-sha256", required=True)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def format_text(result: dict[str, Any]) -> str:
    status = "READY" if result["launch_ready"] else "NOT_READY"
    lines = [
        f"implementation-launch-readiness: {status} "
        f"issue={result['issue'] or 'unknown'}",
        "runner_selected=false",
        "agent_invocation_authorized=false",
        "implementation_started=false",
    ]
    lines.extend(f"- {item['rule']}: {item['message']}" for item in result["failures"])
    return "\n".join(lines)


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = check_launch(
            args.repo,
            args.proposal,
            args.proposal_sha256,
            args.workspace,
            args.worktree_receipt,
            args.worktree_receipt_sha256,
            args.approval_receipt,
            args.approval_receipt_sha256,
            args.preflight,
            args.preflight_sha256,
            args.authorization_receipt,
            args.authorization_receipt_sha256,
            args.consumption_marker,
            args.consumption_marker_sha256,
            load_policies(),
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        print(f"implementation-launch-readiness: ERROR\n- {error}", file=sys.stderr)
        return 1
    if args.format == "json":
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(format_text(result))
    return 0 if result["launch_ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
