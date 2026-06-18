#!/usr/bin/env python3
"""Remove one exact disposable worktree after explicit path confirmation."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Callable

import prepare_disposable_worktree
import validate_disposable_worktree


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / ".agent" / "policies" / "disposable-worktree-cleanup.json"
FALSE_FIELDS = prepare_disposable_worktree.FALSE_FIELDS

EXPECTED_POLICY: dict[str, Any] = {
    "version": 1,
    "purpose": "disposable_implementation_worktree_cleanup",
    "mode": "destructive-cleanup-only",
    "command_timeout_seconds": 15,
    "max_receipt_bytes": 20000,
    "require_external_workspace": True,
    "require_external_preparation_receipt": True,
    "require_preparation_receipt_outside_workspace": True,
    "require_external_cleanup_receipt": True,
    "require_cleanup_receipt_outside_workspace": True,
    "require_absent_cleanup_receipt": True,
    "require_exact_workspace_confirmation": True,
    "require_source_clean": True,
    "require_source_head_match": True,
    "require_workspace_registered": True,
    "require_workspace_detached": True,
    "require_workspace_head_match": True,
    "allow_dirty_workspace": True,
    "force_remove_dirty_workspace": True,
    "preserve_preparation_receipt": True,
    "trusted_receipt_bindings": [
        ".agent/checks/prepare_disposable_worktree.py",
        ".agent/policies/disposable-worktree-preparation.json",
    ],
    "cleanup_bindings": [
        ".agent/checks/prepare_disposable_worktree.py",
        ".agent/policies/disposable-worktree-preparation.json",
        ".agent/checks/validate_disposable_worktree.py",
        ".agent/checks/cleanup_disposable_worktree.py",
        ".agent/policies/disposable-worktree-cleanup.json",
    ],
}


def load_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    policy = json.loads(path.read_text(encoding="utf-8"))
    if policy != EXPECTED_POLICY:
        raise ValueError("Disposable-worktree cleanup policy does not match the pilot contract")
    return policy


def failure(rule: str, message: str) -> dict[str, str]:
    return {"rule": rule, "message": message}


def base_result(
    workspace: Path,
    receipt_sha256: str,
    cleanup_receipt: Path,
) -> dict[str, Any]:
    return {
        "cleaned": False,
        **{field: False for field in FALSE_FIELDS},
        "cleanup_confirmed": False,
        "cleanup_attempted": False,
        "cleanup_succeeded": False,
        "discarded_uncommitted_changes": False,
        "workspace": str(workspace),
        "preparation_receipt_sha256": receipt_sha256,
        "cleanup_receipt": str(cleanup_receipt),
        "failures": [],
    }


def worktree_records(output: bytes) -> dict[str, tuple[str, ...]]:
    records: dict[str, tuple[str, ...]] = {}
    for raw_record in output.decode("utf-8").strip().split("\n\n"):
        lines = tuple(raw_record.splitlines())
        if not lines:
            continue
        if not lines[0].startswith("worktree "):
            raise ValueError("Git worktree registration output does not match the contract")
        path = lines[0][len("worktree ") :].replace("\\", "/")
        if path in records:
            raise ValueError("Git worktree registration contains a duplicate path")
        records[path] = lines
    return records


def expected_records_after_removal(
    output: bytes,
    workspace: Path,
    base: str,
) -> dict[str, tuple[str, ...]]:
    records = worktree_records(output)
    workspace_name = str(workspace).replace("\\", "/")
    record = records.get(workspace_name)
    if record is None or f"HEAD {base}" not in record or "detached" not in record:
        raise ValueError("Workspace is not exactly registered as detached at the receipt base")
    del records[workspace_name]
    return records


def write_exclusive(path: Path, content: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())


def cleanup(
    source: Path,
    workspace: Path,
    receipt: Path,
    receipt_sha256: str,
    cleanup_receipt: Path,
    confirm_workspace: str,
    policy: dict[str, Any],
    writer: Callable[[Path, bytes], None] = write_exclusive,
) -> dict[str, Any]:
    if not validate_disposable_worktree.SHA256.fullmatch(receipt_sha256):
        raise ValueError("Expected receipt SHA-256 must be 64 lowercase hexadecimal characters")
    if source.is_symlink() or workspace.is_symlink() or receipt.is_symlink():
        raise ValueError("Source, workspace, and preparation receipt symbolic links are not allowed")
    timeout = policy["command_timeout_seconds"]
    source_root = Path(
        prepare_disposable_worktree.git_output(source, timeout, "rev-parse", "--show-toplevel")
        .decode("utf-8")
        .strip()
    ).resolve()
    workspace = workspace.resolve()
    receipt = receipt.resolve()
    cleanup_receipt = cleanup_receipt.resolve()
    result = base_result(workspace, receipt_sha256, cleanup_receipt)

    if "\n" in confirm_workspace or "\r" in confirm_workspace:
        raise ValueError("Workspace confirmation must not contain line breaks")
    if policy["require_exact_workspace_confirmation"] and confirm_workspace != str(workspace):
        result["failures"].append(
            failure("workspace_confirmation", "Confirmation must equal the canonical workspace path.")
        )
        return result
    result["cleanup_confirmed"] = True
    if not workspace.is_dir():
        raise ValueError("Disposable workspace must be an existing directory")
    if not receipt.is_file():
        raise ValueError("Preparation receipt must be an existing regular file")
    if policy["require_external_workspace"] and prepare_disposable_worktree.is_within(
        workspace,
        source_root,
    ):
        raise ValueError("Disposable workspace must be outside the source checkout")
    if policy["require_external_preparation_receipt"] and prepare_disposable_worktree.is_within(
        receipt,
        source_root,
    ):
        raise ValueError("Preparation receipt must be outside the source checkout")
    if policy[
        "require_preparation_receipt_outside_workspace"
    ] and prepare_disposable_worktree.is_within(receipt, workspace):
        raise ValueError("Preparation receipt must be outside the workspace")
    if policy["require_external_cleanup_receipt"] and prepare_disposable_worktree.is_within(
        cleanup_receipt,
        source_root,
    ):
        raise ValueError("Cleanup receipt must be outside the source checkout")
    if policy["require_cleanup_receipt_outside_workspace"] and prepare_disposable_worktree.is_within(
        cleanup_receipt,
        workspace,
    ):
        raise ValueError("Cleanup receipt must be outside the workspace")
    if policy["require_absent_cleanup_receipt"] and cleanup_receipt.exists():
        raise ValueError("Cleanup receipt already exists")
    if not cleanup_receipt.parent.is_dir():
        raise ValueError("Cleanup receipt parent must be an existing directory")

    receipt_bytes = receipt.read_bytes()
    if len(receipt_bytes) > policy["max_receipt_bytes"]:
        result["failures"].append(failure("max_receipt_bytes", "Preparation receipt is too large."))
        return result
    if validate_disposable_worktree.sha256_bytes(receipt_bytes) != receipt_sha256:
        result["failures"].append(
            failure("receipt_sha256", "Preparation receipt does not match its expected SHA-256.")
        )
        return result
    value = json.loads(receipt_bytes.decode("utf-8-sig"))
    receipt_failures, base = validate_disposable_worktree.validate_receipt_value(
        value,
        source_root,
        workspace,
        {"trusted_receipt_bindings": policy["trusted_receipt_bindings"]},
    )
    result["failures"].extend(receipt_failures)
    if base is None or result["failures"]:
        return result

    source_before = prepare_disposable_worktree.source_snapshot(source_root, timeout)
    workspace_before = prepare_disposable_worktree.workspace_snapshot(workspace, timeout)
    result["discarded_uncommitted_changes"] = workspace_before["status"] != b""
    if policy["require_source_clean"] and source_before["status"]:
        result["failures"].append(failure("source_clean", "Source checkout must be clean."))
    if policy["require_source_head_match"] and source_before["head"].decode("ascii") != base:
        result["failures"].append(failure("source_head_match", "Source HEAD differs from receipt base."))
    if policy["require_workspace_head_match"] and workspace_before["head"].decode("ascii") != base:
        result["failures"].append(
            failure("workspace_head_match", "Workspace HEAD differs from receipt base.")
        )
    if policy["require_workspace_detached"] and not workspace_before["detached"]:
        result["failures"].append(failure("workspace_detached", "Workspace must remain detached."))
    if Path(workspace_before["root"]).resolve() != workspace:
        result["failures"].append(failure("workspace_root", "Workspace root differs from input."))
    try:
        expected_after_records = expected_records_after_removal(
            source_before["worktrees"],
            workspace,
            base,
        )
    except ValueError:
        expected_after_records = {}
        result["failures"].append(
            failure("workspace_registered", "Workspace is not exactly registered as detached.")
        )
    if result["failures"]:
        return result

    cleanup_bindings = validate_disposable_worktree.binding_records(policy["cleanup_bindings"])
    refreshed_source = prepare_disposable_worktree.source_snapshot(source_root, timeout)
    refreshed_workspace = prepare_disposable_worktree.workspace_snapshot(workspace, timeout)
    refreshed_bindings = validate_disposable_worktree.binding_records(policy["cleanup_bindings"])
    if (
        receipt.read_bytes() != receipt_bytes
        or not validate_disposable_worktree.exact_equal(refreshed_source, source_before)
        or not validate_disposable_worktree.exact_equal(refreshed_workspace, workspace_before)
        or not validate_disposable_worktree.exact_equal(refreshed_bindings, cleanup_bindings)
    ):
        result["failures"].append(
            failure("state_changed", "Receipt, source, workspace, or cleanup binding changed.")
        )
        return result

    result["cleanup_attempted"] = True
    prepare_disposable_worktree.run_git(
        source_root,
        timeout,
        "worktree",
        "remove",
        "--force",
        str(workspace),
    )
    result["cleanup_succeeded"] = True
    source_after = prepare_disposable_worktree.source_snapshot(source_root, timeout)
    postconditions = {
        "workspace_absent": not workspace.exists(),
        "workspace_registration_removed": worktree_records(source_after["worktrees"])
        == expected_after_records,
        "source_head_unchanged": source_after["head"] == source_before["head"],
        "source_branches_unchanged": source_after["branches"] == source_before["branches"],
        "source_status_unchanged": source_after["status"] == source_before["status"],
        "preparation_receipt_preserved": receipt.is_file() and receipt.read_bytes() == receipt_bytes,
    }
    if not all(postconditions.values()):
        result["failures"].append(
            failure("cleanup_postconditions", "Cleanup completed but postconditions did not match.")
        )
        return result

    cleanup_value = {
        "cleanup_receipt_version": policy["version"],
        "purpose": policy["purpose"],
        "mode": policy["mode"],
        **{field: False for field in FALSE_FIELDS},
        "cleanup_confirmed": True,
        "cleanup_performed": True,
        "discarded_uncommitted_changes": result["discarded_uncommitted_changes"],
        "source_repo": str(source_root),
        "workspace": str(workspace),
        "base_commit": base,
        "preparation_receipt_sha256": receipt_sha256,
        "postconditions": postconditions,
        "bindings": cleanup_bindings,
    }
    cleanup_bytes = (json.dumps(cleanup_value, indent=2, sort_keys=True) + "\n").encode("utf-8")
    if len(cleanup_bytes) > policy["max_receipt_bytes"]:
        raise ValueError("Cleanup completed but cleanup receipt exceeds max_receipt_bytes")
    try:
        writer(cleanup_receipt, cleanup_bytes)
    except OSError as error:
        raise ValueError("Cleanup succeeded but cleanup receipt writing failed") from error

    final_source = prepare_disposable_worktree.source_snapshot(source_root, timeout)
    final_bindings = validate_disposable_worktree.binding_records(policy["cleanup_bindings"])
    if (
        workspace.exists()
        or receipt.read_bytes() != receipt_bytes
        or cleanup_receipt.read_bytes() != cleanup_bytes
        or not validate_disposable_worktree.exact_equal(final_source, source_after)
        or not validate_disposable_worktree.exact_equal(final_bindings, cleanup_bindings)
    ):
        cleanup_receipt.unlink(missing_ok=True)
        raise ValueError("Cleanup completed but final evidence validation failed")
    result.update(
        cleaned=True,
        cleanup_receipt_sha256=hashlib.sha256(cleanup_bytes).hexdigest(),
        cleanup_receipt_size_bytes=len(cleanup_bytes),
        postconditions=postconditions,
        bindings=cleanup_bindings,
    )
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--receipt-sha256", required=True)
    parser.add_argument("--cleanup-receipt", type=Path, required=True)
    parser.add_argument("--confirm-workspace", required=True)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def format_text(result: dict[str, Any]) -> str:
    status = "CLEANED" if result["cleaned"] else "NOT_CLEANED"
    lines = [
        f"disposable-worktree-cleanup: {status}",
        "workspace_use_authorized=false",
        "agent_invocation_authorized=false",
    ]
    lines.extend(f"- {item['rule']}: {item['message']}" for item in result["failures"])
    return "\n".join(lines)


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = cleanup(
            args.source,
            args.workspace,
            args.receipt,
            args.receipt_sha256,
            args.cleanup_receipt,
            args.confirm_workspace,
            load_policy(),
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        print(f"disposable-worktree-cleanup: ERROR\n- {error}", file=sys.stderr)
        return 1
    if args.format == "json":
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(format_text(result))
    return 0 if result["cleaned"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
