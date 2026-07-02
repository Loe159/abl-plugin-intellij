#!/usr/bin/env python3
"""Validate one exact local session-start consumption marker."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable

import authorize_implementation_session_start
import build_stage_context
import consume_implementation_session_start_authorization
import diff_policy
import initialize_portable_run
import validate_implementation_session_start_authorization


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = (
    REPO_ROOT
    / ".agent"
    / "policies"
    / "implementation-session-start-consumption-validation.json"
)
FALSE_FIELDS = authorize_implementation_session_start.FALSE_FIELDS

EXPECTED_POLICY: dict[str, Any] = {
    "version": 1,
    "purpose": "implementation_session_start_consumption_validation",
    "mode": "validation-only",
    "max_marker_bytes": 40000,
    "require_external_consumption_marker": True,
    "require_marker_outside_workspace": True,
    "require_exact_derived_marker_path": True,
    "require_canonical_marker": True,
    "require_valid_authorization_receipt": True,
    "trusted_marker_bindings": (
        consume_implementation_session_start_authorization.EXPECTED_POLICY["bindings"]
    ),
    "validator_bindings": [
        ".agent/checks/validate_implementation_session_start_consumption.py",
        ".agent/policies/implementation-session-start-consumption-validation.json",
    ],
}


def load_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    policy = json.loads(path.read_text(encoding="utf-8"))
    if policy != EXPECTED_POLICY:
        raise ValueError("Session-start consumption validation policy does not match")
    return policy


def load_policies() -> dict[str, Any]:
    return {
        **consume_implementation_session_start_authorization.load_policies(),
        "start_consumption_validation": load_policy(),
    }


def failure(rule: str, message: str, **details: Any) -> dict[str, Any]:
    return {"rule": rule, "message": message, **details}


def base_result(marker_sha256: str) -> dict[str, Any]:
    return {
        "valid": False,
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
        "consumption_marker_sha256": marker_sha256,
        "failures": [],
    }


def validate_marker_value(
    value: Any,
    marker_path: Path,
    authorization_receipt: Path,
    authorization_receipt_sha256: str,
    authorization_validation: dict[str, Any],
    policy: dict[str, Any],
) -> list[dict[str, Any]]:
    expected_fields = {
        "consumption_marker_version",
        "purpose",
        "mode",
        *FALSE_FIELDS,
        "session_start_authorized",
        "session_start_authorization_consumed",
        "authorizer_authenticated",
        "local_exclusive_marker_created",
        "ordinary_local_replay_rejected",
        "cross_host_replay_prevention_enforced",
        "tamper_resistant",
        "issue",
        "risk",
        "base_commit",
        "workspace",
        "candidate_runner",
        "authorization_receipt",
        "authorization_receipt_sha256",
        "authorization_validation_sha256",
        "bindings",
    }
    if not isinstance(value, dict) or set(value) != expected_fields:
        return [failure("marker_schema", "Consumption marker fields do not match.")]

    producer = consume_implementation_session_start_authorization.EXPECTED_POLICY
    failures: list[dict[str, Any]] = []
    if (
        type(value["consumption_marker_version"]) is not int
        or value["consumption_marker_version"] != producer["version"]
        or value["purpose"] != producer["purpose"]
        or value["mode"] != producer["mode"]
        or any(value[field] is not False for field in FALSE_FIELDS)
        or value["session_start_authorized"] is not True
        or value["session_start_authorization_consumed"] is not True
        or value["authorizer_authenticated"] is not False
        or value["local_exclusive_marker_created"] is not True
        or value["ordinary_local_replay_rejected"] is not True
        or value["cross_host_replay_prevention_enforced"] is not False
        or value["tamper_resistant"] is not False
    ):
        failures.append(
            failure("marker_metadata", "Consumption marker safety metadata does not match.")
        )

    expected_identity = {
        "issue": authorization_validation["issue"],
        "risk": authorization_validation["risk"],
        "base_commit": authorization_validation["base_commit"],
        "workspace": authorization_validation["workspace"],
        "candidate_runner": authorization_validation["candidate_runner"],
    }
    if (
        any(
            not validate_implementation_session_start_authorization.exact_equal(
                value[field],
                expected,
            )
            for field, expected in expected_identity.items()
        )
        or value["authorization_receipt"] != str(authorization_receipt.resolve())
        or value["authorization_receipt_sha256"] != authorization_receipt_sha256
        or value["authorization_validation_sha256"]
        != authorize_implementation_session_start.canonical_sha256(
            authorization_validation
        )
    ):
        failures.append(
            failure("marker_identity", "Consumption marker identity does not match.")
        )

    trusted_bindings = initialize_portable_run.binding_records(
        policy["trusted_marker_bindings"]
    )
    if not validate_implementation_session_start_authorization.exact_equal(
        value["bindings"],
        trusted_bindings,
    ):
        failures.append(
            failure(
                "trusted_binding_mismatch",
                "Consumption marker bindings differ from trusted bytes.",
            )
        )
    derived = consume_implementation_session_start_authorization.marker_path(
        authorization_receipt,
        producer,
    )
    if policy["require_exact_derived_marker_path"] and marker_path != derived:
        failures.append(
            failure("marker_path", "Consumption marker path is not the derived path.")
        )
    return failures


def validate(
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
    result = base_result(consumption_marker_sha256)
    sha256_pattern = (
        authorize_implementation_session_start.approve_implementation_session.SHA256
    )
    if sha256_pattern.fullmatch(consumption_marker_sha256) is None:
        raise ValueError(
            "Expected consumption marker SHA-256 must be 64 lowercase hexadecimal characters"
        )
    if authorization_receipt.is_symlink() or consumption_marker.is_symlink():
        raise ValueError("Authorization receipt and consumption marker symlinks are not allowed")

    repo_root = Path(
        diff_policy.run_git(repo, "rev-parse", "--show-toplevel").decode("utf-8").strip()
    ).resolve()
    workspace = workspace.resolve()
    authorization_receipt = authorization_receipt.resolve()
    consumption_marker = consumption_marker.resolve()
    policy = policies["start_consumption_validation"]
    if not consumption_marker.is_file():
        raise ValueError("Session-start consumption marker must exist")
    if policy["require_external_consumption_marker"] and build_stage_context.is_within(
        consumption_marker,
        repo_root,
    ):
        raise ValueError("Session-start consumption marker must be outside the checkout")
    if policy["require_marker_outside_workspace"] and build_stage_context.is_within(
        consumption_marker,
        workspace,
    ):
        raise ValueError("Session-start consumption marker must be outside the workspace")

    marker_bytes = consumption_marker.read_bytes()
    if len(marker_bytes) > policy["max_marker_bytes"]:
        result["failures"].append(
            failure("max_marker_bytes", "Consumption marker exceeds byte limit.")
        )
        return result
    if authorize_implementation_session_start.sha256_bytes(
        marker_bytes
    ) != consumption_marker_sha256:
        result["failures"].append(
            failure("marker_sha256", "Consumption marker SHA-256 does not match.")
        )
        return result

    authorization_bytes = authorization_receipt.read_bytes()
    authorization_validation = (
        validate_implementation_session_start_authorization.validate(
            repo_root,
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
    if (
        policy["require_valid_authorization_receipt"]
        and authorization_validation.get("valid") is not True
    ):
        result["failures"].append(
            failure(
                "authorization_receipt_validation",
                "Marker validation requires a valid authorization receipt.",
                validation=authorization_validation,
            )
        )
        return result

    value = json.loads(marker_bytes.decode("utf-8-sig"))
    if (
        policy["require_canonical_marker"]
        and marker_bytes
        != consume_implementation_session_start_authorization.canonical_marker_bytes(
            value
        )
    ):
        result["failures"].append(
            failure("canonical_marker", "Consumption marker is not canonical JSON.")
        )
        return result
    result["failures"].extend(
        validate_marker_value(
            value,
            consumption_marker,
            authorization_receipt,
            authorization_receipt_sha256,
            authorization_validation,
            policy,
        )
    )
    if isinstance(value, dict):
        result.update(
            session_start_authorized=value.get("session_start_authorized") is True,
            session_start_authorization_consumed=(
                value.get("session_start_authorization_consumed") is True
            ),
            authorizer_authenticated=value.get("authorizer_authenticated") is True,
            local_exclusive_marker_created=(
                value.get("local_exclusive_marker_created") is True
            ),
            ordinary_local_replay_rejected=(
                value.get("ordinary_local_replay_rejected") is True
            ),
            cross_host_replay_prevention_enforced=(
                value.get("cross_host_replay_prevention_enforced") is True
            ),
            tamper_resistant=value.get("tamper_resistant") is True,
            issue=value.get("issue"),
            risk=value.get("risk"),
            base_commit=value.get("base_commit"),
            workspace=value.get("workspace"),
            candidate_runner=value.get("candidate_runner"),
        )
    if result["failures"]:
        return result

    validator_bindings = initialize_portable_run.binding_records(
        policy["validator_bindings"]
    )
    refreshed_validation = validate_implementation_session_start_authorization.validate(
        repo_root,
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
    refreshed_bindings = initialize_portable_run.binding_records(
        policy["validator_bindings"]
    )
    if (
        authorization_receipt.read_bytes() != authorization_bytes
        or consumption_marker.read_bytes() != marker_bytes
        or not validate_implementation_session_start_authorization.exact_equal(
            refreshed_validation,
            authorization_validation,
        )
        or not validate_implementation_session_start_authorization.exact_equal(
            refreshed_bindings,
            validator_bindings,
        )
    ):
        result["failures"].append(
            failure(
                "state_changed",
                "Authorization, marker, current validation, or validator changed.",
            )
        )
        return result
    result.update(valid=True, validator_bindings=validator_bindings)
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
    status = "VALID" if result["valid"] else "INVALID"
    lines = [
        f"implementation-session-start-consumption-validation: {status}",
        f"session_start_authorization_consumed="
        f"{str(result['session_start_authorization_consumed']).lower()}",
        "agent_invocation_authorized=false",
        "cross_host_replay_prevention_enforced=false",
    ]
    lines.extend(f"- {item['rule']}: {item['message']}" for item in result["failures"])
    return "\n".join(lines)


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = validate(
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
        print(
            f"implementation-session-start-consumption-validation: ERROR\n- {error}",
            file=sys.stderr,
        )
        return 1
    if args.format == "json":
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(format_text(result))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
