#!/usr/bin/env python3
"""Validate one exact implementation-session approval receipt without starting it."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable

import approve_implementation_session
import assess_runner_readiness
import build_stage_context
import diff_policy
import initialize_portable_run
import validate_implementation_session


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / ".agent" / "policies" / "implementation-session-approval-validation.json"
FALSE_AUTHORIZATION_FIELDS = approve_implementation_session.FALSE_AUTHORIZATION_FIELDS

EXPECTED_POLICY: dict[str, Any] = {
    "version": 1,
    "purpose": "implementation_session_proposal_approval_validation",
    "mode": "validation-only",
    "require_external_approval_receipt": True,
    "require_approval_receipt_outside_workspace": True,
    "require_valid_proposal": True,
    "require_runner_controls_ready": True,
    "require_clean_worktree": True,
    "require_repo_head_match": True,
    "validator_bindings": [
        ".agent/checks/validate_implementation_session_approval.py",
        ".agent/policies/implementation-session-approval-validation.json",
    ],
}


def load_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    policy = json.loads(path.read_text(encoding="utf-8"))
    if policy != EXPECTED_POLICY:
        raise ValueError("Implementation-session approval validation policy does not match")
    return policy


def load_policies() -> dict[str, Any]:
    return {
        **approve_implementation_session.load_policies(),
        "approval_validation": load_policy(),
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
            exact_equal(actual_item, expected_item)
            for actual_item, expected_item in zip(actual, expected, strict=True)
        )
    return actual == expected


def base_result(expected_sha256: str) -> dict[str, Any]:
    return {
        "valid": False,
        "session_proposal_approved": False,
        **{field: False for field in FALSE_AUTHORIZATION_FIELDS},
        "approval_receipt_sha256": expected_sha256,
        "approver_declaration": None,
        "issue": None,
        "risk": None,
        "base_commit": None,
        "proposal_sha256": None,
        "worktree_receipt_sha256": None,
        "runner_controls_ready": False,
        "runner_readiness_sha256": None,
        "failures": [],
    }


def validate_receipt_value(
    value: Any,
    approval_receipt: Path,
    proposal_sha256: str,
    worktree_receipt_sha256: str,
    proposal_validation: dict[str, Any],
    readiness: dict[str, Any],
    policies: dict[str, Any],
) -> list[dict[str, Any]]:
    expected_fields = {
        "session_approval_receipt_version",
        "purpose",
        "mode",
        *FALSE_AUTHORIZATION_FIELDS,
        "session_proposal_approved",
        "runner_controls_ready",
        "approver_declaration",
        "issue",
        "risk",
        "base_commit",
        "proposal_sha256",
        "worktree_receipt_sha256",
        "runner_readiness_sha256",
        "confirmation_sha256",
        "bindings",
    }
    if not isinstance(value, dict) or set(value) != expected_fields:
        return [failure("receipt_schema", "Session-approval receipt fields do not match.")]
    failures: list[dict[str, Any]] = []
    approval = policies["approval"]
    if (
        type(value["session_approval_receipt_version"]) is not int
        or value["session_approval_receipt_version"] != approval["version"]
        or value["purpose"] != approval["purpose"]
        or value["mode"] != approval["mode"]
        or any(value[field] is not False for field in FALSE_AUTHORIZATION_FIELDS)
        or value["session_proposal_approved"] is not True
        or value["runner_controls_ready"] is not True
    ):
        failures.append(failure("receipt_metadata", "Receipt safety metadata does not match."))
    approver = value["approver_declaration"]
    if (
        type(approver) is not str
        or not approver.strip()
        or len(approver) > approval["max_approver_chars"]
        or value["issue"] != proposal_validation["issue"]
        or value["risk"] != proposal_validation["risk"]
        or value["base_commit"] != proposal_validation["base_commit"]
        or value["proposal_sha256"] != proposal_sha256
        or value["worktree_receipt_sha256"] != worktree_receipt_sha256
    ):
        failures.append(failure("receipt_identity", "Receipt identity does not match inputs."))
    runner_readiness_sha256 = approve_implementation_session.canonical_sha256(readiness)
    bindings, bindings_sha256 = approve_implementation_session.binding_records(approval)
    confirmation = (
        f"{approval['confirmation_prefix']} "
        f"issue={proposal_validation['issue']} risk={proposal_validation['risk']} "
        f"base_commit={proposal_validation['base_commit']} "
        f"proposal_sha256={proposal_sha256} "
        f"worktree_receipt_sha256={worktree_receipt_sha256} "
        f"runner_readiness_sha256={runner_readiness_sha256} "
        f"approval_bindings_sha256={bindings_sha256} "
        f"approval_receipt={approval_receipt}"
    )
    expected_digests = {
        "runner_readiness_sha256": runner_readiness_sha256,
        "confirmation_sha256": approve_implementation_session.sha256_bytes(
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
    policies: dict[str, Any],
    readiness_runner: Callable[[Path, dict[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    result = base_result(approval_receipt_sha256)
    if not approve_implementation_session.SHA256.fullmatch(approval_receipt_sha256):
        raise ValueError("Expected approval receipt SHA-256 must be 64 lowercase hexadecimal characters")
    if repo.is_symlink() or proposal.is_symlink() or workspace.is_symlink() or approval_receipt.is_symlink():
        raise ValueError("Repository, proposal, workspace, and approval receipt symlinks are not allowed")
    repo_root = Path(
        diff_policy.run_git(repo, "rev-parse", "--show-toplevel").decode("utf-8").strip()
    ).resolve()
    approval_receipt = approval_receipt.resolve()
    workspace = workspace.resolve()
    policy = policies["approval_validation"]
    if "\n" in str(approval_receipt) or "\r" in str(approval_receipt):
        raise ValueError("Approval receipt path must not contain line breaks")
    if not approval_receipt.is_file():
        raise ValueError("Implementation-session approval receipt must exist")
    if policy["require_external_approval_receipt"] and build_stage_context.is_within(
        approval_receipt,
        repo_root,
    ):
        raise ValueError("Implementation-session approval receipt must be outside the Git checkout")
    if policy["require_approval_receipt_outside_workspace"] and build_stage_context.is_within(
        approval_receipt,
        workspace,
    ):
        raise ValueError("Implementation-session approval receipt must be outside the workspace")
    receipt_bytes = approval_receipt.read_bytes()
    if len(receipt_bytes) > policies["approval"]["max_session_approval_receipt_bytes"]:
        result["failures"].append(failure("max_receipt_bytes", "Approval receipt exceeds byte limit."))
        return result
    if approve_implementation_session.sha256_bytes(receipt_bytes) != approval_receipt_sha256:
        result["failures"].append(
            failure("receipt_sha256", "Receipt does not match its expected SHA-256.")
        )
        return result

    try:
        proposal_validation = validate_implementation_session.validate_proposal(
            repo_root,
            proposal,
            proposal_sha256,
            workspace,
            worktree_receipt,
            worktree_receipt_sha256,
            {
                "diff": policies["diff"],
                "session": policies["session"],
            },
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        proposal_validation = {"valid": False, "failures": [failure("proposal", str(error))]}
    if policy["require_valid_proposal"] and not proposal_validation["valid"]:
        result["failures"].append(
            failure(
                "proposal_validation",
                "Session approval validation requires a valid proposal.",
                validation=proposal_validation,
            )
        )

    runner = readiness_runner or assess_runner_readiness.assess
    readiness = runner(repo_root, policies["runner"])
    result["runner_controls_ready"] = readiness.get("controls_ready") is True
    result["runner_readiness_sha256"] = approve_implementation_session.canonical_sha256(readiness)
    if policy["require_runner_controls_ready"] and not result["runner_controls_ready"]:
        result["failures"].append(
            failure(
                "runner_controls_ready",
                "Session approval validation requires ready runner controls.",
                readiness=readiness,
            )
        )

    value = json.loads(receipt_bytes.decode("utf-8-sig"))
    if proposal_validation.get("valid"):
        result.update(
            issue=proposal_validation["issue"],
            risk=proposal_validation["risk"],
            base_commit=proposal_validation["base_commit"],
            proposal_sha256=proposal_sha256,
            worktree_receipt_sha256=worktree_receipt_sha256,
        )
        result["failures"].extend(
            validate_receipt_value(
                value,
                approval_receipt,
                proposal_sha256,
                worktree_receipt_sha256,
                proposal_validation,
                readiness,
                policies,
            )
        )
    else:
        result["failures"].append(
            failure("receipt_unchecked", "Receipt identity was not checked because proposal is invalid.")
        )
    if isinstance(value, dict):
        result.update(
            session_proposal_approved=value.get("session_proposal_approved") is True,
            approver_declaration=value.get("approver_declaration"),
        )

    head = diff_policy.run_git(repo_root, "rev-parse", "HEAD").decode("ascii").strip()
    status = diff_policy.run_git_with_environment(
        repo_root,
        {"GIT_OPTIONAL_LOCKS": "0"},
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
    )
    if policy["require_repo_head_match"] and result["base_commit"] is not None and head != result["base_commit"]:
        result["failures"].append(failure("repo_head_match", "Repository HEAD differs from proposal base."))
    if policy["require_clean_worktree"] and status:
        result["failures"].append(failure("clean_worktree", "Repository worktree must be clean."))
    secrets = build_stage_context.detect_secrets(
        [build_stage_context.content_record("approver", str(result["approver_declaration"] or ""))],
        policies["diff"],
    )
    if secrets:
        result["approver_declaration"] = None
        result["failures"].append(
            failure("high_confidence_secret", "Approver declaration contains a secret signature.")
        )
    if result["failures"]:
        return result

    validator_bindings = initialize_portable_run.binding_records(policy["validator_bindings"])
    refreshed_bindings = initialize_portable_run.binding_records(policy["validator_bindings"])
    refreshed_receipt = approval_receipt.read_bytes()
    refreshed_head = diff_policy.run_git(repo_root, "rev-parse", "HEAD").decode("ascii").strip()
    refreshed_status = diff_policy.run_git_with_environment(
        repo_root,
        {"GIT_OPTIONAL_LOCKS": "0"},
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
    )
    if (
        refreshed_receipt != receipt_bytes
        or refreshed_head != head
        or refreshed_status != status
        or not exact_equal(refreshed_bindings, validator_bindings)
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
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def format_text(result: dict[str, Any]) -> str:
    status = "VALID" if result["valid"] else "INVALID"
    lines = [
        f"implementation-session-approval-validation: {status} issue={result['issue'] or 'unknown'}",
        "session_start_authorized=false",
        "agent_invocation_authorized=false",
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
            load_policies(),
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        print(f"implementation-session-approval-validation: ERROR\n- {error}", file=sys.stderr)
        return 1
    if args.format == "json":
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(format_text(result))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
