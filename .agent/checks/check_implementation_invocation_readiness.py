#!/usr/bin/env python3
"""Check implementation invocation readiness without selecting or starting anything."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable

import approve_implementation_session
import check_implementation_runner_selection
import check_implementation_session_start
import initialize_portable_run
import validate_implementation_invocation_preflight
import validate_implementation_session_start_authorization


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / ".agent" / "policies" / "implementation-invocation-readiness.json"
FALSE_AUTHORIZATION_FIELDS = approve_implementation_session.FALSE_AUTHORIZATION_FIELDS

EXPECTED_POLICY: dict[str, Any] = {
    "version": 3,
    "purpose": "implementation_invocation_readiness_check",
    "mode": "readiness-check-only",
    "require_valid_preflight": True,
    "require_runner_selection_gate": True,
    "require_session_start_gate": True,
    "require_explicit_start_authorization": True,
    "runner_selection_gate_available": True,
    "session_start_gate_available": True,
    "explicit_start_authorization_available": True,
    "bindings": [
        ".agent/checks/check_implementation_invocation_readiness.py",
        ".agent/policies/implementation-invocation-readiness.json",
        ".agent/checks/check_implementation_session_start.py",
        ".agent/policies/implementation-session-start.json",
        ".agent/checks/check_implementation_runner_selection.py",
        ".agent/policies/implementation-runner-selection.json",
        ".agent/checks/validate_implementation_invocation_preflight.py",
        ".agent/policies/implementation-invocation-preflight-validation.json",
        ".agent/checks/validate_implementation_session_approval.py",
        ".agent/policies/implementation-session-approval-validation.json",
        ".agent/checks/assess_runner_readiness.py",
        ".agent/policies/runner-readiness.json",
        ".agent/checks/authorize_implementation_session_start.py",
        ".agent/policies/implementation-session-start-authorization.json",
        ".agent/checks/validate_implementation_session_start_authorization.py",
        ".agent/policies/implementation-session-start-authorization-validation.json",
    ],
}


def load_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    policy = json.loads(path.read_text(encoding="utf-8"))
    if policy != EXPECTED_POLICY:
        raise ValueError("Implementation invocation readiness policy does not match")
    return policy


def load_policies() -> dict[str, Any]:
    return {
        **validate_implementation_session_start_authorization.load_policies(),
        "invocation_readiness": load_policy(),
    }


def failure(rule: str, message: str, **details: Any) -> dict[str, Any]:
    return {"rule": rule, "message": message, **details}


def sha256_bytes(content: bytes) -> str:
    return approve_implementation_session.sha256_bytes(content)


def binding_records(policy: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
    records = initialize_portable_run.binding_records(policy["bindings"])
    digest = sha256_bytes((json.dumps(records, sort_keys=True) + "\n").encode("utf-8"))
    return records, digest


def base_result() -> dict[str, Any]:
    return {
        "invocation_ready": False,
        "preflight_valid": False,
        "runner_selection_ready": False,
        "session_start_ready": False,
        "start_authorization_valid": False,
        **{field: False for field in FALSE_AUTHORIZATION_FIELDS},
        "issue": None,
        "risk": None,
        "base_commit": None,
        "preflight_sha256": None,
        "runner_selection": None,
        "session_start": None,
        "start_authorization_validation": None,
        "readiness_bindings_sha256": None,
        "missing_gates": [],
        "missing_authorizations": [],
        "failures": [],
    }


def check_readiness(
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
    policies: dict[str, Any],
    readiness_runner: Callable[[Path, dict[str, Any]], dict[str, Any]] | None = None,
    authorization_receipt: Path | None = None,
    authorization_receipt_sha256: str | None = None,
) -> dict[str, Any]:
    result = base_result()
    result["preflight_sha256"] = preflight_sha256
    preflight_validation = validate_implementation_invocation_preflight.validate(
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
    )
    result.update(
        preflight_valid=preflight_validation["valid"],
        issue=preflight_validation.get("issue"),
        risk=preflight_validation.get("risk"),
        base_commit=preflight_validation.get("base_commit"),
    )
    if policies["invocation_readiness"]["require_valid_preflight"] and not result["preflight_valid"]:
        result["failures"].append(
            failure(
                "preflight_validation",
                "Invocation readiness requires a currently valid invocation preflight.",
                validation=preflight_validation,
            )
        )

    runner_selection = check_implementation_runner_selection.check_selection(
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
    )
    result["runner_selection"] = runner_selection
    result["runner_selection_ready"] = runner_selection["runner_selection_ready"]

    bindings, bindings_sha256 = binding_records(policies["invocation_readiness"])
    result["readiness_bindings_sha256"] = bindings_sha256
    if (
        policies["invocation_readiness"]["require_runner_selection_gate"]
        and not runner_selection["runner_selection_ready"]
    ):
        result["missing_gates"].append("runner_selection_gate")
        result["failures"].append(
            failure(
                "runner_selection_gate",
                "Runner-selection gate is not currently ready.",
                selection=runner_selection,
            )
        )

    session_start = check_implementation_session_start.check_start(
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
    )
    result["session_start"] = session_start
    result["session_start_ready"] = session_start["session_start_ready"]

    if policies["invocation_readiness"]["require_session_start_gate"] and not result["session_start_ready"]:
        result["missing_gates"].append("session_start_gate")
        result["failures"].append(
            failure(
                "session_start_gate",
                "Session-start gate is not currently ready.",
                session_start=session_start,
            )
        )
    if authorization_receipt is None or authorization_receipt_sha256 is None:
        result["missing_gates"].append("session_start_authorization_gate")
        result["missing_authorizations"].append("session_start_authorization")
        result["failures"].append(
            failure(
                "session_start_authorization_gate",
                "An exact session-start authorization receipt and SHA-256 are required.",
            )
        )
    else:
        authorization_validation = (
            validate_implementation_session_start_authorization.validate(
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
                policies,
                readiness_runner,
            )
        )
        result["start_authorization_validation"] = authorization_validation
        result["start_authorization_valid"] = authorization_validation["valid"]
        if (
            policies["invocation_readiness"]["require_explicit_start_authorization"]
            and not result["start_authorization_valid"]
        ):
            result["missing_gates"].append("session_start_authorization_gate")
            result["missing_authorizations"].append("session_start_authorization")
            result["failures"].append(
                failure(
                    "session_start_authorization_gate",
                    "The exact session-start authorization receipt is not currently valid.",
                    validation=authorization_validation,
                )
            )

    refreshed_bindings, refreshed_bindings_sha256 = binding_records(policies["invocation_readiness"])
    if refreshed_bindings != bindings or refreshed_bindings_sha256 != bindings_sha256:
        result["failures"].append(
            failure("state_changed", "Invocation readiness bindings changed during assessment.")
        )
    result["bindings"] = bindings
    result["invocation_ready"] = not result["failures"]
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
    parser.add_argument("--authorization-receipt", type=Path)
    parser.add_argument("--authorization-receipt-sha256")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def format_text(result: dict[str, Any]) -> str:
    status = "READY" if result["invocation_ready"] else "NOT_READY"
    lines = [
        f"implementation-invocation-readiness: {status} issue={result['issue'] or 'unknown'}",
        "runner_selected=false",
        "session_start_authorized=false",
        "agent_invocation_authorized=false",
    ]
    lines.extend(f"- {item['rule']}: {item['message']}" for item in result["failures"])
    return "\n".join(lines)


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = check_readiness(
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
            load_policies(),
            authorization_receipt=args.authorization_receipt,
            authorization_receipt_sha256=args.authorization_receipt_sha256,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        print(f"implementation-invocation-readiness: ERROR\n- {error}", file=sys.stderr)
        return 1
    if args.format == "json":
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(format_text(result))
    return 0 if result["invocation_ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
