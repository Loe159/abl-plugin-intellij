#!/usr/bin/env python3
"""Build one exact supervised-runner command without authorizing or running it."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Sequence

import build_stage_context
import diff_policy
import initialize_portable_run
import run_supervised_implementation
import validate_disposable_worktree


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / ".agent" / "policies" / "supervised-runner-invocation.json"
FALSE_FIELDS = (
    "authorized",
    "agent_invocation_authorized",
    "implementation_authorized",
    "repository_mutation_authorized",
    "network_authorized",
    "publication_authorized",
    "runner_selected",
    "session_start_authorized",
)

EXPECTED_POLICY: dict[str, Any] = {
    "version": 1,
    "purpose": "supervised_runner_invocation_builder",
    "mode": "command-construction-only",
    "require_valid_disposable_worktree_receipt": True,
    "require_external_output_dir": True,
    "require_outputs_outside_workspace": True,
    "require_absent_outputs": True,
    "output_files": [
        "expected-session.json",
        "result.json",
        "patch.diff",
        "patch-validation.json",
        "quality-gate.json",
        "final-receipt.json",
    ],
    "bindings": [
        ".agent/checks/build_supervised_runner_invocation.py",
        ".agent/policies/supervised-runner-invocation.json",
        ".agent/checks/run_supervised_implementation.py",
        ".agent/policies/supervised-implementation-runner.json",
        ".agent/checks/validate_disposable_worktree.py",
        ".agent/policies/disposable-worktree-validation.json",
    ],
}


def load_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    policy = json.loads(path.read_text(encoding="utf-8"))
    if policy != EXPECTED_POLICY:
        raise ValueError("Supervised-runner invocation policy does not match")
    return policy


def sha256_file(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"Input artifact must be an existing regular file: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_root(repo: Path) -> Path:
    return Path(
        diff_policy.run_git(repo, "rev-parse", "--show-toplevel").decode("utf-8").strip()
    ).resolve()


def validate_output_dir(
    repo_root: Path,
    workspace: Path,
    output_dir: Path,
    policy: dict[str, Any],
) -> dict[str, Path]:
    if output_dir.is_symlink():
        raise ValueError("Supervised-runner output directory must not be a symbolic link")
    output_dir = output_dir.resolve()
    if not output_dir.is_dir():
        raise ValueError("Supervised-runner output directory must exist")
    if "\n" in str(output_dir) or "\r" in str(output_dir):
        raise ValueError("Supervised-runner output directory must not contain line breaks")
    if policy["require_external_output_dir"] and build_stage_context.is_within(output_dir, repo_root):
        raise ValueError("Supervised-runner output directory must be outside the source checkout")
    if policy["require_outputs_outside_workspace"] and build_stage_context.is_within(
        output_dir,
        workspace.resolve(),
    ):
        raise ValueError("Supervised-runner output directory must be outside the workspace")
    outputs = [output_dir / name for name in policy["output_files"]]
    labels = run_supervised_implementation.validate_outputs(
        repo_root,
        workspace,
        outputs,
        run_supervised_implementation.load_policy(),
    )
    return labels


def command_value(
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
    outputs: dict[str, Path],
    gradle_user_home: Path,
    runner_format: str,
    adapter_command: Sequence[str],
) -> list[str]:
    return [
        sys.executable,
        str(REPO_ROOT / ".agent" / "checks" / "run_supervised_implementation.py"),
        "--repo",
        str(repo),
        "--proposal",
        str(proposal.resolve()),
        "--proposal-sha256",
        proposal_sha256,
        "--workspace",
        str(workspace.resolve()),
        "--worktree-receipt",
        str(worktree_receipt.resolve()),
        "--worktree-receipt-sha256",
        worktree_receipt_sha256,
        "--approval-receipt",
        str(approval_receipt.resolve()),
        "--approval-receipt-sha256",
        approval_receipt_sha256,
        "--preflight",
        str(preflight.resolve()),
        "--preflight-sha256",
        preflight_sha256,
        "--authorization-receipt",
        str(authorization_receipt.resolve()),
        "--authorization-receipt-sha256",
        authorization_receipt_sha256,
        "--expected-session-output",
        str(outputs["expected_session"]),
        "--result-output",
        str(outputs["result"]),
        "--patch-output",
        str(outputs["patch"]),
        "--patch-receipt-output",
        str(outputs["patch_receipt"]),
        "--quality-gate-receipt-output",
        str(outputs["quality_gate_receipt"]),
        "--final-receipt-output",
        str(outputs["final_receipt"]),
        "--gradle-user-home",
        str(gradle_user_home.resolve()),
        "--format",
        runner_format,
        "--",
        *adapter_command,
    ]


def build_invocation(
    repo: Path,
    proposal: Path,
    workspace: Path,
    worktree_receipt: Path,
    approval_receipt: Path,
    preflight: Path,
    authorization_receipt: Path,
    output_dir: Path,
    gradle_user_home: Path,
    runner_format: str,
    adapter_command: Sequence[str],
    policy: dict[str, Any],
) -> dict[str, Any]:
    if not adapter_command:
        raise ValueError("Adapter command is required")
    repo_root = source_root(repo)
    workspace = workspace.resolve()
    proposal_sha256 = sha256_file(proposal)
    worktree_receipt_sha256 = sha256_file(worktree_receipt)
    approval_receipt_sha256 = sha256_file(approval_receipt)
    preflight_sha256 = sha256_file(preflight)
    authorization_receipt_sha256 = sha256_file(authorization_receipt)
    if not gradle_user_home.resolve().is_dir():
        raise ValueError("Gradle user home must be an existing directory")

    if policy["require_valid_disposable_worktree_receipt"]:
        worktree_validation = validate_disposable_worktree.validate(
            repo_root,
            workspace,
            worktree_receipt,
            worktree_receipt_sha256,
            validate_disposable_worktree.load_policy(),
        )
        if worktree_validation["valid"] is not True:
            raise ValueError("Disposable worktree receipt is not valid")
    else:
        worktree_validation = None

    outputs = validate_output_dir(repo_root, workspace, output_dir, policy)
    command = command_value(
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
        outputs,
        gradle_user_home,
        runner_format,
        adapter_command,
    )
    return {
        "invocation_version": policy["version"],
        "purpose": policy["purpose"],
        "mode": policy["mode"],
        **{field: False for field in FALSE_FIELDS},
        "runner_invocation_ready": True,
        "repo": str(repo_root),
        "workspace": str(workspace),
        "input_sha256": {
            "proposal": proposal_sha256,
            "worktree_receipt": worktree_receipt_sha256,
            "approval_receipt": approval_receipt_sha256,
            "preflight": preflight_sha256,
            "authorization_receipt": authorization_receipt_sha256,
        },
        "outputs": {label: str(path) for label, path in outputs.items()},
        "gradle_user_home": str(gradle_user_home.resolve()),
        "adapter_command": list(adapter_command),
        "command": command,
        "worktree_validation": worktree_validation,
        "bindings": initialize_portable_run.binding_records(policy["bindings"]),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--proposal", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--worktree-receipt", type=Path, required=True)
    parser.add_argument("--approval-receipt", type=Path, required=True)
    parser.add_argument("--preflight", type=Path, required=True)
    parser.add_argument("--authorization-receipt", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--gradle-user-home", type=Path, required=True)
    parser.add_argument("--runner-format", choices=("text", "json"), default="json")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("adapter_command", nargs=argparse.REMAINDER)
    return parser


def format_text(result: dict[str, Any]) -> str:
    lines = [
        "supervised-runner-invocation: READY",
        "runner_selected=false",
        "agent_invocation_authorized=false",
        "command_json=" + json.dumps(result["command"], ensure_ascii=True),
    ]
    return "\n".join(lines)


def main() -> int:
    args = build_parser().parse_args()
    command = args.adapter_command
    if command and command[0] == "--":
        command = command[1:]
    elif command and command[0].startswith("--"):
        print(
            "supervised-runner-invocation: ERROR\n- adapter command options must follow --",
            file=sys.stderr,
        )
        return 1
    try:
        result = build_invocation(
            args.repo,
            args.proposal,
            args.workspace,
            args.worktree_receipt,
            args.approval_receipt,
            args.preflight,
            args.authorization_receipt,
            args.output_dir,
            args.gradle_user_home,
            args.runner_format,
            command,
            load_policy(),
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        print(f"supervised-runner-invocation: ERROR\n- {error}", file=sys.stderr)
        return 1
    if args.format == "json":
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(format_text(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
