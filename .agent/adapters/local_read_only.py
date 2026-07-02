#!/usr/bin/env python3
"""Run one explicit local read-only command and validate its captured response."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Sequence


REPO_ROOT = Path(__file__).resolve().parents[2]
CHECKS_DIR = REPO_ROOT / ".agent" / "checks"
sys.path.insert(0, str(CHECKS_DIR))

import build_stage_context  # noqa: E402
import diff_policy  # noqa: E402
import validate_artifacts  # noqa: E402
import validate_prompts  # noqa: E402
import validate_stage_output  # noqa: E402


POLICY_DIR = REPO_ROOT / ".agent" / "policies"
POLICY_PATH = POLICY_DIR / "local-read-only-adapter.json"


EXPECTED_POLICY: dict[str, Any] = {
    "version": 1,
    "adapter": "local-read-only-command",
    "mode": "command-wrapper",
    "command_timeout_seconds": 300,
    "max_stdout_bytes": 20000,
    "max_stderr_bytes": 4000,
    "require_external_bundle": True,
    "require_external_response": True,
    "require_absent_response": True,
    "require_clean_worktree_before": True,
    "require_clean_worktree_after": True,
    "safety": {
        "mutates_run": False,
        "applies_response": False,
        "authorizes": False,
        "network_authorized": False,
        "publication_authorized": False,
    },
    "bindings": [
        ".agent/adapters/local_read_only.py",
        ".agent/policies/local-read-only-adapter.json",
        ".agent/checks/build_stage_context.py",
        ".agent/checks/validate_stage_output.py",
        ".agent/policies/stage-context.json",
        ".agent/policies/stage-output.json",
        ".agent/policies/artifact-contract.json",
        ".agent/policies/prompt-contract.json",
        ".agent/policies/diff-policy.json",
    ],
}


def load_adapter_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    policy = json.loads(path.read_text(encoding="utf-8"))
    if policy != EXPECTED_POLICY:
        raise ValueError("Local read-only adapter policy does not match")
    return policy


def load_policies() -> dict[str, Any]:
    artifact = validate_artifacts.load_contract(POLICY_DIR / "artifact-contract.json")
    prompt = validate_prompts.load_prompt_contract(POLICY_DIR / "prompt-contract.json", artifact)
    context = build_stage_context.load_context_policy(
        POLICY_DIR / "stage-context.json",
        prompt,
        artifact,
    )
    return {
        "artifact": artifact,
        "prompt": prompt,
        "context": context,
        "output": validate_stage_output.load_output_policy(
            POLICY_DIR / "stage-output.json",
            context,
            prompt,
            artifact,
        ),
        "diff": diff_policy.load_policy(POLICY_DIR / "diff-policy.json"),
        "adapter": load_adapter_policy(),
    }


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def repo_status(repo: Path) -> bytes:
    return diff_policy.run_git_with_environment(
        repo,
        {"GIT_OPTIONAL_LOCKS": "0"},
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
    )


def write_exclusive(path: Path, content: bytes) -> None:
    with path.open("xb") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())


def envelope(result: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    return {
        "adapter_contract_version": policy["version"],
        "adapter": policy["adapter"],
        "mode": "read-only",
        "command_invoked": result.get("command_invoked", False),
        "run_mutated": False,
        "response_applied": False,
        "authorized": False,
        "network_authorized": False,
        "publication_authorized": False,
        "result": result,
    }


def bounded_stderr(stderr: bytes, policy: dict[str, Any]) -> str:
    return stderr[: policy["max_stderr_bytes"]].decode("utf-8", errors="replace")


def run_adapter(
    repo: Path,
    bundle: Path,
    bundle_sha256: str,
    response: Path,
    command: Sequence[str],
    policies: dict[str, Any],
) -> dict[str, Any]:
    policy = policies["adapter"]
    if not command:
        raise ValueError("Local read-only adapter command is required")
    repo_root = Path(
        diff_policy.run_git(repo, "rev-parse", "--show-toplevel").decode("utf-8").strip()
    ).resolve()
    bundle = bundle.resolve()
    response = response.resolve()
    if policy["require_external_bundle"] and build_stage_context.is_within(bundle, repo_root):
        raise ValueError("Bundle must be outside the Git checkout")
    if policy["require_external_response"] and build_stage_context.is_within(response, repo_root):
        raise ValueError("Response output must be outside the Git checkout")
    if policy["require_absent_response"] and response.exists():
        raise ValueError("Response output already exists")
    if bundle.is_symlink() or response.is_symlink():
        raise ValueError("Bundle and response symbolic links are not allowed")
    initial_status = repo_status(repo_root)
    if policy["require_clean_worktree_before"] and initial_status:
        return {
            "produced": False,
            "accepted": False,
            "command_invoked": False,
            "failures": [
                {
                    "rule": "clean_worktree_before",
                    "message": "Repository worktree must be clean before read-only command execution.",
                }
            ],
        }
    bundle_bytes = bundle.read_bytes()
    if sha256_bytes(bundle_bytes) != bundle_sha256:
        return {
            "produced": False,
            "accepted": False,
            "command_invoked": False,
            "failures": [
                {"rule": "bundle_sha256", "message": "Bundle does not match expected digest."}
            ],
        }
    completed: subprocess.CompletedProcess[bytes] | None = None
    timed_out = False
    try:
        env = os.environ.copy()
        env["AGENT_CONTEXT_BUNDLE"] = str(bundle)
        completed = subprocess.run(
            list(command),
            cwd=repo_root,
            input=bundle_bytes,
            capture_output=True,
            check=False,
            timeout=policy["command_timeout_seconds"],
            shell=False,
            env=env,
        )
    except subprocess.TimeoutExpired as error:
        timed_out = True
        completed = subprocess.CompletedProcess(
            list(command),
            returncode=124,
            stdout=error.stdout or b"",
            stderr=error.stderr or b"",
        )
    assert completed is not None
    final_status = repo_status(repo_root)
    if policy["require_clean_worktree_after"] and final_status != initial_status:
        response.unlink(missing_ok=True)
        failures = [
            {
                "rule": "clean_worktree_after",
                "message": "Read-only command changed the repository worktree.",
            }
        ]
        if timed_out or completed.returncode != 0:
            failures.append(
                {
                    "rule": "command_failed",
                    "message": "Read-only command failed or timed out.",
                }
            )
        return {
            "produced": False,
            "accepted": False,
            "command_invoked": True,
            "returncode": completed.returncode,
            "stderr": bounded_stderr(completed.stderr or b"", policy),
            "failures": failures,
        }
    if timed_out or completed.returncode != 0:
        return {
            "produced": False,
            "accepted": False,
            "command_invoked": True,
            "returncode": completed.returncode,
            "stderr": bounded_stderr(completed.stderr or b"", policy),
            "failures": [
                {
                    "rule": "command_failed",
                    "message": "Read-only command failed or timed out.",
                }
            ],
        }
    if len(completed.stdout or b"") > policy["max_stdout_bytes"]:
        return {
            "produced": False,
            "accepted": False,
            "command_invoked": True,
            "failures": [
                {"rule": "max_stdout_bytes", "message": "Read-only command output is too large."}
            ],
        }
    write_exclusive(response, completed.stdout or b"")
    validation = validate_stage_output.validate_output(
        bundle,
        bundle_sha256,
        response,
        repo_root,
        policies,
        REPO_ROOT / ".agent" / "prompts",
    )
    return {
        "produced": True,
        "accepted": validation["accepted"],
        "command_invoked": True,
        "response": str(response),
        "response_sha256": sha256_bytes(response.read_bytes()),
        "validation": validation,
        "failures": validation["failures"],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--bundle-sha256", required=True)
    parser.add_argument("--response", type=Path, required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    command = args.command
    if command and command[0] == "--":
        command = command[1:]
    elif command and command[0].startswith("--"):
        print(
            "local-read-only: ERROR\n- adapter command options must follow --",
            file=sys.stderr,
        )
        return 1
    try:
        policies = load_policies()
        result = envelope(
            run_adapter(args.repo, args.bundle, args.bundle_sha256, args.response, command, policies),
            policies["adapter"],
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        print(f"local-read-only: ERROR\n- {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["result"].get("accepted") else 2


if __name__ == "__main__":
    raise SystemExit(main())
