#!/usr/bin/env python3
"""Atomically consume one exact local session-start authorization receipt."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable

import authorize_implementation_session_start
import initialize_portable_run
import validate_implementation_session_start_authorization


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = (
    REPO_ROOT
    / ".agent"
    / "policies"
    / "implementation-session-start-consumption.json"
)
FALSE_FIELDS = authorize_implementation_session_start.FALSE_FIELDS

EXPECTED_POLICY: dict[str, Any] = {
    "version": 1,
    "purpose": "implementation_session_start_authorization_consumption",
    "mode": "local-exclusive-consumption-only",
    "marker_suffix": ".consumed.json",
    "max_marker_bytes": 40000,
    "require_valid_authorization_receipt": True,
    "require_absent_consumption_marker": True,
    "bindings": [
        ".agent/checks/consume_implementation_session_start_authorization.py",
        ".agent/policies/implementation-session-start-consumption.json",
        ".agent/checks/validate_implementation_session_start_authorization.py",
        ".agent/policies/implementation-session-start-authorization-validation.json",
    ],
}


def load_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    policy = json.loads(path.read_text(encoding="utf-8"))
    if policy != EXPECTED_POLICY:
        raise ValueError("Session-start consumption policy does not match")
    return policy


def load_policies() -> dict[str, Any]:
    return {
        **validate_implementation_session_start_authorization.load_policies(),
        "start_consumption": load_policy(),
    }


def failure(rule: str, message: str, **details: Any) -> dict[str, Any]:
    return {"rule": rule, "message": message, **details}


def canonical_marker_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def marker_path(authorization_receipt: Path, policy: dict[str, Any]) -> Path:
    receipt = authorization_receipt.resolve()
    marker = receipt.with_name(receipt.name + policy["marker_suffix"])
    if marker.is_symlink():
        raise ValueError("Session-start consumption marker symlinks are not allowed")
    if not marker.parent.is_dir():
        raise ValueError("Session-start consumption marker parent must exist")
    return marker


def base_result(
    authorization_receipt_sha256: str,
    marker: Path,
) -> dict[str, Any]:
    return {
        "consumed": False,
        "session_start_authorized": False,
        "session_start_authorization_consumed": False,
        **{field: False for field in FALSE_FIELDS},
        "authorizer_authenticated": False,
        "local_exclusive_marker_created": False,
        "ordinary_local_replay_rejected": False,
        "cross_host_replay_prevention_enforced": False,
        "tamper_resistant": False,
        "issue": None,
        "risk": None,
        "base_commit": None,
        "workspace": None,
        "candidate_runner": None,
        "authorization_receipt_sha256": authorization_receipt_sha256,
        "consumption_marker": str(marker),
        "consumption_marker_sha256": None,
        "failures": [],
    }


def consume(
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
    policies: dict[str, Any],
    readiness_runner: Callable[[Path, dict[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    policy = policies["start_consumption"]
    if authorization_receipt.is_symlink():
        raise ValueError("Session-start authorization receipt symlinks are not allowed")
    marker = marker_path(authorization_receipt, policy)
    result = base_result(authorization_receipt_sha256, marker)
    if policy["require_absent_consumption_marker"] and marker.exists():
        result["failures"].append(
            failure(
                "authorization_already_consumed",
                "The local session-start authorization consumption marker already exists.",
            )
        )
        result["ordinary_local_replay_rejected"] = True
        return result

    receipt_bytes = authorization_receipt.read_bytes()
    validation = validate_implementation_session_start_authorization.validate(
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
    result.update(
        session_start_authorized=validation.get("session_start_authorized") is True,
        authorizer_authenticated=validation.get("authorizer_authenticated") is True,
        issue=validation.get("issue"),
        risk=validation.get("risk"),
        base_commit=validation.get("base_commit"),
        workspace=validation.get("workspace"),
        candidate_runner=validation.get("candidate_runner"),
    )
    if policy["require_valid_authorization_receipt"] and validation.get("valid") is not True:
        result["failures"].append(
            failure(
                "authorization_receipt_validation",
                "Consumption requires a currently valid session-start authorization receipt.",
                validation=validation,
            )
        )
        return result
    if authorization_receipt.read_bytes() != receipt_bytes:
        result["failures"].append(
            failure(
                "authorization_receipt_changed",
                "Session-start authorization receipt changed before consumption.",
            )
        )
        return result

    bindings = initialize_portable_run.binding_records(policy["bindings"])
    marker_value = {
        "consumption_marker_version": policy["version"],
        "purpose": policy["purpose"],
        "mode": policy["mode"],
        **{field: False for field in FALSE_FIELDS},
        "session_start_authorized": True,
        "session_start_authorization_consumed": True,
        "authorizer_authenticated": False,
        "local_exclusive_marker_created": True,
        "ordinary_local_replay_rejected": True,
        "cross_host_replay_prevention_enforced": False,
        "tamper_resistant": False,
        "issue": validation["issue"],
        "risk": validation["risk"],
        "base_commit": validation["base_commit"],
        "workspace": validation["workspace"],
        "candidate_runner": validation["candidate_runner"],
        "authorization_receipt": str(authorization_receipt.resolve()),
        "authorization_receipt_sha256": authorization_receipt_sha256,
        "authorization_validation_sha256": (
            authorize_implementation_session_start.canonical_sha256(validation)
        ),
        "bindings": bindings,
    }
    marker_bytes = canonical_marker_bytes(marker_value)
    if len(marker_bytes) > policy["max_marker_bytes"]:
        raise ValueError("Session-start consumption marker exceeds byte limit")

    refreshed_validation = validate_implementation_session_start_authorization.validate(
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
    refreshed_bindings = initialize_portable_run.binding_records(policy["bindings"])
    if (
        authorization_receipt.read_bytes() != receipt_bytes
        or not validate_implementation_session_start_authorization.exact_equal(
            refreshed_validation,
            validation,
        )
        or not validate_implementation_session_start_authorization.exact_equal(
            refreshed_bindings,
            bindings,
        )
    ):
        result["failures"].append(
            failure(
                "state_changed",
                "Authorization, current validation, or producer bindings changed.",
            )
        )
        return result
    try:
        with marker.open("xb") as stream:
            stream.write(marker_bytes)
    except FileExistsError:
        result["failures"].append(
            failure(
                "authorization_already_consumed",
                "Another local consumer created the exclusive marker first.",
            )
        )
        result["ordinary_local_replay_rejected"] = True
        return result

    result.update(
        consumed=True,
        session_start_authorization_consumed=True,
        local_exclusive_marker_created=True,
        ordinary_local_replay_rejected=True,
        consumption_marker_sha256=(
            authorize_implementation_session_start.sha256_bytes(marker_bytes)
        ),
    )
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
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def format_text(result: dict[str, Any]) -> str:
    status = "CONSUMED" if result["consumed"] else "NOT_CONSUMED"
    lines = [
        f"implementation-session-start-consumption: {status} "
        f"issue={result['issue'] or 'unknown'}",
        "agent_invocation_authorized=false",
        f"local_exclusive_marker_created="
        f"{str(result['local_exclusive_marker_created']).lower()}",
        "cross_host_replay_prevention_enforced=false",
    ]
    lines.extend(f"- {item['rule']}: {item['message']}" for item in result["failures"])
    return "\n".join(lines)


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = consume(
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
            load_policies(),
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        print(f"implementation-session-start-consumption: ERROR\n- {error}", file=sys.stderr)
        return 1
    if args.format == "json":
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(format_text(result))
    return 0 if result["consumed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
