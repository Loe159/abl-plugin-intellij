#!/usr/bin/env python3
"""Validate one exact supervised implementation proposal without authorizing it."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

import build_implementation_handoff
import build_implementation_session
import build_stage_context
import diff_policy


REPO_ROOT = Path(__file__).resolve().parents[2]
PROMPTS_DIR = REPO_ROOT / ".agent" / "prompts"
FALSE_AUTHORIZATION_FIELDS = (
    *build_implementation_session.FALSE_AUTHORIZATION_FIELDS,
    "session_start_authorized",
)


def failure(rule: str, message: str, **details: Any) -> dict[str, Any]:
    return {"rule": rule, "message": message, **details}


def base_result() -> dict[str, Any]:
    return {
        "valid": False,
        **{field: False for field in FALSE_AUTHORIZATION_FIELDS},
        "issue": None,
        "risk": None,
        "base_commit": None,
        "proposal_sha256": None,
        "handoff_sha256": None,
        "failures": [],
    }


def reconstructed_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


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


def validate_handoff_record(record: Any, policy: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(record, dict) or set(record) != {"sha256", "size_bytes", "content"}:
        raise ValueError("Proposal handoff record fields do not match the contract")
    if (
        not isinstance(record["sha256"], str)
        or not build_implementation_session.SHA256.fullmatch(record["sha256"])
        or not isinstance(record["size_bytes"], int)
        or isinstance(record["size_bytes"], bool)
        or record["size_bytes"] < 1
        or not isinstance(record["content"], dict)
    ):
        raise ValueError("Proposal handoff record types do not match the contract")
    content = reconstructed_json_bytes(record["content"])
    if len(content) != record["size_bytes"]:
        raise ValueError("Proposal handoff size does not match its content")
    if build_implementation_session.sha256_bytes(content) != record["sha256"]:
        raise ValueError("Proposal handoff SHA-256 does not match its content")
    with tempfile.TemporaryDirectory() as temp_dir:
        path = Path(temp_dir) / "handoff.json"
        path.write_bytes(content)
        return build_implementation_session.validate_handoff(
            path,
            record["sha256"],
            policy["max_handoff_bytes"],
        )


def validate_proposal_value(
    proposal: Any,
    repo_root: Path,
    policies: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    failures: list[dict[str, Any]] = []
    expected_fields = {
        "proposal_version",
        "purpose",
        "mode",
        *FALSE_AUTHORIZATION_FIELDS,
        "issue",
        "risk",
        "base_commit",
        "repo_head",
        "handoff",
        "prompt",
        "policy_bindings",
        "workspace",
        "prepared_workspace",
        "capabilities",
        "budgets",
        "required_external_controls",
    }
    if not isinstance(proposal, dict) or set(proposal) != expected_fields:
        return [failure("proposal_schema", "Proposal fields do not match the contract.")], None
    policy = policies["session"]
    if (
        not isinstance(proposal["proposal_version"], int)
        or isinstance(proposal["proposal_version"], bool)
        or proposal["proposal_version"] != policy["version"]
        or proposal["purpose"] != policy["purpose"]
        or proposal["mode"] != policy["mode"]
        or any(proposal[field] is not False for field in FALSE_AUTHORIZATION_FIELDS)
    ):
        failures.append(
            failure("proposal_metadata", "Proposal safety metadata does not match the contract.")
        )
    try:
        handoff = validate_handoff_record(proposal["handoff"], policy)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        failures.append(failure("proposal_handoff", str(error)))
        return failures, None
    if (
        type(proposal["issue"]) is not int
        or proposal["issue"] != handoff["issue"]
        or type(proposal["risk"]) is not str
        or proposal["risk"] != handoff["risk"]
        or type(proposal["base_commit"]) is not str
        or proposal["base_commit"] != handoff["base_commit"]
        or type(proposal["repo_head"]) is not str
        or proposal["repo_head"] != proposal["base_commit"]
    ):
        failures.append(
            failure("proposal_identity", "Proposal identity does not match its exact handoff.")
        )

    trusted_prompt = build_implementation_session.validate_prompt(
        PROMPTS_DIR / policy["prompt"],
        policy,
    )
    if not exact_equal(proposal["prompt"], trusted_prompt):
        failures.append(
            failure("proposal_prompt", "Proposal prompt differs from the trusted prompt.")
        )
    workspace_bindings = build_implementation_session.binding_records(
        repo_root,
        policy["policy_bindings"],
    )
    trusted_bindings = build_implementation_session.binding_records(
        REPO_ROOT,
        policy["policy_bindings"],
    )
    if not exact_equal(proposal["policy_bindings"], workspace_bindings):
        failures.append(
            failure("proposal_policy_bindings", "Proposal policy bindings differ from workspace.")
        )
    if not exact_equal(workspace_bindings, trusted_bindings):
        failures.append(
            failure("bound_policy_mismatch", "Workspace policies differ from trusted policies.")
        )
    for field in ("workspace", "capabilities", "budgets", "required_external_controls"):
        if not exact_equal(proposal[field], policy[field]):
            failures.append(
                failure(f"proposal_{field}", f"Proposal {field} differs from the fixed policy.")
            )
    detections = build_stage_context.detect_secrets(
        [
            build_stage_context.content_record(
                "implementation-session-proposal.json",
                json.dumps(proposal),
            )
        ],
        policies["diff"],
    )
    if detections:
        failures.append(
            failure(
                "high_confidence_secret",
                "Proposal contains a high-confidence secret signature.",
                detections=detections,
            )
        )
    return failures, handoff


def validate_proposal(
    repo: Path,
    proposal_path: Path,
    expected_sha256: str,
    workspace: Path,
    worktree_receipt: Path,
    worktree_receipt_sha256: str,
    policies: dict[str, Any],
) -> dict[str, Any]:
    result = base_result()
    if proposal_path.is_symlink():
        raise ValueError("Implementation session proposal symbolic links are not allowed")
    repo_root = Path(
        diff_policy.run_git(repo, "rev-parse", "--show-toplevel").decode("utf-8").strip()
    ).resolve()
    proposal_path = proposal_path.resolve()
    if build_stage_context.is_within(proposal_path, repo_root):
        raise ValueError("Implementation session proposal must be outside the Git checkout")
    if not build_implementation_session.SHA256.fullmatch(expected_sha256):
        raise ValueError("Expected proposal SHA-256 must be 64 lowercase hexadecimal characters")
    if not proposal_path.is_file():
        raise ValueError("Implementation session proposal must be an existing regular file")
    if proposal_path.stat().st_size > policies["session"]["max_proposal_bytes"]:
        result["failures"].append(
            failure("max_proposal_bytes", "Proposal exceeds the configured byte limit.")
        )
        return result
    proposal_bytes = proposal_path.read_bytes()
    result["proposal_sha256"] = build_implementation_session.sha256_bytes(proposal_bytes)
    if result["proposal_sha256"] != expected_sha256:
        result["failures"].append(
            failure("proposal_sha256", "Proposal does not match its expected SHA-256.")
        )
        return result
    proposal = json.loads(proposal_bytes.decode("utf-8-sig"))
    failures, handoff = validate_proposal_value(proposal, repo_root, policies)
    result["failures"].extend(failures)
    if handoff is not None:
        result.update(
            issue=handoff["issue"],
            risk=handoff["risk"],
            base_commit=handoff["base_commit"],
            handoff_sha256=proposal["handoff"]["sha256"],
        )
    head = diff_policy.run_git(repo_root, "rev-parse", "HEAD").decode("ascii").strip()
    if policies["session"]["require_repo_head_match"] and result["base_commit"] is not None:
        if head != result["base_commit"]:
            result["failures"].append(
                failure("repo_head_match", "Repository HEAD differs from proposal base.")
            )
    status = build_implementation_handoff.repository_status(repo_root)
    if policies["session"]["require_clean_worktree"] and status:
        result["failures"].append(
            failure("clean_worktree", "Repository worktree must be clean.")
        )
    prepared_workspace = None
    if (
        policies["session"]["require_valid_disposable_worktree"]
        and result["base_commit"] is not None
    ):
        prepared_workspace, workspace_validation = (
            build_implementation_session.validate_prepared_workspace(
                repo_root,
                workspace,
                worktree_receipt,
                worktree_receipt_sha256,
                result["base_commit"],
            )
        )
        if prepared_workspace is None:
            result["failures"].append(
                failure(
                    "disposable_worktree_validation",
                    "Prepared disposable worktree did not validate.",
                    validation=workspace_validation,
                )
            )
        elif not exact_equal(proposal["prepared_workspace"], prepared_workspace):
            result["failures"].append(
                failure(
                    "proposal_prepared_workspace",
                    "Proposal prepared-workspace record differs from current validation.",
                )
            )
    if result["failures"]:
        return result

    refreshed_bindings = build_implementation_session.binding_records(
        repo_root,
        policies["session"]["policy_bindings"],
    )
    refreshed_trusted_bindings = build_implementation_session.binding_records(
        REPO_ROOT,
        policies["session"]["policy_bindings"],
    )
    refreshed_prompt = build_implementation_session.validate_prompt(
        PROMPTS_DIR / policies["session"]["prompt"],
        policies["session"],
    )
    refreshed_head = diff_policy.run_git(repo_root, "rev-parse", "HEAD").decode("ascii").strip()
    refreshed_status = build_implementation_handoff.repository_status(repo_root)
    refreshed_proposal = build_implementation_session.sha256_bytes(proposal_path.read_bytes())
    refreshed_prepared_workspace = None
    if policies["session"]["require_valid_disposable_worktree"]:
        refreshed_prepared_workspace, refreshed_workspace_validation = (
            build_implementation_session.validate_prepared_workspace(
                repo_root,
                workspace,
                worktree_receipt,
                worktree_receipt_sha256,
                result["base_commit"],
            )
        )
    if (
        refreshed_proposal != expected_sha256
        or refreshed_head != head
        or refreshed_status != status
        or not exact_equal(refreshed_bindings, proposal["policy_bindings"])
        or not exact_equal(refreshed_trusted_bindings, proposal["policy_bindings"])
        or not exact_equal(refreshed_prepared_workspace, prepared_workspace)
        or not exact_equal(refreshed_prompt, proposal["prompt"])
    ):
        result["failures"].append(
            failure(
                "state_changed",
                "Proposal, repository, prepared workspace, prompt, or policy changed during validation.",
            )
        )
        return result
    result["valid"] = True
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--proposal", type=Path, required=True)
    parser.add_argument("--proposal-sha256", required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--worktree-receipt", type=Path, required=True)
    parser.add_argument("--worktree-receipt-sha256", required=True)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def format_text(result: dict[str, Any]) -> str:
    status = "VALID" if result["valid"] else "INVALID"
    lines = [
        f"implementation-session-validation: {status} issue={result['issue'] or 'unknown'}",
        "session_start_authorized=false",
        "implementation_authorized=false",
    ]
    for item in result["failures"]:
        lines.append(f"- {item['rule']}: {item['message']}")
    return "\n".join(lines)


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = validate_proposal(
            args.repo,
            args.proposal,
            args.proposal_sha256,
            args.workspace,
            args.worktree_receipt,
            args.worktree_receipt_sha256,
            build_implementation_session.load_policies(),
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        print(f"implementation-session-validation: ERROR\n- {error}", file=sys.stderr)
        return 1
    if args.format == "json":
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(format_text(result))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
