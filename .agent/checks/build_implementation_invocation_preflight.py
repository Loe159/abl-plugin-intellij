#!/usr/bin/env python3
"""Build a deterministic non-authorizing implementation invocation preflight."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable

import approve_implementation_session
import build_stage_context
import diff_policy
import initialize_portable_run
import validate_implementation_session_approval


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / ".agent" / "policies" / "implementation-invocation-preflight.json"
FALSE_AUTHORIZATION_FIELDS = approve_implementation_session.FALSE_AUTHORIZATION_FIELDS

EXPECTED_POLICY: dict[str, Any] = {
    "version": 1,
    "purpose": "implementation_invocation_preflight",
    "mode": "preflight-only",
    "max_preflight_bytes": 220000,
    "require_valid_approval_validation": True,
    "require_external_output": True,
    "require_output_outside_workspace": True,
    "require_absent_output": True,
    "require_clean_worktree": True,
    "require_repo_head_match": True,
    "policy_bindings": [
        ".agent/checks/build_implementation_invocation_preflight.py",
        ".agent/policies/implementation-invocation-preflight.json",
        ".agent/checks/validate_implementation_session_approval.py",
        ".agent/policies/implementation-session-approval-validation.json",
        ".agent/checks/validate_implementation_session.py",
        ".agent/policies/implementation-session.json",
        ".agent/checks/assess_runner_readiness.py",
        ".agent/policies/runner-readiness.json",
    ],
}


def load_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    policy = json.loads(path.read_text(encoding="utf-8"))
    if policy != EXPECTED_POLICY:
        raise ValueError("Implementation invocation preflight policy does not match")
    return policy


def load_policies() -> dict[str, Any]:
    return {
        **validate_implementation_session_approval.load_policies(),
        "preflight": load_policy(),
    }


def failure(rule: str, message: str, **details: Any) -> dict[str, Any]:
    return {"rule": rule, "message": message, **details}


def sha256_bytes(content: bytes) -> str:
    return approve_implementation_session.sha256_bytes(content)


def binding_records(policy: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
    records = initialize_portable_run.binding_records(policy["policy_bindings"])
    digest = sha256_bytes((json.dumps(records, sort_keys=True) + "\n").encode("utf-8"))
    return records, digest


def validate_output_target(
    repo_root: Path,
    workspace: Path,
    output: Path,
    policy: dict[str, Any],
) -> Path:
    output = output.resolve()
    if "\n" in str(output) or "\r" in str(output):
        raise ValueError("Implementation invocation preflight output path must not contain line breaks")
    if output.is_symlink():
        raise ValueError("Implementation invocation preflight output symbolic links are not allowed")
    if policy["require_external_output"] and build_stage_context.is_within(output, repo_root):
        raise ValueError("Implementation invocation preflight output must be outside the Git checkout")
    if policy["require_output_outside_workspace"] and build_stage_context.is_within(
        output,
        workspace.resolve(),
    ):
        raise ValueError("Implementation invocation preflight output must be outside the workspace")
    if policy["require_absent_output"] and output.exists():
        raise ValueError("Implementation invocation preflight output already exists")
    if not output.parent.is_dir():
        raise ValueError("Implementation invocation preflight output parent must exist")
    return output


def base_result() -> dict[str, Any]:
    return {
        "produced": False,
        "preflight_passed": False,
        **{field: False for field in FALSE_AUTHORIZATION_FIELDS},
        "issue": None,
        "risk": None,
        "base_commit": None,
        "proposal_sha256": None,
        "worktree_receipt_sha256": None,
        "approval_receipt_sha256": None,
        "output": None,
        "sha256": None,
        "size_bytes": None,
        "policy_bindings_sha256": None,
        "failures": [],
    }


def read_json_file(path: Path, expected_sha256: str) -> tuple[dict[str, Any], bytes]:
    content = path.read_bytes()
    if sha256_bytes(content) != expected_sha256:
        raise ValueError(f"{path.name} does not match its expected SHA-256")
    value = json.loads(content.decode("utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return value, content


def validate_identity(
    proposal: dict[str, Any],
    validation: dict[str, Any],
    proposal_sha256: str,
    worktree_receipt_sha256: str,
) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    if (
        proposal.get("issue") != validation["issue"]
        or proposal.get("risk") != validation["risk"]
        or proposal.get("base_commit") != validation["base_commit"]
        or validation["proposal_sha256"] != proposal_sha256
        or validation["worktree_receipt_sha256"] != worktree_receipt_sha256
    ):
        failures.append(
            failure("identity_mismatch", "Preflight inputs do not match approval validation.")
        )
    prepared = proposal.get("prepared_workspace")
    if not isinstance(prepared, dict) or prepared.get("receipt_sha256") != worktree_receipt_sha256:
        failures.append(
            failure("prepared_workspace", "Proposal prepared workspace does not match receipt.")
        )
    return failures


def build_preflight(
    repo: Path,
    proposal: Path,
    proposal_sha256: str,
    workspace: Path,
    worktree_receipt: Path,
    worktree_receipt_sha256: str,
    approval_receipt: Path,
    approval_receipt_sha256: str,
    output: Path,
    policies: dict[str, Any],
    readiness_runner: Callable[[Path, dict[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    result = base_result()
    repo_root = Path(
        diff_policy.run_git(repo, "rev-parse", "--show-toplevel").decode("utf-8").strip()
    ).resolve()
    if (
        repo.is_symlink()
        or proposal.is_symlink()
        or workspace.is_symlink()
        or worktree_receipt.is_symlink()
        or approval_receipt.is_symlink()
    ):
        raise ValueError("Repository, proposal, workspace, receipt symlinks are not allowed")
    output = validate_output_target(repo_root, workspace, output, policies["preflight"])
    result.update(
        proposal_sha256=proposal_sha256,
        worktree_receipt_sha256=worktree_receipt_sha256,
        approval_receipt_sha256=approval_receipt_sha256,
        output=str(output),
    )

    validation = validate_implementation_session_approval.validate(
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
    if policies["preflight"]["require_valid_approval_validation"] and not validation["valid"]:
        result["failures"].append(
            failure(
                "approval_validation",
                "Implementation invocation preflight requires a valid approval validation.",
                validation=validation,
            )
        )
        return result

    proposal_value, proposal_bytes = read_json_file(proposal.resolve(), proposal_sha256)
    approval_receipt_bytes = approval_receipt.resolve().read_bytes()
    worktree_receipt_bytes = worktree_receipt.resolve().read_bytes()
    result.update(
        issue=validation["issue"],
        risk=validation["risk"],
        base_commit=validation["base_commit"],
    )
    result["failures"].extend(
        validate_identity(proposal_value, validation, proposal_sha256, worktree_receipt_sha256)
    )
    head = diff_policy.run_git(repo_root, "rev-parse", "HEAD").decode("ascii").strip()
    status = diff_policy.run_git_with_environment(
        repo_root,
        {"GIT_OPTIONAL_LOCKS": "0"},
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
    )
    if policies["preflight"]["require_repo_head_match"] and head != validation["base_commit"]:
        result["failures"].append(failure("repo_head_match", "Repository HEAD differs from proposal base."))
    if policies["preflight"]["require_clean_worktree"] and status:
        result["failures"].append(failure("clean_worktree", "Repository worktree must be clean."))
    policy_bindings, policy_bindings_sha256 = binding_records(policies["preflight"])
    result["policy_bindings_sha256"] = policy_bindings_sha256
    detections = build_stage_context.detect_secrets(
        [
            build_stage_context.content_record("implementation-session-proposal.json", json.dumps(proposal_value)),
            build_stage_context.content_record(
                "implementation-session-approval-validation.json",
                json.dumps(validation),
            ),
        ],
        policies["diff"],
    )
    if detections:
        result["failures"].append(
            failure(
                "high_confidence_secret",
                "Implementation invocation preflight source contains a high-confidence secret signature.",
                detections=detections,
            )
        )
    if result["failures"]:
        return result

    preflight = {
        "preflight_version": policies["preflight"]["version"],
        "purpose": policies["preflight"]["purpose"],
        "mode": policies["preflight"]["mode"],
        "preflight_passed": True,
        **{field: False for field in FALSE_AUTHORIZATION_FIELDS},
        "issue": validation["issue"],
        "risk": validation["risk"],
        "base_commit": validation["base_commit"],
        "repo_head": head,
        "workspace": str(workspace.resolve()),
        "proposal": {
            "sha256": proposal_sha256,
            "size_bytes": len(proposal_bytes),
            "content": proposal_value,
        },
        "worktree_receipt": {
            "sha256": worktree_receipt_sha256,
            "size_bytes": len(worktree_receipt_bytes),
        },
        "approval_receipt": {
            "sha256": approval_receipt_sha256,
            "size_bytes": len(approval_receipt_bytes),
        },
        "approval_validation": validation,
        "policy_bindings": policy_bindings,
        "policy_bindings_sha256": policy_bindings_sha256,
        "runner_selection": {
            "required": True,
            "completed": False,
            "authorized": False,
        },
        "session_start": {
            "required": True,
            "completed": False,
            "authorized": False,
        },
    }
    preflight_bytes = (json.dumps(preflight, indent=2, sort_keys=True) + "\n").encode("utf-8")
    if len(preflight_bytes) > policies["preflight"]["max_preflight_bytes"]:
        result["failures"].append(
            failure(
                "max_preflight_bytes",
                "Implementation invocation preflight exceeds the configured byte limit.",
                actual=len(preflight_bytes),
                limit=policies["preflight"]["max_preflight_bytes"],
            )
        )
        return result

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
    refreshed_policy_bindings, _refreshed_bindings_sha256 = binding_records(policies["preflight"])
    refreshed_head = diff_policy.run_git(repo_root, "rev-parse", "HEAD").decode("ascii").strip()
    refreshed_status = diff_policy.run_git_with_environment(
        repo_root,
        {"GIT_OPTIONAL_LOCKS": "0"},
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
    )
    if (
        refreshed_validation != validation
        or refreshed_policy_bindings != policy_bindings
        or refreshed_head != head
        or refreshed_status != status
        or output.exists()
    ):
        result["failures"].append(
            failure("state_changed", "Approval validation, repository, policy, or output changed.")
        )
        return result

    build_stage_context.write_atomic(output, preflight_bytes)
    result.update(
        produced=True,
        preflight_passed=True,
        sha256=sha256_bytes(preflight_bytes),
        size_bytes=len(preflight_bytes),
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
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def format_text(result: dict[str, Any]) -> str:
    status = "PRODUCED" if result["produced"] else "BLOCKED"
    lines = [
        f"implementation-invocation-preflight: {status} issue={result['issue'] or 'unknown'}",
        "runner_selected=false",
        "session_start_authorized=false",
        "agent_invocation_authorized=false",
    ]
    lines.extend(f"- {item['rule']}: {item['message']}" for item in result["failures"])
    return "\n".join(lines)


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = build_preflight(
            args.repo,
            args.proposal,
            args.proposal_sha256,
            args.workspace,
            args.worktree_receipt,
            args.worktree_receipt_sha256,
            args.approval_receipt,
            args.approval_receipt_sha256,
            args.output,
            load_policies(),
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        print(f"implementation-invocation-preflight: ERROR\n- {error}", file=sys.stderr)
        return 1
    if args.format == "json":
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(format_text(result))
    return 0 if result["produced"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
