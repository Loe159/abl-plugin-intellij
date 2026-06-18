#!/usr/bin/env python3
"""Validate one exact implementation session-start authorization receipt."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable

import authorize_implementation_session_start
import build_stage_context
import check_implementation_session_start
import diff_policy
import initialize_portable_run


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = (
    REPO_ROOT
    / ".agent"
    / "policies"
    / "implementation-session-start-authorization-validation.json"
)

EXPECTED_POLICY: dict[str, Any] = {
    "version": 1,
    "purpose": "implementation_session_start_authorization_validation",
    "mode": "validation-only",
    "require_external_authorization_receipt": True,
    "require_authorization_receipt_outside_workspace": True,
    "require_session_start_ready": True,
    "require_clean_worktree": True,
    "require_repo_head_match": True,
    "validator_bindings": [
        ".agent/checks/validate_implementation_session_start_authorization.py",
        ".agent/policies/implementation-session-start-authorization-validation.json",
    ],
}


def load_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    policy = json.loads(path.read_text(encoding="utf-8"))
    if policy != EXPECTED_POLICY:
        raise ValueError("Session-start authorization validation policy does not match")
    return policy


def load_policies() -> dict[str, Any]:
    return {
        **authorize_implementation_session_start.load_policies(),
        "start_authorization_validation": load_policy(),
    }


def failure(rule: str, message: str, **details: Any) -> dict[str, Any]:
    return {"rule": rule, "message": message, **details}


def exact_equal(actual: Any, expected: Any) -> bool:
    if type(actual) is not type(expected):
        return False
    if isinstance(expected, dict):
        return set(actual) == set(expected) and all(
            exact_equal(actual[key], value) for key, value in expected.items()
        )
    if isinstance(expected, list):
        return len(actual) == len(expected) and all(
            exact_equal(left, right)
            for left, right in zip(actual, expected, strict=True)
        )
    return actual == expected


def base_result(expected_sha256: str) -> dict[str, Any]:
    return {
        "valid": False,
        "session_start_authorized": False,
        **{
            field: False
            for field in authorize_implementation_session_start.FALSE_FIELDS
        },
        "authorizer_authenticated": False,
        "authorizer_declaration": None,
        "replay_prevention_enforced": False,
        "issue": None,
        "risk": None,
        "base_commit": None,
        "workspace": None,
        "candidate_runner": None,
        "preflight_sha256": None,
        "authorization_receipt_sha256": expected_sha256,
        "failures": [],
    }


def expected_confirmation(
    policy: dict[str, Any],
    receipt_path: Path,
    start: dict[str, Any],
    workspace: Path,
    proposal_sha256: str,
    worktree_receipt_sha256: str,
    approval_receipt_sha256: str,
    preflight_sha256: str,
    authorization_bindings_sha256: str,
) -> str:
    return (
        f"{policy['confirmation_prefix']} "
        f"issue={start['issue']} risk={start['risk']} "
        f"base_commit={start['base_commit']} workspace={workspace} "
        f"proposal_sha256={proposal_sha256} "
        f"worktree_receipt_sha256={worktree_receipt_sha256} "
        f"approval_receipt_sha256={approval_receipt_sha256} "
        f"preflight_sha256={preflight_sha256} "
        f"candidate_runner_sha256="
        f"{authorize_implementation_session_start.canonical_sha256(start['candidate_runner'])} "
        f"session_start_readiness_sha256="
        f"{authorize_implementation_session_start.canonical_sha256(start)} "
        f"authorization_bindings_sha256={authorization_bindings_sha256} "
        f"authorization_receipt={receipt_path}"
    )


def validate_receipt_value(
    value: Any,
    receipt_path: Path,
    start: dict[str, Any],
    workspace: Path,
    proposal_sha256: str,
    worktree_receipt_sha256: str,
    approval_receipt_sha256: str,
    preflight_sha256: str,
    policies: dict[str, Any],
) -> list[dict[str, Any]]:
    false_fields = authorize_implementation_session_start.FALSE_FIELDS
    expected_fields = {
        "start_authorization_receipt_version",
        "purpose",
        "mode",
        *false_fields,
        "session_start_authorized",
        "authorizer_authenticated",
        "authorizer_declaration",
        "replay_prevention_enforced",
        "issue",
        "risk",
        "base_commit",
        "workspace",
        "candidate_runner",
        "proposal_sha256",
        "worktree_receipt_sha256",
        "approval_receipt_sha256",
        "preflight_sha256",
        "session_start_readiness_sha256",
        "confirmation_sha256",
        "bindings",
    }
    if not isinstance(value, dict) or set(value) != expected_fields:
        return [failure("receipt_schema", "Start-authorization receipt fields do not match.")]
    policy = policies["start_authorization"]
    failures: list[dict[str, Any]] = []
    if (
        type(value["start_authorization_receipt_version"]) is not int
        or value["start_authorization_receipt_version"] != policy["version"]
        or value["purpose"] != policy["purpose"]
        or value["mode"] != policy["mode"]
        or any(value[field] is not False for field in false_fields)
        or value["session_start_authorized"] is not True
        or value["authorizer_authenticated"] is not False
        or value["replay_prevention_enforced"] is not False
    ):
        failures.append(
            failure("receipt_metadata", "Start-authorization safety metadata does not match.")
        )
    authorizer = value["authorizer_declaration"]
    if (
        type(authorizer) is not str
        or not authorizer.strip()
        or len(authorizer) > policy["max_authorizer_chars"]
        or value["issue"] != start["issue"]
        or value["risk"] != start["risk"]
        or value["base_commit"] != start["base_commit"]
        or value["workspace"] != str(workspace)
        or not exact_equal(value["candidate_runner"], start["candidate_runner"])
        or value["proposal_sha256"] != proposal_sha256
        or value["worktree_receipt_sha256"] != worktree_receipt_sha256
        or value["approval_receipt_sha256"] != approval_receipt_sha256
        or value["preflight_sha256"] != preflight_sha256
    ):
        failures.append(
            failure("receipt_identity", "Start-authorization identity does not match inputs.")
        )
    bindings, bindings_sha256 = authorize_implementation_session_start.binding_records(policy)
    confirmation = expected_confirmation(
        policy,
        receipt_path,
        start,
        workspace,
        proposal_sha256,
        worktree_receipt_sha256,
        approval_receipt_sha256,
        preflight_sha256,
        bindings_sha256,
    )
    expected_digests = {
        "session_start_readiness_sha256": (
            authorize_implementation_session_start.canonical_sha256(start)
        ),
        "confirmation_sha256": authorize_implementation_session_start.sha256_bytes(
            confirmation.encode("utf-8")
        ),
    }
    for field, expected in expected_digests.items():
        if value[field] != expected:
            failures.append(failure(field, f"Receipt {field} does not match current state."))
    if not exact_equal(value["bindings"], bindings):
        failures.append(
            failure("trusted_binding_mismatch", "Receipt bindings differ from trusted bytes.")
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
    policies: dict[str, Any],
    readiness_runner: Callable[[Path, dict[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    result = base_result(authorization_receipt_sha256)
    if not authorize_implementation_session_start.approve_implementation_session.SHA256.fullmatch(
        authorization_receipt_sha256
    ):
        raise ValueError(
            "Expected authorization receipt SHA-256 must be 64 lowercase hexadecimal characters"
        )
    paths = (
        repo,
        proposal,
        workspace,
        worktree_receipt,
        approval_receipt,
        preflight,
        authorization_receipt,
    )
    if any(path.is_symlink() for path in paths):
        raise ValueError("Session-start authorization input symlinks are not allowed")
    repo_root = Path(
        diff_policy.run_git(repo, "rev-parse", "--show-toplevel").decode("utf-8").strip()
    ).resolve()
    workspace = workspace.resolve()
    receipt_path = authorization_receipt.resolve()
    policy = policies["start_authorization_validation"]
    if not receipt_path.is_file():
        raise ValueError("Session-start authorization receipt must exist")
    if policy["require_external_authorization_receipt"] and build_stage_context.is_within(
        receipt_path, repo_root
    ):
        raise ValueError("Session-start authorization receipt must be outside the checkout")
    if policy["require_authorization_receipt_outside_workspace"] and build_stage_context.is_within(
        receipt_path, workspace
    ):
        raise ValueError("Session-start authorization receipt must be outside the workspace")
    receipt_bytes = receipt_path.read_bytes()
    if len(receipt_bytes) > policies["start_authorization"]["max_authorization_receipt_bytes"]:
        result["failures"].append(
            failure("max_receipt_bytes", "Start-authorization receipt exceeds byte limit.")
        )
        return result
    if authorize_implementation_session_start.sha256_bytes(
        receipt_bytes
    ) != authorization_receipt_sha256:
        result["failures"].append(
            failure("receipt_sha256", "Receipt does not match its expected SHA-256.")
        )
        return result

    start = check_implementation_session_start.check_start(
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
        policies,
        readiness_runner,
    )
    if policy["require_session_start_ready"] and start["session_start_ready"] is not True:
        result["failures"].append(
            failure(
                "session_start_readiness",
                "Authorization validation requires current session-start readiness.",
                readiness=start,
            )
        )
    value = json.loads(receipt_bytes.decode("utf-8-sig"))
    result.update(
        issue=start.get("issue"),
        risk=start.get("risk"),
        base_commit=start.get("base_commit"),
        workspace=str(workspace),
        candidate_runner=start.get("candidate_runner"),
        preflight_sha256=preflight_sha256,
    )
    if start["session_start_ready"]:
        result["failures"].extend(
            validate_receipt_value(
                value,
                receipt_path,
                start,
                workspace,
                proposal_sha256,
                worktree_receipt_sha256,
                approval_receipt_sha256,
                preflight_sha256,
                policies,
            )
        )
    if isinstance(value, dict):
        result.update(
            session_start_authorized=value.get("session_start_authorized") is True,
            authorizer_authenticated=value.get("authorizer_authenticated") is True,
            authorizer_declaration=value.get("authorizer_declaration"),
            replay_prevention_enforced=value.get("replay_prevention_enforced") is True,
        )

    head = diff_policy.run_git(repo_root, "rev-parse", "HEAD").decode("ascii").strip()
    status = diff_policy.run_git_with_environment(
        repo_root,
        {"GIT_OPTIONAL_LOCKS": "0"},
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
    )
    if (
        policy["require_repo_head_match"]
        and result["base_commit"] is not None
        and head != result["base_commit"]
    ):
        result["failures"].append(
            failure("repo_head_match", "Repository HEAD differs from the authorized base.")
        )
    if policy["require_clean_worktree"] and status:
        result["failures"].append(
            failure("clean_worktree", "Repository worktree must be clean.")
        )
    secrets = build_stage_context.detect_secrets(
        [
            build_stage_context.content_record(
                "authorizer", str(result["authorizer_declaration"] or "")
            )
        ],
        policies["diff"],
    )
    if secrets:
        result["authorizer_declaration"] = None
        result["failures"].append(
            failure(
                "high_confidence_secret",
                "Authorizer declaration contains a secret signature.",
            )
        )
    if result["failures"]:
        return result

    validator_bindings = initialize_portable_run.binding_records(
        policy["validator_bindings"]
    )
    refreshed_bindings = initialize_portable_run.binding_records(
        policy["validator_bindings"]
    )
    if (
        receipt_path.read_bytes() != receipt_bytes
        or not exact_equal(refreshed_bindings, validator_bindings)
        or diff_policy.run_git(repo_root, "rev-parse", "HEAD").decode("ascii").strip()
        != head
        or diff_policy.run_git_with_environment(
            repo_root,
            {"GIT_OPTIONAL_LOCKS": "0"},
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
        )
        != status
    ):
        result["failures"].append(
            failure("state_changed", "Receipt, repository, or validator changed.")
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
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def format_text(result: dict[str, Any]) -> str:
    status = "VALID" if result["valid"] else "INVALID"
    lines = [
        f"implementation-session-start-authorization-validation: {status} "
        f"issue={result['issue'] or 'unknown'}",
        f"session_start_authorized={str(result['session_start_authorized']).lower()}",
        "agent_invocation_authorized=false",
        "replay_prevention_enforced=false",
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
            load_policies(),
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        print(
            f"implementation-session-start-authorization-validation: ERROR\n- {error}",
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
