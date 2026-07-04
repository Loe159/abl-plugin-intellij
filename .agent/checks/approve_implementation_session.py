#!/usr/bin/env python3
"""Approve one exact implementation-session proposal without starting it."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Callable

import apply_stage_output
import assess_runner_readiness
import build_stage_context
import diff_policy
import initialize_portable_run
import validate_implementation_session


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_DIR = REPO_ROOT / ".agent" / "policies"
SHA256 = re.compile(r"[0-9a-f]{64}")
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


def load_policy(path: Path = POLICY_DIR / "implementation-session-approval.json") -> dict[str, Any]:
    policy = json.loads(path.read_text(encoding="utf-8"))
    expected = {
        "version": 1,
        "purpose": "implementation_session_proposal_approval",
        "mode": "exact-local-approval-only",
        "confirmation_prefix": "APPROVE-EXACT-IMPLEMENTATION-SESSION",
        "max_approver_chars": 80,
        "max_session_approval_receipt_bytes": 30000,
        "require_valid_proposal": True,
        "require_runner_controls_ready": False,
        "require_external_approval_receipt": True,
        "require_approval_receipt_outside_workspace": True,
        "require_absent_approval_receipt": True,
        "require_clean_worktree": True,
        "require_repo_head_match": True,
        "bindings": [
            ".agent/checks/approve_implementation_session.py",
            ".agent/policies/implementation-session-approval.json",
            ".agent/checks/validate_implementation_session.py",
            ".agent/policies/implementation-session.json",
            ".agent/checks/assess_runner_readiness.py",
            ".agent/policies/runner-readiness.json",
        ],
    }
    if policy != expected:
        raise ValueError("Implementation-session approval policy does not match the pilot contract")
    return policy


def load_policies() -> dict[str, Any]:
    return {
        "diff": validate_implementation_session.build_implementation_session.load_policies()["diff"],
        "session": validate_implementation_session.build_implementation_session.load_policies()[
            "session"
        ],
        "runner": assess_runner_readiness.load_policy(),
        "approval": load_policy(),
    }


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def failure(rule: str, message: str, **details: Any) -> dict[str, Any]:
    return {"rule": rule, "message": message, **details}


def binding_records(policy: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
    records = initialize_portable_run.binding_records(policy["bindings"])
    content = (json.dumps(records, sort_keys=True) + "\n").encode("utf-8")
    return records, sha256_bytes(content)


def canonical_sha256(value: Any) -> str:
    return sha256_bytes((json.dumps(value, sort_keys=True) + "\n").encode("utf-8"))


def base_result() -> dict[str, Any]:
    return {
        "approvable": False,
        "session_proposal_approved": False,
        **{field: False for field in FALSE_AUTHORIZATION_FIELDS},
        "approver_declaration": None,
        "issue": None,
        "risk": None,
        "base_commit": None,
        "proposal_sha256": None,
        "worktree_receipt_sha256": None,
        "runner_controls_ready": False,
        "runner_readiness_sha256": None,
        "approval_bindings_sha256": None,
        "approval_receipt": None,
        "approval_receipt_sha256": None,
        "approval_receipt_size_bytes": None,
        "receipt_written": False,
        "required_confirmation": None,
        "failures": [],
    }


def validate_receipt_target(
    repo_root: Path,
    workspace: Path,
    approval_receipt: Path,
    policy: dict[str, Any],
) -> Path:
    approval_receipt = approval_receipt.resolve()
    if "\n" in str(approval_receipt) or "\r" in str(approval_receipt):
        raise ValueError("Implementation-session approval receipt path must not contain line breaks")
    if approval_receipt.is_symlink():
        raise ValueError("Implementation-session approval receipt symbolic links are not allowed")
    if policy["require_external_approval_receipt"] and build_stage_context.is_within(
        approval_receipt,
        repo_root,
    ):
        raise ValueError("Implementation-session approval receipt must be outside the Git checkout")
    if policy["require_approval_receipt_outside_workspace"] and build_stage_context.is_within(
        approval_receipt,
        workspace.resolve(),
    ):
        raise ValueError("Implementation-session approval receipt must be outside the workspace")
    if policy["require_absent_approval_receipt"] and approval_receipt.exists():
        raise ValueError("Implementation-session approval receipt already exists")
    if not approval_receipt.parent.is_dir():
        raise ValueError("Implementation-session approval receipt parent must exist")
    return approval_receipt


def assess_approval(
    repo: Path,
    proposal: Path,
    proposal_sha256: str,
    workspace: Path,
    worktree_receipt: Path,
    worktree_receipt_sha256: str,
    approval_receipt: Path,
    policies: dict[str, Any],
    readiness_runner: Callable[[Path, dict[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    result = base_result()
    repo_root = Path(
        diff_policy.run_git(repo, "rev-parse", "--show-toplevel").decode("utf-8").strip()
    ).resolve()
    approval_receipt = validate_receipt_target(
        repo_root,
        workspace,
        approval_receipt,
        policies["approval"],
    )
    result.update(
        proposal_sha256=proposal_sha256,
        worktree_receipt_sha256=worktree_receipt_sha256,
        approval_receipt=str(approval_receipt),
    )

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
    if policies["approval"]["require_valid_proposal"] and not proposal_validation["valid"]:
        result["failures"].append(
            failure(
                "proposal_validation",
                "Implementation-session approval requires a valid exact proposal.",
                validation=proposal_validation,
            )
        )
    else:
        result.update(
            issue=proposal_validation["issue"],
            risk=proposal_validation["risk"],
            base_commit=proposal_validation["base_commit"],
        )

    runner = readiness_runner or assess_runner_readiness.assess
    try:
        readiness = runner(repo_root, policies["runner"])
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        readiness = {
            "assessment_complete": False,
            "controls_ready": False,
            "failures": [failure("runner_readiness", str(error))],
        }
    result["runner_controls_ready"] = readiness.get("controls_ready") is True
    result["runner_readiness_sha256"] = canonical_sha256(readiness)
    if policies["approval"]["require_runner_controls_ready"] and not result["runner_controls_ready"]:
        result["failures"].append(
            failure(
                "runner_controls_ready",
                "Implementation-session approval requires all runner controls to be ready.",
                readiness=readiness,
            )
        )

    _bindings, bindings_sha256 = binding_records(policies["approval"])
    result["approval_bindings_sha256"] = bindings_sha256
    head = diff_policy.run_git(repo_root, "rev-parse", "HEAD").decode("ascii").strip()
    if (
        policies["approval"]["require_repo_head_match"]
        and result["base_commit"] is not None
        and head != result["base_commit"]
    ):
        result["failures"].append(
            failure("repo_head_match", "Repository HEAD differs from proposal base.")
        )
    status = diff_policy.run_git_with_environment(
        repo_root,
        {"GIT_OPTIONAL_LOCKS": "0"},
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
    )
    if policies["approval"]["require_clean_worktree"] and status:
        result["failures"].append(failure("clean_worktree", "Repository worktree must be clean."))

    if result["issue"] is not None:
        result["required_confirmation"] = (
            f"{policies['approval']['confirmation_prefix']} "
            f"issue={result['issue']} risk={result['risk']} base_commit={result['base_commit']} "
            f"proposal_sha256={proposal_sha256} "
            f"worktree_receipt_sha256={worktree_receipt_sha256} "
            f"runner_readiness_sha256={result['runner_readiness_sha256']} "
            f"approval_bindings_sha256={bindings_sha256} "
            f"approval_receipt={approval_receipt}"
        )
    result["approvable"] = not result["failures"]
    return result


def write_exclusive(path: Path, content: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(content)


def approve(
    args: argparse.Namespace,
    policies: dict[str, Any],
    assessment: dict[str, Any],
    readiness_runner: Callable[[Path, dict[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    approver = apply_stage_output.validate_reviewer(
        args.approver,
        policies["approval"]["max_approver_chars"],
    )
    if build_stage_context.detect_secrets(
        [build_stage_context.content_record("approver", approver)],
        policies["diff"],
    ):
        raise ValueError("Approver declaration contains a high-confidence secret signature")
    if args.confirm != assessment["required_confirmation"]:
        assessment["failures"].append(
            failure("confirmation_mismatch", "Confirmation does not match the current exact proposal.")
        )
        assessment["approvable"] = False
        return assessment
    refreshed = assess_approval(
        args.repo,
        args.proposal,
        args.proposal_sha256,
        args.workspace,
        args.worktree_receipt,
        args.worktree_receipt_sha256,
        args.approval_receipt,
        policies,
        readiness_runner,
    )
    if not refreshed["approvable"] or args.confirm != refreshed["required_confirmation"]:
        refreshed["failures"].append(failure("state_changed", "Session approval state changed."))
        refreshed["approvable"] = False
        return refreshed

    bindings, bindings_sha256 = binding_records(policies["approval"])
    receipt_value = {
        "session_approval_receipt_version": policies["approval"]["version"],
        "purpose": policies["approval"]["purpose"],
        "mode": policies["approval"]["mode"],
        **{field: False for field in FALSE_AUTHORIZATION_FIELDS},
        "session_proposal_approved": True,
        "runner_controls_ready": refreshed["runner_controls_ready"],
        "approver_declaration": approver,
        "issue": refreshed["issue"],
        "risk": refreshed["risk"],
        "base_commit": refreshed["base_commit"],
        "proposal_sha256": refreshed["proposal_sha256"],
        "worktree_receipt_sha256": refreshed["worktree_receipt_sha256"],
        "runner_readiness_sha256": refreshed["runner_readiness_sha256"],
        "confirmation_sha256": sha256_bytes(args.confirm.encode("utf-8")),
        "bindings": bindings,
    }
    receipt_bytes = (json.dumps(receipt_value, indent=2, sort_keys=True) + "\n").encode("utf-8")
    if len(receipt_bytes) > policies["approval"]["max_session_approval_receipt_bytes"]:
        raise ValueError("Implementation-session approval receipt exceeds byte limit")
    approval_receipt = args.approval_receipt.resolve()
    write_exclusive(approval_receipt, receipt_bytes)
    refreshed.update(
        approver_declaration=approver,
        approval_bindings_sha256=bindings_sha256,
        approval_receipt=str(approval_receipt),
        approval_receipt_sha256=sha256_bytes(receipt_bytes),
        approval_receipt_size_bytes=len(receipt_bytes),
        receipt_written=True,
        session_proposal_approved=True,
    )
    return refreshed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("check", "approve"):
        command = subparsers.add_parser(name)
        command.add_argument("--repo", type=Path, required=True)
        command.add_argument("--proposal", type=Path, required=True)
        command.add_argument("--proposal-sha256", required=True)
        command.add_argument("--workspace", type=Path, required=True)
        command.add_argument("--worktree-receipt", type=Path, required=True)
        command.add_argument("--worktree-receipt-sha256", required=True)
        command.add_argument("--approval-receipt", type=Path, required=True)
        command.add_argument("--format", choices=("text", "json"), default="text")
    subparsers.choices["approve"].add_argument("--approver", required=True)
    subparsers.choices["approve"].add_argument("--confirm", required=True)
    return parser


def format_text(result: dict[str, Any]) -> str:
    status = "APPROVABLE" if result["approvable"] else "NOT_APPROVABLE"
    if result["session_proposal_approved"]:
        status = "APPROVED"
    lines = [
        f"implementation-session-approval: {status} issue={result['issue'] or 'unknown'}",
        "session_start_authorized=false",
        "agent_invocation_authorized=false",
    ]
    if result["required_confirmation"]:
        lines.append(f"required_confirmation={result['required_confirmation']}")
    lines.extend(f"- {item['rule']}: {item['message']}" for item in result["failures"])
    return "\n".join(lines)


def main() -> int:
    args = build_parser().parse_args()
    try:
        policies = load_policies()
        assessment = assess_approval(
            args.repo,
            args.proposal,
            args.proposal_sha256,
            args.workspace,
            args.worktree_receipt,
            args.worktree_receipt_sha256,
            args.approval_receipt,
            policies,
        )
        result = approve(args, policies, assessment) if args.command == "approve" else assessment
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        print(f"implementation-session-approval: ERROR\n- {error}", file=sys.stderr)
        return 1
    if args.format == "json":
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(format_text(result))
    return 0 if (result["approvable"] or result["session_proposal_approved"]) else 2


if __name__ == "__main__":
    raise SystemExit(main())
