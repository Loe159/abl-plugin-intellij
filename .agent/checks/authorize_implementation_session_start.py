#!/usr/bin/env python3
"""Authorize one exact implementation session-start boundary without invoking it."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable

import apply_stage_output
import approve_implementation_session
import build_stage_context
import check_implementation_session_start
import diff_policy
import initialize_portable_run


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = (
    REPO_ROOT / ".agent" / "policies" / "implementation-session-start-authorization.json"
)
FALSE_FIELDS = (
    "authorized",
    "agent_invocation_authorized",
    "implementation_authorized",
    "repository_mutation_authorized",
    "network_authorized",
    "publication_authorized",
    "runner_selected",
)

EXPECTED_POLICY: dict[str, Any] = {
    "version": 1,
    "purpose": "implementation_session_start_authorization",
    "mode": "exact-local-start-authorization-only",
    "confirmation_prefix": "AUTHORIZE-EXACT-IMPLEMENTATION-SESSION-START",
    "max_authorizer_chars": 80,
    "max_authorization_receipt_bytes": 40000,
    "require_session_start_ready": True,
    "require_external_authorization_receipt": True,
    "require_authorization_receipt_outside_workspace": True,
    "require_absent_authorization_receipt": True,
    "require_clean_worktree": True,
    "require_repo_head_match": True,
    "replay_prevention_enforced": False,
    "bindings": [
        ".agent/checks/authorize_implementation_session_start.py",
        ".agent/policies/implementation-session-start-authorization.json",
        ".agent/checks/check_implementation_session_start.py",
        ".agent/policies/implementation-session-start.json",
        ".agent/checks/check_implementation_runner_selection.py",
        ".agent/policies/implementation-runner-selection.json",
        ".agent/checks/validate_implementation_invocation_preflight.py",
        ".agent/policies/implementation-invocation-preflight-validation.json",
        ".agent/checks/assess_runner_readiness.py",
        ".agent/policies/runner-readiness.json",
    ],
}


def load_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    policy = json.loads(path.read_text(encoding="utf-8"))
    if policy != EXPECTED_POLICY:
        raise ValueError("Session-start authorization policy does not match")
    return policy


def load_policies() -> dict[str, Any]:
    return {
        **check_implementation_session_start.load_policies(),
        "start_authorization": load_policy(),
    }


def failure(rule: str, message: str, **details: Any) -> dict[str, Any]:
    return {"rule": rule, "message": message, **details}


def sha256_bytes(content: bytes) -> str:
    return approve_implementation_session.sha256_bytes(content)


def canonical_sha256(value: Any) -> str:
    return approve_implementation_session.canonical_sha256(value)


def binding_records(policy: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
    records = initialize_portable_run.binding_records(policy["bindings"])
    digest = sha256_bytes((json.dumps(records, sort_keys=True) + "\n").encode("utf-8"))
    return records, digest


def base_result() -> dict[str, Any]:
    return {
        "authorizable": False,
        "session_start_authorized": False,
        **{field: False for field in FALSE_FIELDS},
        "authorizer_authenticated": False,
        "authorizer_declaration": None,
        "issue": None,
        "risk": None,
        "base_commit": None,
        "workspace": None,
        "candidate_runner": None,
        "proposal_sha256": None,
        "worktree_receipt_sha256": None,
        "approval_receipt_sha256": None,
        "preflight_sha256": None,
        "session_start_readiness_sha256": None,
        "authorization_bindings_sha256": None,
        "authorization_receipt": None,
        "authorization_receipt_sha256": None,
        "authorization_receipt_size_bytes": None,
        "receipt_written": False,
        "replay_prevention_enforced": False,
        "required_confirmation": None,
        "failures": [],
    }


def validate_receipt_target(
    repo_root: Path,
    workspace: Path,
    authorization_receipt: Path,
    policy: dict[str, Any],
) -> Path:
    if authorization_receipt.is_symlink():
        raise ValueError("Session-start authorization receipt symlinks are not allowed")
    target = authorization_receipt.resolve()
    if "\n" in str(target) or "\r" in str(target):
        raise ValueError("Session-start authorization receipt path must not contain line breaks")
    if policy["require_external_authorization_receipt"] and build_stage_context.is_within(
        target, repo_root
    ):
        raise ValueError("Session-start authorization receipt must be outside the Git checkout")
    if policy["require_authorization_receipt_outside_workspace"] and build_stage_context.is_within(
        target, workspace.resolve()
    ):
        raise ValueError("Session-start authorization receipt must be outside the workspace")
    if policy["require_absent_authorization_receipt"] and target.exists():
        raise ValueError("Session-start authorization receipt already exists")
    if not target.parent.is_dir():
        raise ValueError("Session-start authorization receipt parent must exist")
    return target


def assess_authorization(
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
    policies: dict[str, Any],
    readiness_runner: Callable[[Path, dict[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    result = base_result()
    repo_root = Path(
        diff_policy.run_git(repo, "rev-parse", "--show-toplevel").decode("utf-8").strip()
    ).resolve()
    workspace = workspace.resolve()
    policy = policies["start_authorization"]
    target = validate_receipt_target(repo_root, workspace, authorization_receipt, policy)
    result.update(
        workspace=str(workspace),
        proposal_sha256=proposal_sha256,
        worktree_receipt_sha256=worktree_receipt_sha256,
        approval_receipt_sha256=approval_receipt_sha256,
        preflight_sha256=preflight_sha256,
        authorization_receipt=str(target),
        replay_prevention_enforced=policy["replay_prevention_enforced"],
    )

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
    result.update(
        issue=start.get("issue"),
        risk=start.get("risk"),
        base_commit=start.get("base_commit"),
        candidate_runner=start.get("candidate_runner"),
        session_start_readiness_sha256=canonical_sha256(start),
    )
    if policy["require_session_start_ready"] and start.get("session_start_ready") is not True:
        result["failures"].append(
            failure(
                "session_start_readiness",
                "Authorization requires current session-start readiness.",
                readiness=start,
            )
        )

    _bindings, bindings_sha256 = binding_records(policy)
    result["authorization_bindings_sha256"] = bindings_sha256
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

    if result["issue"] is not None and result["candidate_runner"] is not None:
        runner_sha256 = canonical_sha256(result["candidate_runner"])
        result["required_confirmation"] = (
            f"{policy['confirmation_prefix']} "
            f"issue={result['issue']} risk={result['risk']} "
            f"base_commit={result['base_commit']} workspace={workspace} "
            f"proposal_sha256={proposal_sha256} "
            f"worktree_receipt_sha256={worktree_receipt_sha256} "
            f"approval_receipt_sha256={approval_receipt_sha256} "
            f"preflight_sha256={preflight_sha256} "
            f"candidate_runner_sha256={runner_sha256} "
            f"session_start_readiness_sha256={result['session_start_readiness_sha256']} "
            f"authorization_bindings_sha256={bindings_sha256} "
            f"authorization_receipt={target}"
        )
    result["authorizable"] = not result["failures"]
    return result


def write_exclusive(path: Path, content: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(content)


def authorize(
    args: argparse.Namespace,
    policies: dict[str, Any],
    assessment: dict[str, Any],
    readiness_runner: Callable[[Path, dict[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    policy = policies["start_authorization"]
    authorizer = apply_stage_output.validate_reviewer(
        args.authorizer, policy["max_authorizer_chars"]
    )
    if build_stage_context.detect_secrets(
        [build_stage_context.content_record("authorizer", authorizer)],
        policies["diff"],
    ):
        raise ValueError("Authorizer declaration contains a high-confidence secret signature")
    if args.confirm != assessment["required_confirmation"]:
        assessment["failures"].append(
            failure(
                "confirmation_mismatch",
                "Confirmation does not match the current exact session-start boundary.",
            )
        )
        assessment["authorizable"] = False
        return assessment

    refreshed = assess_authorization(
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
        policies,
        readiness_runner,
    )
    if not refreshed["authorizable"] or args.confirm != refreshed["required_confirmation"]:
        refreshed["failures"].append(
            failure("state_changed", "Session-start authorization state changed.")
        )
        refreshed["authorizable"] = False
        return refreshed

    bindings, bindings_sha256 = binding_records(policy)
    receipt_value = {
        "start_authorization_receipt_version": policy["version"],
        "purpose": policy["purpose"],
        "mode": policy["mode"],
        **{field: False for field in FALSE_FIELDS},
        "session_start_authorized": True,
        "authorizer_authenticated": False,
        "authorizer_declaration": authorizer,
        "replay_prevention_enforced": False,
        "issue": refreshed["issue"],
        "risk": refreshed["risk"],
        "base_commit": refreshed["base_commit"],
        "workspace": refreshed["workspace"],
        "candidate_runner": refreshed["candidate_runner"],
        "proposal_sha256": refreshed["proposal_sha256"],
        "worktree_receipt_sha256": refreshed["worktree_receipt_sha256"],
        "approval_receipt_sha256": refreshed["approval_receipt_sha256"],
        "preflight_sha256": refreshed["preflight_sha256"],
        "session_start_readiness_sha256": refreshed["session_start_readiness_sha256"],
        "confirmation_sha256": sha256_bytes(args.confirm.encode("utf-8")),
        "bindings": bindings,
    }
    receipt_bytes = (json.dumps(receipt_value, indent=2, sort_keys=True) + "\n").encode("utf-8")
    if len(receipt_bytes) > policy["max_authorization_receipt_bytes"]:
        raise ValueError("Session-start authorization receipt exceeds byte limit")
    target = args.authorization_receipt.resolve()
    write_exclusive(target, receipt_bytes)
    refreshed.update(
        session_start_authorized=True,
        authorizer_declaration=authorizer,
        authorization_bindings_sha256=bindings_sha256,
        authorization_receipt=str(target),
        authorization_receipt_sha256=sha256_bytes(receipt_bytes),
        authorization_receipt_size_bytes=len(receipt_bytes),
        receipt_written=True,
    )
    return refreshed


def add_common_arguments(parser: argparse.ArgumentParser) -> None:
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
    parser.add_argument("--format", choices=("text", "json"), default="text")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("check", "authorize"):
        add_common_arguments(subparsers.add_parser(name))
    subparsers.choices["authorize"].add_argument("--authorizer", required=True)
    subparsers.choices["authorize"].add_argument("--confirm", required=True)
    return parser


def format_text(result: dict[str, Any]) -> str:
    status = "AUTHORIZABLE" if result["authorizable"] else "NOT_AUTHORIZABLE"
    if result["session_start_authorized"]:
        status = "AUTHORIZED"
    lines = [
        f"implementation-session-start-authorization: {status} "
        f"issue={result['issue'] or 'unknown'}",
        f"session_start_authorized={str(result['session_start_authorized']).lower()}",
        "agent_invocation_authorized=false",
        "replay_prevention_enforced=false",
    ]
    if result["required_confirmation"]:
        lines.append(f"required_confirmation={result['required_confirmation']}")
    lines.extend(f"- {item['rule']}: {item['message']}" for item in result["failures"])
    return "\n".join(lines)


def main() -> int:
    args = build_parser().parse_args()
    try:
        policies = load_policies()
        assessment = assess_authorization(
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
            policies,
        )
        result = (
            authorize(args, policies, assessment)
            if args.command == "authorize"
            else assessment
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        print(f"implementation-session-start-authorization: ERROR\n- {error}", file=sys.stderr)
        return 1
    if args.format == "json":
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(format_text(result))
    return 0 if (result["authorizable"] or result["session_start_authorized"]) else 2


if __name__ == "__main__":
    raise SystemExit(main())
