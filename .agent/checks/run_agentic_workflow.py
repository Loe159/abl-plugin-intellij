#!/usr/bin/env python3
"""Trigger the supervised implementation workflow with one explicit command."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import build_supervised_runner_invocation
import initialize_portable_run


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / ".agent" / "policies" / "agentic-workflow-trigger.json"
FALSE_FIELDS = (
    "authorized",
    "agent_invocation_authorized",
    "implementation_authorized",
    "repository_mutation_authorized",
    "network_authorized",
    "publication_authorized",
    "merge_authorized",
    "runner_selected",
    "session_start_authorized",
)

EXPECTED_POLICY: dict[str, Any] = {
    "version": 1,
    "purpose": "agentic_workflow_single_command_trigger",
    "mode": "dry-run-or-explicit-execute",
    "default_dry_run": True,
    "require_execute_flag_for_runner_process": True,
    "require_runner_invocation_builder": True,
    "command_timeout_seconds": 1800.0,
    "max_captured_output_bytes": 20000,
    "bindings": [
        ".agent/checks/run_agentic_workflow.py",
        ".agent/policies/agentic-workflow-trigger.json",
        ".agent/checks/build_supervised_runner_invocation.py",
        ".agent/policies/supervised-runner-invocation.json",
        ".agent/checks/run_supervised_implementation.py",
        ".agent/policies/supervised-implementation-runner.json",
        "docs/agent-guides/supervised-runner-workflow.md",
    ],
}


def load_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    policy = json.loads(path.read_text(encoding="utf-8"))
    if policy != EXPECTED_POLICY:
        raise ValueError("Agentic workflow trigger policy does not match")
    return policy


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def run_command(
    argv: Sequence[str],
    cwd: Path,
    timeout_seconds: float,
    max_output_bytes: int,
) -> dict[str, Any]:
    completed = subprocess.run(
        list(argv),
        cwd=cwd,
        check=False,
        capture_output=True,
        timeout=timeout_seconds,
    )
    stdout = (completed.stdout or b"")[:max_output_bytes]
    stderr = (completed.stderr or b"")[:max_output_bytes]
    return {
        "argv": list(argv),
        "returncode": completed.returncode,
        "stdout_bytes": len(stdout),
        "stderr_bytes": len(stderr),
        "stdout_sha256": sha256_bytes(stdout),
        "stderr_sha256": sha256_bytes(stderr),
        "stdout_truncated": len(completed.stdout or b"") > len(stdout),
        "stderr_truncated": len(completed.stderr or b"") > len(stderr),
    }


def build_base_result(
    invocation: dict[str, Any],
    execute: bool,
    policy: dict[str, Any],
) -> dict[str, Any]:
    return {
        "trigger_version": policy["version"],
        "purpose": policy["purpose"],
        "mode": policy["mode"],
        **{field: False for field in FALSE_FIELDS},
        "dry_run": not execute,
        "execute_requested": execute,
        "workflow_trigger_ready": invocation["runner_invocation_ready"] is True,
        "runner_process_started": False,
        "runner_exit_code": None,
        "runner_completed": False,
        "runner_blocked": False,
        "final_receipt_present": False,
        "final_receipt": invocation["outputs"]["final_receipt"],
        "final_receipt_sha256": None,
        "invocation": invocation,
        "runner_process": None,
        "bindings": initialize_portable_run.binding_records(policy["bindings"]),
    }


def trigger_workflow(
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
    execute: bool,
    policy: dict[str, Any],
    command_runner: Callable[[Sequence[str], Path, float, int], dict[str, Any]] = run_command,
) -> dict[str, Any]:
    invocation = build_supervised_runner_invocation.build_invocation(
        repo,
        proposal,
        workspace,
        worktree_receipt,
        approval_receipt,
        preflight,
        authorization_receipt,
        output_dir,
        gradle_user_home,
        runner_format,
        adapter_command,
        build_supervised_runner_invocation.load_policy(),
    )
    result = build_base_result(invocation, execute, policy)
    if not execute:
        return result

    record = command_runner(
        invocation["command"],
        Path(invocation["repo"]),
        policy["command_timeout_seconds"],
        policy["max_captured_output_bytes"],
    )
    result["runner_process"] = record
    result["runner_process_started"] = True
    result["runner_exit_code"] = record["returncode"]
    result["runner_completed"] = record["returncode"] == 0
    result["runner_blocked"] = record["returncode"] == 2
    final_receipt = Path(result["final_receipt"])
    if final_receipt.is_file() and not final_receipt.is_symlink():
        result["final_receipt_present"] = True
        result["final_receipt_sha256"] = sha256_file(final_receipt)
    return result


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
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("adapter_command", nargs=argparse.REMAINDER)
    return parser


def format_text(result: dict[str, Any]) -> str:
    if result["dry_run"]:
        status = "READY"
    elif result["runner_completed"]:
        status = "COMPLETE"
    elif result["runner_blocked"]:
        status = "BLOCKED"
    else:
        status = "FAILED"
    lines = [
        f"agentic-workflow-trigger: {status}",
        f"dry_run={str(result['dry_run']).lower()}",
        f"execute_requested={str(result['execute_requested']).lower()}",
        f"runner_process_started={str(result['runner_process_started']).lower()}",
        f"runner_exit_code={result['runner_exit_code']}",
        "agent_invocation_authorized=false",
        "publication_authorized=false",
    ]
    if result["dry_run"]:
        lines.append("command_json=" + json.dumps(result["invocation"]["command"], ensure_ascii=True))
    return "\n".join(lines)


def main() -> int:
    args = build_parser().parse_args()
    command = args.adapter_command
    if command and command[0] == "--":
        command = command[1:]
    elif command and command[0].startswith("--"):
        print(
            "agentic-workflow-trigger: ERROR\n- adapter command options must follow --",
            file=sys.stderr,
        )
        return 1
    try:
        result = trigger_workflow(
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
            args.execute,
            load_policy(),
        )
    except (
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        ValueError,
        subprocess.TimeoutExpired,
    ) as error:
        print(f"agentic-workflow-trigger: ERROR\n- {error}", file=sys.stderr)
        return 1
    if args.format == "json":
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(format_text(result))
    if result["dry_run"] or result["runner_completed"]:
        return 0
    return 2 if result["runner_blocked"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
