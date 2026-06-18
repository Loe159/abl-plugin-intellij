#!/usr/bin/env python3
"""Prove one disposable Git worktree lifecycle in a temporary synthetic repository."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / ".agent" / "policies" / "disposable-worktree-proof.json"
FALSE_FIELDS = (
    "authorized",
    "agent_invocation_authorized",
    "implementation_authorized",
    "runner_selected",
    "session_start_authorized",
)

EXPECTED_POLICY: dict[str, Any] = {
    "version": 1,
    "purpose": "disposable_git_worktree_lifecycle_proof",
    "mode": "fixture-only",
    "command_timeout_seconds": 10,
    "fixture": {
        "base_file": "README.md",
        "base_content": "base\n",
        "dirty_content": "dirty worktree\n",
        "untracked_file": "untracked.txt",
        "untracked_content": "temporary\n",
    },
    "proven_control": "disposable_git_worktree_lifecycle_fixture",
    "unproven_controls": [
        "concurrent_worktree_lifecycle",
        "implementation_runner_disposable_worktree_lifecycle",
        "worktree_cleanup_after_host_crash",
    ],
}


def load_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    policy = json.loads(path.read_text(encoding="utf-8"))
    if policy != EXPECTED_POLICY:
        raise ValueError("Disposable-worktree proof policy does not match the fixture-only contract")
    return policy


def run_git(
    git_path: str,
    repo: Path,
    timeout: int,
    *args: str,
    runner: Callable[..., subprocess.CompletedProcess[bytes]] = subprocess.run,
) -> bytes:
    completed = runner(
        [
            git_path,
            "-c",
            f"safe.directory={repo.as_posix()}",
            "-C",
            str(repo),
            *args,
        ],
        check=False,
        capture_output=True,
        timeout=timeout,
        shell=False,
    )
    if completed.returncode != 0:
        raise ValueError("Git fixture command failed")
    return completed.stdout


def worktree_count(output: bytes) -> int:
    return sum(line.startswith(b"worktree ") for line in output.splitlines())


def base_observation(observation: str) -> dict[str, Any]:
    return {
        "id": "dirty_detached_worktree_lifecycle",
        "observation": observation,
        "matched": False,
        "exact_base_checkout": False,
        "detached_worktree_created": False,
        "dirty_state_confined": False,
        "forced_removal_succeeded": False,
        "worktree_directory_removed": False,
        "worktree_registration_removed": False,
        "base_head_unchanged": False,
        "base_content_unchanged": False,
        "base_status_clean": False,
    }


def observe_fixture(
    policy: dict[str, Any],
    git_path: str,
    temp_factory: Callable[..., tempfile.TemporaryDirectory[str]] = tempfile.TemporaryDirectory,
    runner: Callable[..., subprocess.CompletedProcess[bytes]] = subprocess.run,
) -> dict[str, Any]:
    observation = base_observation("fixture_error")
    with temp_factory(prefix="abl-worktree-proof-") as temp_dir:
        root = Path(temp_dir)
        base = root / "base"
        worktree = root / "worktree"
        base.mkdir()
        timeout = policy["command_timeout_seconds"]
        fixture = policy["fixture"]
        try:
            run_git(git_path, base, timeout, "init", runner=runner)
            run_git(git_path, base, timeout, "config", "user.email", "proof@example.invalid", runner=runner)
            run_git(git_path, base, timeout, "config", "user.name", "Proof", runner=runner)
            (base / fixture["base_file"]).write_text(fixture["base_content"], encoding="utf-8")
            run_git(git_path, base, timeout, "add", fixture["base_file"], runner=runner)
            run_git(git_path, base, timeout, "commit", "-m", "fixture base", runner=runner)
            base_head = run_git(git_path, base, timeout, "rev-parse", "HEAD", runner=runner).strip()
            base_branches = run_git(
                git_path,
                base,
                timeout,
                "for-each-ref",
                "--format=%(refname)",
                "refs/heads",
                runner=runner,
            )
            base_status = run_git(
                git_path,
                base,
                timeout,
                "status",
                "--porcelain=v1",
                "--untracked-files=all",
                runner=runner,
            )
            observation["exact_base_checkout"] = (
                base_status == b""
                and (base / fixture["base_file"]).read_text(encoding="utf-8")
                == fixture["base_content"]
            )

            run_git(
                git_path,
                base,
                timeout,
                "worktree",
                "add",
                "--detach",
                str(worktree),
                base_head.decode("ascii"),
                runner=runner,
            )
            worktree_head = run_git(
                git_path,
                worktree,
                timeout,
                "rev-parse",
                "HEAD",
                runner=runner,
            ).strip()
            worktree_branches = run_git(
                git_path,
                base,
                timeout,
                "for-each-ref",
                "--format=%(refname)",
                "refs/heads",
                runner=runner,
            )
            registered = run_git(
                git_path,
                base,
                timeout,
                "worktree",
                "list",
                "--porcelain",
                runner=runner,
            )
            observation["detached_worktree_created"] = (
                worktree.is_dir()
                and worktree_head == base_head
                and worktree_branches == base_branches
                and worktree_count(registered) == 2
            )

            (worktree / fixture["base_file"]).write_text(fixture["dirty_content"], encoding="utf-8")
            (worktree / fixture["untracked_file"]).write_text(
                fixture["untracked_content"],
                encoding="utf-8",
            )
            dirty_status = run_git(
                git_path,
                worktree,
                timeout,
                "status",
                "--porcelain=v1",
                "--untracked-files=all",
                runner=runner,
            )
            confined_base_status = run_git(
                git_path,
                base,
                timeout,
                "status",
                "--porcelain=v1",
                "--untracked-files=all",
                runner=runner,
            )
            observation["dirty_state_confined"] = (
                dirty_status != b""
                and confined_base_status == b""
                and (base / fixture["base_file"]).read_text(encoding="utf-8")
                == fixture["base_content"]
            )

            run_git(
                git_path,
                base,
                timeout,
                "worktree",
                "remove",
                "--force",
                str(worktree),
                runner=runner,
            )
            observation["forced_removal_succeeded"] = True
            run_git(
                git_path,
                base,
                timeout,
                "worktree",
                "prune",
                "--expire",
                "now",
                runner=runner,
            )
            final_registered = run_git(
                git_path,
                base,
                timeout,
                "worktree",
                "list",
                "--porcelain",
                runner=runner,
            )
            final_head = run_git(git_path, base, timeout, "rev-parse", "HEAD", runner=runner).strip()
            final_branches = run_git(
                git_path,
                base,
                timeout,
                "for-each-ref",
                "--format=%(refname)",
                "refs/heads",
                runner=runner,
            )
            final_status = run_git(
                git_path,
                base,
                timeout,
                "status",
                "--porcelain=v1",
                "--untracked-files=all",
                runner=runner,
            )
            observation["worktree_directory_removed"] = not worktree.exists()
            observation["worktree_registration_removed"] = worktree_count(final_registered) == 1
            observation["base_head_unchanged"] = final_head == base_head and final_branches == base_branches
            observation["base_content_unchanged"] = (
                (base / fixture["base_file"]).read_text(encoding="utf-8")
                == fixture["base_content"]
            )
            observation["base_status_clean"] = final_status == b""
            observation["matched"] = all(
                observation[field]
                for field in observation
                if field not in {"id", "observation", "matched"}
            )
            observation["observation"] = (
                "dirty_detached_worktree_removed_cleanly"
                if observation["matched"]
                else "lifecycle_invariant_failed"
            )
        except (OSError, UnicodeError, ValueError, subprocess.TimeoutExpired):
            observation["observation"] = "fixture_error"
    return observation


def prove(
    repo: Path,
    policy: dict[str, Any],
    which: Callable[[str], str | None] = shutil.which,
    fixture_runner: Callable[[dict[str, Any], str], dict[str, Any]] = observe_fixture,
) -> dict[str, Any]:
    repo = repo.resolve()
    if not repo.is_dir():
        raise ValueError("Repository path must be an existing directory")
    git_path = which("git")
    observation = (
        fixture_runner(policy, git_path)
        if git_path is not None
        else base_observation("unsupported_environment")
    )
    verified = git_path is not None and observation["matched"]
    return {
        "proof_version": policy["version"],
        "purpose": policy["purpose"],
        "mode": policy["mode"],
        **{field: False for field in FALSE_FIELDS},
        "proof_complete": True,
        "scope": {
            "synthetic_repository_only": True,
            "temporary_directory_only": True,
            "detached_worktree": True,
            "dirty_worktree_force_removal": True,
            "uses_shell": False,
            "invokes_agent": False,
            "writes_input_repository": False,
        },
        "fixture": observation,
        "control_assessments": [
            {
                "id": policy["proven_control"],
                "assessment": "verified_fixture" if verified else "not_proven",
            },
            *[
                {"id": control, "assessment": "not_proven"}
                for control in policy["unproven_controls"]
            ],
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def format_text(result: dict[str, Any]) -> str:
    assessment = result["control_assessments"][0]["assessment"]
    lines = [
        f"disposable-worktree-proof: {assessment.upper()}",
        "runner_selected=false",
        "agent_invocation_authorized=false",
        f"- fixture: {result['fixture']['observation']}",
    ]
    lines.extend(
        f"- {item['id']}: {item['assessment']}" for item in result["control_assessments"][1:]
    )
    return "\n".join(lines)


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = prove(args.repo, load_policy())
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        print(f"disposable-worktree-proof: ERROR\n- {error}", file=sys.stderr)
        return 1
    if args.format == "json":
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(format_text(result))
    return 0 if result["control_assessments"][0]["assessment"] == "verified_fixture" else 2


if __name__ == "__main__":
    raise SystemExit(main())
