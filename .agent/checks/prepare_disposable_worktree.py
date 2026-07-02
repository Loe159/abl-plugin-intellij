#!/usr/bin/env python3
"""Prepare one detached disposable Git worktree without authorizing its use."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / ".agent" / "policies" / "disposable-worktree-preparation.json"
COMMIT = re.compile(r"[0-9a-f]{40}")
FALSE_FIELDS = (
    "authorized",
    "agent_invocation_authorized",
    "implementation_authorized",
    "runner_selected",
    "session_start_authorized",
    "workspace_use_authorized",
)

EXPECTED_POLICY: dict[str, Any] = {
    "version": 1,
    "purpose": "disposable_implementation_worktree_preparation",
    "mode": "preparation-only",
    "command_timeout_seconds": 15,
    "max_receipt_bytes": 20000,
    "require_exact_base_commit": True,
    "require_source_head_match": True,
    "require_source_clean": True,
    "require_external_target": True,
    "require_absent_target": True,
    "require_external_receipt": True,
    "require_receipt_outside_target": True,
    "require_absent_receipt": True,
    "require_detached_workspace": True,
    "require_clean_workspace": True,
    "rollback_on_failure": True,
}


def load_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    policy = json.loads(path.read_text(encoding="utf-8"))
    if policy != EXPECTED_POLICY:
        raise ValueError("Disposable-worktree preparation policy does not match the pilot contract")
    return policy


def is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def run_git(
    repo: Path,
    timeout: int,
    *arguments: str,
    allowed_returncodes: tuple[int, ...] = (0,),
    runner: Callable[..., subprocess.CompletedProcess[bytes]] = subprocess.run,
) -> tuple[int, bytes]:
    environment = os.environ.copy()
    environment["GIT_OPTIONAL_LOCKS"] = "0"
    completed = runner(
        [
            "git",
            "-c",
            f"safe.directory={repo.resolve().as_posix()}",
            "-c",
            "core.fsmonitor=false",
            "-C",
            str(repo),
            *arguments,
        ],
        check=False,
        capture_output=True,
        env=environment,
        timeout=timeout,
        shell=False,
    )
    if completed.returncode not in allowed_returncodes:
        raise ValueError("Git worktree preparation command failed")
    return completed.returncode, completed.stdout


def git_output(repo: Path, timeout: int, *arguments: str) -> bytes:
    return run_git(repo, timeout, *arguments)[1]


def source_snapshot(repo: Path, timeout: int) -> dict[str, bytes]:
    return {
        "head": git_output(repo, timeout, "rev-parse", "HEAD").strip(),
        "branches": git_output(
            repo,
            timeout,
            "for-each-ref",
            "--format=%(refname)%00%(objectname)",
            "refs/heads",
        ),
        "status": git_output(
            repo,
            timeout,
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
        ),
        "worktrees": git_output(repo, timeout, "worktree", "list", "--porcelain"),
    }


def worktree_count(output: bytes) -> int:
    return sum(line.startswith(b"worktree ") for line in output.splitlines())


def workspace_snapshot(workspace: Path, timeout: int) -> dict[str, Any]:
    symbolic_returncode, _ = run_git(
        workspace,
        timeout,
        "symbolic-ref",
        "--quiet",
        "HEAD",
        allowed_returncodes=(0, 1),
    )
    return {
        "head": git_output(workspace, timeout, "rev-parse", "HEAD").strip(),
        "status": git_output(
            workspace,
            timeout,
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
        ),
        "detached": symbolic_returncode == 1,
        "root": git_output(workspace, timeout, "rev-parse", "--show-toplevel")
        .decode("utf-8")
        .strip(),
    }


def write_exclusive(path: Path, content: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())


def binding_record(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ValueError("Preparation binding must be an existing regular file")
    content = path.read_bytes()
    return {
        "name": path.relative_to(REPO_ROOT).as_posix(),
        "sha256": hashlib.sha256(content).hexdigest(),
        "size_bytes": len(content),
    }


def rollback(repo: Path, target: Path, timeout: int) -> bool:
    try:
        run_git(repo, timeout, "worktree", "remove", "--force", str(target))
        run_git(repo, timeout, "worktree", "prune", "--expire", "now")
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return False
    return not target.exists()


def base_result(base: str, target: Path, receipt: Path) -> dict[str, Any]:
    return {
        "prepared": False,
        **{field: False for field in FALSE_FIELDS},
        "base_commit": base,
        "workspace": str(target),
        "receipt": str(receipt),
        "cleanup_required": False,
        "source_git_metadata_changed": False,
        "rollback_attempted": False,
        "rollback_succeeded": False,
        "failures": [],
    }


def failure(rule: str, message: str) -> dict[str, str]:
    return {"rule": rule, "message": message}


def prepare(
    repo: Path,
    base: str,
    target: Path,
    receipt: Path,
    policy: dict[str, Any],
    writer: Callable[[Path, bytes], None] = write_exclusive,
) -> dict[str, Any]:
    if not COMMIT.fullmatch(base):
        raise ValueError("Base commit must be exactly 40 lowercase hexadecimal characters")
    timeout = policy["command_timeout_seconds"]
    repo_root = Path(
        git_output(repo, timeout, "rev-parse", "--show-toplevel").decode("utf-8").strip()
    ).resolve()
    target = target.resolve()
    receipt = receipt.resolve()
    result = base_result(base, target, receipt)

    if "\n" in str(target) or "\r" in str(target) or "\n" in str(receipt) or "\r" in str(receipt):
        raise ValueError("Target and receipt paths must not contain line breaks")
    if policy["require_external_target"] and is_within(target, repo_root):
        raise ValueError("Disposable worktree target must be outside the source checkout")
    if policy["require_absent_target"] and target.exists():
        raise ValueError("Disposable worktree target already exists")
    if not target.parent.is_dir():
        raise ValueError("Disposable worktree target parent must be an existing directory")
    if policy["require_external_receipt"] and is_within(receipt, repo_root):
        raise ValueError("Disposable worktree receipt must be outside the source checkout")
    if policy["require_receipt_outside_target"] and is_within(receipt, target):
        raise ValueError("Disposable worktree receipt must be outside the target")
    if policy["require_absent_receipt"] and receipt.exists():
        raise ValueError("Disposable worktree receipt already exists")
    if not receipt.parent.is_dir():
        raise ValueError("Disposable worktree receipt parent must be an existing directory")

    verified_base = git_output(repo_root, timeout, "rev-parse", "--verify", f"{base}^{{commit}}")
    if policy["require_exact_base_commit"] and verified_base.decode("ascii").strip() != base:
        raise ValueError("Base commit does not resolve to the exact requested commit")
    before = source_snapshot(repo_root, timeout)
    bindings = [
        binding_record(Path(__file__).resolve()),
        binding_record(POLICY_PATH),
    ]
    if policy["require_source_head_match"] and before["head"].decode("ascii") != base:
        result["failures"].append(
            failure("source_head_match", "Source checkout HEAD differs from the requested base.")
        )
    if policy["require_source_clean"] and before["status"]:
        result["failures"].append(
            failure("source_clean", "Source checkout must be clean before preparation.")
        )
    if result["failures"]:
        return result

    created = False
    try:
        run_git(repo_root, timeout, "worktree", "add", "--detach", str(target), base)
        created = True
        result["source_git_metadata_changed"] = True
        result["cleanup_required"] = True
        workspace = workspace_snapshot(target, timeout)
        after = source_snapshot(repo_root, timeout)
        invariants = {
            "workspace_head_matches_base": workspace["head"].decode("ascii") == base,
            "workspace_detached": workspace["detached"],
            "workspace_clean": workspace["status"] == b"",
            "workspace_root_matches_target": Path(workspace["root"]).resolve() == target,
            "source_head_unchanged": after["head"] == before["head"],
            "source_branches_unchanged": after["branches"] == before["branches"],
            "source_status_unchanged": after["status"] == before["status"],
            "worktree_registration_added": worktree_count(after["worktrees"])
            == worktree_count(before["worktrees"]) + 1,
        }
        if not all(invariants.values()):
            raise ValueError("Prepared worktree does not satisfy the required invariants")
        receipt_value = {
            "receipt_version": policy["version"],
            "purpose": policy["purpose"],
            "mode": policy["mode"],
            **{field: False for field in FALSE_FIELDS},
            "workspace_prepared": True,
            "cleanup_required": True,
            "source_git_metadata_changed": True,
            "source_repo": str(repo_root),
            "workspace": str(target),
            "base_commit": base,
            "invariants": invariants,
            "bindings": bindings,
        }
        receipt_bytes = (json.dumps(receipt_value, indent=2, sort_keys=True) + "\n").encode("utf-8")
        if len(receipt_bytes) > policy["max_receipt_bytes"]:
            raise ValueError("Disposable-worktree receipt exceeds max_receipt_bytes")
        writer(receipt, receipt_bytes)

        final_source = source_snapshot(repo_root, timeout)
        final_workspace = workspace_snapshot(target, timeout)
        if (
            final_source["head"] != before["head"]
            or final_source["branches"] != before["branches"]
            or final_source["status"] != before["status"]
            or worktree_count(final_source["worktrees"]) != worktree_count(before["worktrees"]) + 1
            or final_workspace["head"].decode("ascii") != base
            or final_workspace["status"] != b""
            or not final_workspace["detached"]
        ):
            raise ValueError("Repository or worktree state changed while writing the receipt")
        result.update(
            prepared=True,
            receipt_sha256=hashlib.sha256(receipt_bytes).hexdigest(),
            receipt_size_bytes=len(receipt_bytes),
            invariants=invariants,
        )
        return result
    except (OSError, UnicodeError, ValueError, subprocess.TimeoutExpired) as error:
        receipt.unlink(missing_ok=True)
        if created and policy["rollback_on_failure"]:
            result["rollback_attempted"] = True
            result["rollback_succeeded"] = rollback(repo_root, target, timeout)
            if result["rollback_succeeded"]:
                result["cleanup_required"] = False
            rollback_status = "succeeded" if result["rollback_succeeded"] else "failed"
            raise ValueError(
                f"Disposable-worktree preparation failed after creation; rollback {rollback_status}"
            ) from error
        raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--base", required=True)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def format_text(result: dict[str, Any]) -> str:
    status = "PREPARED" if result["prepared"] else "NOT_PREPARED"
    lines = [
        f"disposable-worktree-preparation: {status}",
        "workspace_use_authorized=false",
        "agent_invocation_authorized=false",
    ]
    lines.extend(f"- {item['rule']}: {item['message']}" for item in result["failures"])
    return "\n".join(lines)


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = prepare(args.repo, args.base, args.target, args.receipt, load_policy())
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        print(f"disposable-worktree-preparation: ERROR\n- {error}", file=sys.stderr)
        return 1
    if args.format == "json":
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(format_text(result))
    return 0 if result["prepared"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
