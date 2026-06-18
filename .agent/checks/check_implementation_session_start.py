#!/usr/bin/env python3
"""Check implementation session-start preconditions without starting anything."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable

import approve_implementation_session
import check_implementation_runner_selection
import initialize_portable_run


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / ".agent" / "policies" / "implementation-session-start.json"
FALSE_AUTHORIZATION_FIELDS = approve_implementation_session.FALSE_AUTHORIZATION_FIELDS

EXPECTED_POLICY: dict[str, Any] = {
    "version": 1,
    "purpose": "implementation_session_start_readiness_check",
    "mode": "session-start-readiness-only",
    "require_runner_selection_ready": True,
    "track_explicit_start_authorization": True,
    "explicit_start_authorization_available": True,
    "bindings": [
        ".agent/checks/check_implementation_session_start.py",
        ".agent/policies/implementation-session-start.json",
        ".agent/checks/check_implementation_runner_selection.py",
        ".agent/policies/implementation-runner-selection.json",
        ".agent/checks/validate_implementation_invocation_preflight.py",
        ".agent/policies/implementation-invocation-preflight-validation.json",
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
        raise ValueError("Implementation session-start policy does not match")
    return policy


def load_policies() -> dict[str, Any]:
    return {
        **check_implementation_runner_selection.load_policies(),
        "session_start": load_policy(),
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
        "session_start_ready": False,
        "runner_selection_ready": False,
        **{field: False for field in FALSE_AUTHORIZATION_FIELDS},
        "candidate_runner": None,
        "issue": None,
        "risk": None,
        "base_commit": None,
        "preflight_sha256": None,
        "runner_selection": None,
        "session_start_bindings_sha256": None,
        "missing_authorizations": [],
        "failures": [],
    }


def check_start(
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
) -> dict[str, Any]:
    policy = policies["session_start"]
    result = base_result()
    result["preflight_sha256"] = preflight_sha256
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
    result.update(
        runner_selection=runner_selection,
        runner_selection_ready=runner_selection["runner_selection_ready"],
        candidate_runner=runner_selection.get("candidate_runner"),
        issue=runner_selection.get("issue"),
        risk=runner_selection.get("risk"),
        base_commit=runner_selection.get("base_commit"),
    )
    if policy["require_runner_selection_ready"] and not runner_selection["runner_selection_ready"]:
        result["failures"].append(
            failure(
                "runner_selection_gate",
                "Session-start readiness requires runner-selection readiness.",
                selection=runner_selection,
            )
        )

    if policy["track_explicit_start_authorization"]:
        result["missing_authorizations"].append("session_start_authorization")

    bindings, bindings_sha256 = binding_records(policy)
    result["session_start_bindings_sha256"] = bindings_sha256
    refreshed_bindings, refreshed_bindings_sha256 = binding_records(policy)
    if refreshed_bindings != bindings or refreshed_bindings_sha256 != bindings_sha256:
        result["failures"].append(
            failure("state_changed", "Session-start bindings changed during assessment.")
        )
    result["bindings"] = bindings
    result["session_start_ready"] = not result["failures"]
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
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def format_text(result: dict[str, Any]) -> str:
    status = "READY" if result["session_start_ready"] else "NOT_READY"
    runner = result["candidate_runner"]["id"] if result["candidate_runner"] else "unknown"
    lines = [
        f"implementation-session-start: {status} candidate={runner}",
        "runner_selected=false",
        "session_start_authorized=false",
        "agent_invocation_authorized=false",
    ]
    lines.extend(f"- {item['rule']}: {item['message']}" for item in result["failures"])
    if result["missing_authorizations"]:
        lines.append(
            "- authorization: an explicit session-start authorization receipt "
            "is required separately"
        )
    return "\n".join(lines)


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = check_start(
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
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        print(f"implementation-session-start: ERROR\n- {error}", file=sys.stderr)
        return 1
    if args.format == "json":
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(format_text(result))
    return 0 if result["session_start_ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
