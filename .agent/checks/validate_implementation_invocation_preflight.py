#!/usr/bin/env python3
"""Validate one implementation invocation preflight without starting it."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable

import approve_implementation_session
import build_implementation_invocation_preflight
import build_stage_context
import diff_policy
import initialize_portable_run
import validate_implementation_session_approval


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = (
    REPO_ROOT / ".agent" / "policies" / "implementation-invocation-preflight-validation.json"
)
FALSE_AUTHORIZATION_FIELDS = approve_implementation_session.FALSE_AUTHORIZATION_FIELDS

EXPECTED_POLICY: dict[str, Any] = {
    "version": 1,
    "purpose": "implementation_invocation_preflight_validation",
    "mode": "validation-only",
    "require_external_preflight": True,
    "require_preflight_outside_workspace": True,
    "require_valid_approval_validation": True,
    "require_clean_worktree": True,
    "require_repo_head_match": True,
    "validator_bindings": [
        ".agent/checks/validate_implementation_invocation_preflight.py",
        ".agent/policies/implementation-invocation-preflight-validation.json",
    ],
}


def load_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    policy = json.loads(path.read_text(encoding="utf-8"))
    if policy != EXPECTED_POLICY:
        raise ValueError("Implementation invocation preflight validation policy does not match")
    return policy


def load_policies() -> dict[str, Any]:
    return {
        **build_implementation_invocation_preflight.load_policies(),
        "preflight_validation": load_policy(),
    }


def failure(rule: str, message: str, **details: Any) -> dict[str, Any]:
    return {"rule": rule, "message": message, **details}


def sha256_bytes(content: bytes) -> str:
    return approve_implementation_session.sha256_bytes(content)


def exact_equal(actual: Any, expected: Any) -> bool:
    return validate_implementation_session_approval.exact_equal(actual, expected)


def base_result(expected_sha256: str) -> dict[str, Any]:
    return {
        "valid": False,
        "preflight_passed": False,
        **{field: False for field in FALSE_AUTHORIZATION_FIELDS},
        "preflight_sha256": expected_sha256,
        "issue": None,
        "risk": None,
        "base_commit": None,
        "proposal_sha256": None,
        "worktree_receipt_sha256": None,
        "approval_receipt_sha256": None,
        "runner_controls_ready": False,
        "runner_readiness_sha256": None,
        "policy_bindings_sha256": None,
        "failures": [],
    }


def canonical_sha256(value: Any) -> str:
    return sha256_bytes((json.dumps(value, sort_keys=True) + "\n").encode("utf-8"))


def binding_records(policy: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
    records = initialize_portable_run.binding_records(policy["policy_bindings"])
    digest = canonical_sha256(records)
    return records, digest


def validate_preflight_location(
    repo_root: Path,
    workspace: Path,
    preflight: Path,
    policy: dict[str, Any],
) -> Path:
    preflight = preflight.resolve()
    if "\n" in str(preflight) or "\r" in str(preflight):
        raise ValueError("Implementation invocation preflight path must not contain line breaks")
    if preflight.is_symlink():
        raise ValueError("Implementation invocation preflight symbolic links are not allowed")
    if not preflight.is_file():
        raise ValueError("Implementation invocation preflight must exist")
    if policy["require_external_preflight"] and build_stage_context.is_within(preflight, repo_root):
        raise ValueError("Implementation invocation preflight must be outside the Git checkout")
    if policy["require_preflight_outside_workspace"] and build_stage_context.is_within(
        preflight,
        workspace.resolve(),
    ):
        raise ValueError("Implementation invocation preflight must be outside the workspace")
    return preflight


def load_json_object(path: Path, expected_sha256: str) -> tuple[dict[str, Any], bytes]:
    content = path.read_bytes()
    if sha256_bytes(content) != expected_sha256:
        raise ValueError(f"{path.name} does not match its expected SHA-256")
    value = json.loads(content.decode("utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return value, content


def validate_preflight_value(
    value: Any,
    proposal_value: dict[str, Any],
    proposal_bytes: bytes,
    worktree_receipt_bytes: bytes,
    approval_receipt_bytes: bytes,
    approval_validation: dict[str, Any],
    policy_bindings: list[dict[str, Any]],
    policy_bindings_sha256: str,
    proposal_sha256: str,
    worktree_receipt_sha256: str,
    approval_receipt_sha256: str,
    policies: dict[str, Any],
) -> list[dict[str, Any]]:
    expected_fields = {
        "preflight_version",
        "purpose",
        "mode",
        "preflight_passed",
        *FALSE_AUTHORIZATION_FIELDS,
        "issue",
        "risk",
        "base_commit",
        "repo_head",
        "workspace",
        "proposal",
        "worktree_receipt",
        "approval_receipt",
        "approval_validation",
        "policy_bindings",
        "policy_bindings_sha256",
        "runner_selection",
        "session_start",
    }
    if not isinstance(value, dict) or set(value) != expected_fields:
        return [failure("preflight_schema", "Preflight fields do not match.")]

    failures: list[dict[str, Any]] = []
    preflight_policy = policies["preflight"]
    if (
        value["preflight_version"] != preflight_policy["version"]
        or value["purpose"] != preflight_policy["purpose"]
        or value["mode"] != preflight_policy["mode"]
        or value["preflight_passed"] is not True
        or any(value[field] is not False for field in FALSE_AUTHORIZATION_FIELDS)
    ):
        failures.append(failure("preflight_metadata", "Preflight safety metadata does not match."))
    if (
        value["issue"] != approval_validation["issue"]
        or value["risk"] != approval_validation["risk"]
        or value["base_commit"] != approval_validation["base_commit"]
        or value["repo_head"] != approval_validation["base_commit"]
    ):
        failures.append(failure("preflight_identity", "Preflight identity does not match validation."))
    expected_proposal = {
        "sha256": proposal_sha256,
        "size_bytes": len(proposal_bytes),
        "content": proposal_value,
    }
    expected_worktree_receipt = {
        "sha256": worktree_receipt_sha256,
        "size_bytes": len(worktree_receipt_bytes),
    }
    expected_approval_receipt = {
        "sha256": approval_receipt_sha256,
        "size_bytes": len(approval_receipt_bytes),
    }
    if not exact_equal(value["proposal"], expected_proposal):
        failures.append(failure("proposal_record", "Preflight proposal record does not match."))
    if not exact_equal(value["worktree_receipt"], expected_worktree_receipt):
        failures.append(failure("worktree_receipt_record", "Preflight worktree receipt record does not match."))
    if not exact_equal(value["approval_receipt"], expected_approval_receipt):
        failures.append(failure("approval_receipt_record", "Preflight approval receipt record does not match."))
    if not exact_equal(value["approval_validation"], approval_validation):
        failures.append(failure("approval_validation_record", "Preflight approval validation is stale."))
    if not exact_equal(value["policy_bindings"], policy_bindings):
        failures.append(failure("policy_bindings", "Preflight policy bindings differ from trusted bytes."))
    if value["policy_bindings_sha256"] != policy_bindings_sha256:
        failures.append(failure("policy_bindings_sha256", "Preflight policy binding digest differs."))
    expected_gate = {"required": True, "completed": False, "authorized": False}
    if not exact_equal(value["runner_selection"], expected_gate):
        failures.append(failure("runner_selection", "Preflight runner-selection gate overclaims."))
    if not exact_equal(value["session_start"], expected_gate):
        failures.append(failure("session_start", "Preflight session-start gate overclaims."))
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
    policies: dict[str, Any],
    readiness_runner: Callable[[Path, dict[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    result = base_result(preflight_sha256)
    if not approve_implementation_session.SHA256.fullmatch(preflight_sha256):
        raise ValueError("Expected preflight SHA-256 must be 64 lowercase hexadecimal characters")
    if (
        repo.is_symlink()
        or proposal.is_symlink()
        or workspace.is_symlink()
        or worktree_receipt.is_symlink()
        or approval_receipt.is_symlink()
    ):
        raise ValueError("Repository, proposal, workspace, and receipt symlinks are not allowed")
    repo_root = Path(
        diff_policy.run_git(repo, "rev-parse", "--show-toplevel").decode("utf-8").strip()
    ).resolve()
    preflight = validate_preflight_location(
        repo_root,
        workspace,
        preflight,
        policies["preflight_validation"],
    )
    preflight_bytes = preflight.read_bytes()
    if len(preflight_bytes) > policies["preflight"]["max_preflight_bytes"]:
        result["failures"].append(failure("max_preflight_bytes", "Preflight exceeds byte limit."))
        return result
    if sha256_bytes(preflight_bytes) != preflight_sha256:
        result["failures"].append(failure("preflight_sha256", "Preflight does not match expected SHA-256."))
        return result

    approval_validation = validate_implementation_session_approval.validate(
        repo_root,
        proposal,
        proposal_sha256,
        workspace,
        worktree_receipt,
        worktree_receipt_sha256,
        approval_receipt,
        approval_receipt_sha256,
        policies,
        readiness_runner,
    )
    if policies["preflight_validation"]["require_valid_approval_validation"] and not approval_validation["valid"]:
        result["failures"].append(
            failure(
                "approval_validation",
                "Preflight validation requires a valid approval validation.",
                validation=approval_validation,
            )
        )

    try:
        value = json.loads(preflight_bytes.decode("utf-8-sig"))
    except (UnicodeError, json.JSONDecodeError) as error:
        result["failures"].append(failure("preflight_json", str(error)))
        return result
    proposal_value, proposal_bytes = load_json_object(proposal.resolve(), proposal_sha256)
    worktree_receipt_bytes = worktree_receipt.resolve().read_bytes()
    approval_receipt_bytes = approval_receipt.resolve().read_bytes()
    policy_bindings, policy_bindings_sha256 = build_implementation_invocation_preflight.binding_records(
        policies["preflight"],
    )
    result.update(
        issue=approval_validation.get("issue"),
        risk=approval_validation.get("risk"),
        base_commit=approval_validation.get("base_commit"),
        proposal_sha256=proposal_sha256,
        worktree_receipt_sha256=worktree_receipt_sha256,
        approval_receipt_sha256=approval_receipt_sha256,
        runner_controls_ready=approval_validation.get("runner_controls_ready") is True,
        runner_readiness_sha256=approval_validation.get("runner_readiness_sha256"),
        policy_bindings_sha256=policy_bindings_sha256,
    )
    if approval_validation.get("valid"):
        result["failures"].extend(
            validate_preflight_value(
                value,
                proposal_value,
                proposal_bytes,
                worktree_receipt_bytes,
                approval_receipt_bytes,
                approval_validation,
                policy_bindings,
                policy_bindings_sha256,
                proposal_sha256,
                worktree_receipt_sha256,
                approval_receipt_sha256,
                policies,
            )
        )
    else:
        result["failures"].append(
            failure("preflight_unchecked", "Preflight identity was not checked because approval validation failed.")
        )
    if isinstance(value, dict):
        result.update(
            preflight_passed=value.get("preflight_passed") is True,
            **{field: value.get(field) is True for field in FALSE_AUTHORIZATION_FIELDS},
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
        policies["preflight_validation"]["require_repo_head_match"]
        and result["base_commit"] is not None
        and head != result["base_commit"]
    ):
        result["failures"].append(failure("repo_head_match", "Repository HEAD differs from proposal base."))
    if policies["preflight_validation"]["require_clean_worktree"] and status:
        result["failures"].append(failure("clean_worktree", "Repository worktree must be clean."))
    detections = build_stage_context.detect_secrets(
        [build_stage_context.content_record("implementation-invocation-preflight.json", json.dumps(value))],
        policies["diff"],
    )
    if detections:
        result["failures"].append(
            failure(
                "high_confidence_secret",
                "Implementation invocation preflight contains a high-confidence secret signature.",
                detections=detections,
            )
        )
    if result["failures"]:
        return result

    validator_bindings = initialize_portable_run.binding_records(
        policies["preflight_validation"]["validator_bindings"],
    )
    refreshed_bindings = initialize_portable_run.binding_records(
        policies["preflight_validation"]["validator_bindings"],
    )
    refreshed_validation = validate_implementation_session_approval.validate(
        repo_root,
        proposal,
        proposal_sha256,
        workspace,
        worktree_receipt,
        worktree_receipt_sha256,
        approval_receipt,
        approval_receipt_sha256,
        policies,
        readiness_runner,
    )
    refreshed_head = diff_policy.run_git(repo_root, "rev-parse", "HEAD").decode("ascii").strip()
    refreshed_status = diff_policy.run_git_with_environment(
        repo_root,
        {"GIT_OPTIONAL_LOCKS": "0"},
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
    )
    if (
        preflight.read_bytes() != preflight_bytes
        or refreshed_validation != approval_validation
        or refreshed_bindings != validator_bindings
        or refreshed_head != head
        or refreshed_status != status
    ):
        result["failures"].append(
            failure("state_changed", "Preflight, approval validation, repository, or validator changed.")
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
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def format_text(result: dict[str, Any]) -> str:
    status = "VALID" if result["valid"] else "INVALID"
    lines = [
        f"implementation-invocation-preflight-validation: {status} issue={result['issue'] or 'unknown'}",
        "runner_selected=false",
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
            args.preflight,
            args.preflight_sha256,
            load_policies(),
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        print(f"implementation-invocation-preflight-validation: ERROR\n- {error}", file=sys.stderr)
        return 1
    if args.format == "json":
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(format_text(result))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
