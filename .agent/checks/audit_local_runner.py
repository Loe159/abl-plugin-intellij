#!/usr/bin/env python3
"""Audit local runner metadata without invoking an agent or selecting a runner."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / ".agent" / "policies" / "local-runner-audit.json"
FALSE_FIELDS = (
    "authorized",
    "agent_invocation_authorized",
    "implementation_authorized",
    "runner_selected",
    "session_start_authorized",
)

EXPECTED_POLICY: dict[str, Any] = {
    "version": 1,
    "purpose": "local_runner_capability_audit",
    "mode": "metadata-only",
    "max_probe_seconds": 5,
    "max_output_bytes": 120000,
    "probes": [
        {"id": "codex_version", "command": ["codex", "--version"], "markers": ["codex-cli"]},
        {
            "id": "codex_help",
            "command": ["codex", "--help"],
            "markers": ["--ask-for-approval"],
        },
        {
            "id": "codex_exec_help",
            "command": ["codex", "exec", "--help"],
            "markers": [
                "Run Codex non-interactively",
                "--sandbox",
                "--ephemeral",
                "--ignore-user-config",
                "--output-schema",
                "--json",
                "--output-last-message",
            ],
        },
        {
            "id": "codex_sandbox_help",
            "command": ["codex", "sandbox", "--help"],
            "markers": [
                "Run commands within a Codex-provided sandbox",
                "--permissions-profile",
            ],
        },
        {"id": "git_version", "command": ["git", "--version"], "markers": ["git version"]},
        {
            "id": "git_worktree_list",
            "command": [
                "git",
                "-c",
                "safe.directory={repo}",
                "-C",
                "{repo}",
                "worktree",
                "list",
                "--porcelain",
            ],
            "markers": ["worktree ", "HEAD "],
        },
        {"id": "wsl_status", "command": ["wsl", "--status"], "markers": []},
        {
            "id": "docker_version",
            "command": ["docker", "--version"],
            "markers": ["Docker version"],
        },
        {
            "id": "podman_version",
            "command": ["podman", "--version"],
            "markers": ["podman version"],
        },
    ],
    "metadata_assessments": [
        {"id": "codex_cli_metadata", "probe": "codex_version", "required_markers": ["codex-cli"]},
        {
            "id": "codex_global_approval_metadata",
            "probe": "codex_help",
            "required_markers": ["--ask-for-approval"],
        },
        {
            "id": "codex_noninteractive_exec_metadata",
            "probe": "codex_exec_help",
            "required_markers": [
                "Run Codex non-interactively",
                "--sandbox",
                "--ephemeral",
                "--ignore-user-config",
                "--output-schema",
                "--json",
                "--output-last-message",
            ],
        },
        {
            "id": "codex_sandbox_metadata",
            "probe": "codex_sandbox_help",
            "required_markers": [
                "Run commands within a Codex-provided sandbox",
                "--permissions-profile",
            ],
        },
        {"id": "git_cli_metadata", "probe": "git_version", "required_markers": ["git version"]},
        {
            "id": "git_worktree_metadata",
            "probe": "git_worktree_list",
            "required_markers": ["worktree ", "HEAD "],
        },
        {"id": "wsl_status_metadata", "probe": "wsl_status", "required_markers": []},
        {
            "id": "docker_cli_metadata",
            "probe": "docker_version",
            "required_markers": ["Docker version"],
        },
        {
            "id": "podman_cli_metadata",
            "probe": "podman_version",
            "required_markers": ["podman version"],
        },
    ],
    "unproven_enforcement_controls": [
        "credential_isolation",
        "disposable_worktree_lifecycle",
        "filesystem_write_scope",
        "model_turn_budget",
        "network_isolation",
        "bounded_output_capture",
        "authorization_consumption_to_process_start",
        "implementation_result_contract_validation",
        "runner_enforced_output_post_validation",
        "implementation_patch_post_validation",
        "implementation_patch_receipt_validation",
        "implementation_quality_gate_execution",
        "quality_gate_receipt_validation",
        "tool_allowlist",
        "wall_clock_timeout",
    ],
}


def load_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    policy = json.loads(path.read_text(encoding="utf-8"))
    if policy != EXPECTED_POLICY:
        raise ValueError("Local-runner audit policy does not match the bounded metadata-only contract")
    return policy


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def empty_probe_record(probe: dict[str, Any], status: str) -> dict[str, Any]:
    return {
        "id": probe["id"],
        "status": status,
        "returncode": None,
        "timed_out": status == "timeout",
        "stdout_bytes": None,
        "stderr_bytes": None,
        "stdout_sha256": None,
        "stderr_sha256": None,
        "markers": {marker: False for marker in probe["markers"]},
    }


def expand_command(command: list[str], repo: Path) -> list[str]:
    return [part.replace("{repo}", repo.as_posix()) for part in command]


def run_probe(
    probe: dict[str, Any],
    repo: Path,
    policy: dict[str, Any],
    which: Callable[[str], str | None] = shutil.which,
    runner: Callable[..., subprocess.CompletedProcess[bytes]] = subprocess.run,
) -> dict[str, Any]:
    command = expand_command(probe["command"], repo)
    executable = which(command[0])
    if executable is None:
        return empty_probe_record(probe, "missing")
    command[0] = executable
    try:
        completed = runner(
            command,
            cwd=repo,
            check=False,
            capture_output=True,
            timeout=policy["max_probe_seconds"],
        )
    except subprocess.TimeoutExpired:
        return empty_probe_record(probe, "timeout")
    except OSError:
        return empty_probe_record(probe, "error")

    stdout = completed.stdout if isinstance(completed.stdout, bytes) else completed.stdout.encode()
    stderr = completed.stderr if isinstance(completed.stderr, bytes) else completed.stderr.encode()
    total_bytes = len(stdout) + len(stderr)
    if total_bytes > policy["max_output_bytes"]:
        status = "output_limit"
        markers = {marker: False for marker in probe["markers"]}
    else:
        status = "success" if completed.returncode == 0 else "nonzero"
        combined = stdout + b"\n" + stderr
        markers = {marker: marker.encode("utf-8") in combined for marker in probe["markers"]}
    return {
        "id": probe["id"],
        "status": status,
        "returncode": completed.returncode,
        "timed_out": False,
        "stdout_bytes": len(stdout),
        "stderr_bytes": len(stderr),
        "stdout_sha256": sha256_bytes(stdout),
        "stderr_sha256": sha256_bytes(stderr),
        "markers": markers,
    }


def assess_metadata(policy: dict[str, Any], probes: list[dict[str, Any]]) -> list[dict[str, str]]:
    by_id = {probe["id"]: probe for probe in probes}
    assessments = []
    for rule in policy["metadata_assessments"]:
        probe = by_id[rule["probe"]]
        observed = probe["status"] == "success" and all(
            probe["markers"][marker] for marker in rule["required_markers"]
        )
        assessments.append(
            {
                "id": rule["id"],
                "assessment": "observed_metadata" if observed else "not_observed",
                "evidence_probe": rule["probe"],
            }
        )
    return assessments


def audit(
    repo: Path,
    policy: dict[str, Any],
    which: Callable[[str], str | None] = shutil.which,
    runner: Callable[..., subprocess.CompletedProcess[bytes]] = subprocess.run,
) -> dict[str, Any]:
    repo = repo.resolve()
    if not repo.is_dir():
        raise ValueError("Repository path must be an existing directory")
    probes = [run_probe(probe, repo, policy, which, runner) for probe in policy["probes"]]
    return {
        "audit_version": policy["version"],
        "purpose": policy["purpose"],
        "mode": policy["mode"],
        **{field: False for field in FALSE_FIELDS},
        "audit_complete": True,
        "platform": {
            "system": platform.system(),
            "machine": platform.machine(),
            "python_version": platform.python_version(),
        },
        "probes": probes,
        "metadata_assessments": assess_metadata(policy, probes),
        "enforcement_assessments": [
            {"id": control, "assessment": "not_proven"}
            for control in policy["unproven_enforcement_controls"]
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def format_text(result: dict[str, Any]) -> str:
    observed = sum(
        item["assessment"] == "observed_metadata" for item in result["metadata_assessments"]
    )
    lines = [
        f"local-runner-audit: COMPLETE observed_metadata={observed}",
        "runner_selected=false",
        "agent_invocation_authorized=false",
    ]
    lines.extend(
        f"- {item['id']}: {item['assessment']}" for item in result["enforcement_assessments"]
    )
    return "\n".join(lines)


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = audit(args.repo, load_policy())
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        print(f"local-runner-audit: ERROR\n- {error}", file=sys.stderr)
        return 1
    if args.format == "json":
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(format_text(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
