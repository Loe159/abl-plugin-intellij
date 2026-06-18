#!/usr/bin/env python3
"""Validate one exact disposable-worktree cleanup receipt without authorizing anything."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import prepare_disposable_worktree
import validate_disposable_worktree


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / ".agent" / "policies" / "disposable-worktree-cleanup-validation.json"
FALSE_FIELDS = prepare_disposable_worktree.FALSE_FIELDS
POSTCONDITION_FIELDS = (
    "workspace_absent",
    "workspace_registration_removed",
    "source_head_unchanged",
    "source_branches_unchanged",
    "source_status_unchanged",
    "preparation_receipt_preserved",
)

EXPECTED_POLICY: dict[str, Any] = {
    "version": 1,
    "purpose": "disposable_implementation_worktree_cleanup_validation",
    "mode": "validation-only",
    "command_timeout_seconds": 15,
    "max_receipt_bytes": 20000,
    "require_external_workspace": True,
    "require_external_preparation_receipt": True,
    "require_external_cleanup_receipt": True,
    "require_receipts_outside_workspace": True,
    "require_source_clean": True,
    "require_source_head_match": True,
    "require_workspace_absent": True,
    "require_workspace_unregistered": True,
    "trusted_preparation_receipt_bindings": [
        ".agent/checks/prepare_disposable_worktree.py",
        ".agent/policies/disposable-worktree-preparation.json",
    ],
    "trusted_cleanup_receipt_bindings": [
        ".agent/checks/prepare_disposable_worktree.py",
        ".agent/policies/disposable-worktree-preparation.json",
        ".agent/checks/validate_disposable_worktree.py",
        ".agent/checks/cleanup_disposable_worktree.py",
        ".agent/policies/disposable-worktree-cleanup.json",
    ],
    "validator_bindings": [
        ".agent/checks/validate_disposable_worktree_cleanup.py",
        ".agent/policies/disposable-worktree-cleanup-validation.json",
    ],
}


def load_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    policy = json.loads(path.read_text(encoding="utf-8"))
    if policy != EXPECTED_POLICY:
        raise ValueError("Cleanup-receipt validation policy does not match the pilot contract")
    return policy


def failure(rule: str, message: str) -> dict[str, str]:
    return {"rule": rule, "message": message}


def base_result(
    preparation_sha256: str,
    cleanup_sha256: str,
) -> dict[str, Any]:
    return {
        "valid": False,
        **{field: False for field in FALSE_FIELDS},
        "preparation_receipt_sha256": preparation_sha256,
        "cleanup_receipt_sha256": cleanup_sha256,
        "base_commit": None,
        "failures": [],
    }


def read_bounded_receipt(
    path: Path,
    expected_sha256: str,
    max_bytes: int,
    label: str,
) -> tuple[bytes | None, dict[str, str] | None]:
    if not path.is_file():
        raise ValueError(f"{label} receipt must be an existing regular file")
    if path.stat().st_size > max_bytes:
        return None, failure(
            f"{label}_max_receipt_bytes",
            f"{label} receipt exceeds the byte limit.",
        )
    content = path.read_bytes()
    if validate_disposable_worktree.sha256_bytes(content) != expected_sha256:
        return None, failure(f"{label}_receipt_sha256", f"{label} receipt SHA-256 does not match.")
    return content, None


def validate_cleanup_receipt_value(
    value: Any,
    source: Path,
    workspace: Path,
    preparation_sha256: str,
    policy: dict[str, Any],
) -> tuple[list[dict[str, str]], str | None]:
    failures: list[dict[str, str]] = []
    expected_fields = {
        "cleanup_receipt_version",
        "purpose",
        "mode",
        *FALSE_FIELDS,
        "cleanup_confirmed",
        "cleanup_performed",
        "discarded_uncommitted_changes",
        "source_repo",
        "workspace",
        "base_commit",
        "preparation_receipt_sha256",
        "postconditions",
        "bindings",
    }
    if not isinstance(value, dict) or set(value) != expected_fields:
        return [failure("cleanup_receipt_schema", "Cleanup receipt fields do not match.")], None
    if (
        type(value["cleanup_receipt_version"]) is not int
        or value["cleanup_receipt_version"] != 1
        or value["purpose"] != "disposable_implementation_worktree_cleanup"
        or value["mode"] != "destructive-cleanup-only"
        or any(value[field] is not False for field in FALSE_FIELDS)
        or value["cleanup_confirmed"] is not True
        or value["cleanup_performed"] is not True
        or type(value["discarded_uncommitted_changes"]) is not bool
    ):
        failures.append(
            failure("cleanup_receipt_metadata", "Cleanup receipt safety metadata does not match.")
        )
    base = value["base_commit"]
    if (
        type(value["source_repo"]) is not str
        or Path(value["source_repo"]).resolve() != source
        or type(value["workspace"]) is not str
        or Path(value["workspace"]).resolve() != workspace
        or type(base) is not str
        or prepare_disposable_worktree.COMMIT.fullmatch(base) is None
        or value["preparation_receipt_sha256"] != preparation_sha256
    ):
        failures.append(
            failure("cleanup_receipt_identity", "Cleanup receipt identity does not match.")
        )
        base = None
    expected_postconditions = {name: True for name in POSTCONDITION_FIELDS}
    if not validate_disposable_worktree.exact_equal(
        value["postconditions"],
        expected_postconditions,
    ):
        failures.append(
            failure("cleanup_receipt_postconditions", "Cleanup postconditions do not match.")
        )
    names = policy["trusted_cleanup_receipt_bindings"]
    if not validate_disposable_worktree.validate_binding_values(value["bindings"], names):
        failures.append(
            failure("cleanup_receipt_bindings", "Cleanup receipt bindings do not match.")
        )
    elif not validate_disposable_worktree.exact_equal(
        value["bindings"],
        validate_disposable_worktree.binding_records(names),
    ):
        failures.append(
            failure(
                "trusted_cleanup_binding_mismatch",
                "Cleanup bindings differ from trusted bytes.",
            )
        )
    return failures, base


def workspace_registered(output: bytes, workspace: Path) -> bool:
    expected_path = str(workspace).replace("\\", "/")
    for record in output.decode("utf-8").strip().split("\n\n"):
        lines = record.splitlines()
        if lines and lines[0].startswith("worktree "):
            if lines[0][len("worktree ") :].replace("\\", "/") == expected_path:
                return True
    return False


def validate(
    source: Path,
    workspace: Path,
    preparation_receipt: Path,
    preparation_sha256: str,
    cleanup_receipt: Path,
    cleanup_sha256: str,
    policy: dict[str, Any],
) -> dict[str, Any]:
    result = base_result(preparation_sha256, cleanup_sha256)
    if (
        validate_disposable_worktree.SHA256.fullmatch(preparation_sha256) is None
        or validate_disposable_worktree.SHA256.fullmatch(cleanup_sha256) is None
    ):
        raise ValueError("Receipt SHA-256 values must be 64 lowercase hexadecimal characters")
    if (
        source.is_symlink()
        or workspace.is_symlink()
        or preparation_receipt.is_symlink()
        or cleanup_receipt.is_symlink()
    ):
        raise ValueError("Source, workspace, and receipt symbolic links are not allowed")
    timeout = policy["command_timeout_seconds"]
    source_root = Path(
        prepare_disposable_worktree.git_output(source, timeout, "rev-parse", "--show-toplevel")
        .decode("utf-8")
        .strip()
    ).resolve()
    workspace = workspace.resolve()
    preparation_receipt = preparation_receipt.resolve()
    cleanup_receipt = cleanup_receipt.resolve()
    if policy["require_external_workspace"] and prepare_disposable_worktree.is_within(
        workspace,
        source_root,
    ):
        raise ValueError("Disposable workspace path must be outside the source checkout")
    for path, label in (
        (preparation_receipt, "Preparation"),
        (cleanup_receipt, "Cleanup"),
    ):
        if prepare_disposable_worktree.is_within(path, source_root):
            raise ValueError(f"{label} receipt must be outside the source checkout")
        if policy["require_receipts_outside_workspace"] and prepare_disposable_worktree.is_within(
            path,
            workspace,
        ):
            raise ValueError(f"{label} receipt must be outside the workspace")

    preparation_bytes, preparation_failure = read_bounded_receipt(
        preparation_receipt,
        preparation_sha256,
        policy["max_receipt_bytes"],
        "preparation",
    )
    if preparation_failure is not None:
        result["failures"].append(preparation_failure)
        return result
    cleanup_bytes, cleanup_failure = read_bounded_receipt(
        cleanup_receipt,
        cleanup_sha256,
        policy["max_receipt_bytes"],
        "cleanup",
    )
    if cleanup_failure is not None:
        result["failures"].append(cleanup_failure)
        return result
    assert preparation_bytes is not None
    assert cleanup_bytes is not None

    preparation_value = json.loads(preparation_bytes.decode("utf-8-sig"))
    preparation_failures, preparation_base = validate_disposable_worktree.validate_receipt_value(
        preparation_value,
        source_root,
        workspace,
        {"trusted_receipt_bindings": policy["trusted_preparation_receipt_bindings"]},
    )
    result["failures"].extend(preparation_failures)
    cleanup_value = json.loads(cleanup_bytes.decode("utf-8-sig"))
    cleanup_failures, cleanup_base = validate_cleanup_receipt_value(
        cleanup_value,
        source_root,
        workspace,
        preparation_sha256,
        policy,
    )
    result["failures"].extend(cleanup_failures)
    if preparation_base is None or cleanup_base is None or preparation_base != cleanup_base:
        if preparation_base is not None and cleanup_base is not None:
            result["failures"].append(
                failure("receipt_base_match", "Preparation and cleanup receipt bases differ.")
            )
        return result
    result["base_commit"] = preparation_base

    source_before = prepare_disposable_worktree.source_snapshot(source_root, timeout)
    if policy["require_source_clean"] and source_before["status"]:
        result["failures"].append(failure("source_clean", "Source checkout must be clean."))
    if (
        policy["require_source_head_match"]
        and source_before["head"].decode("ascii") != preparation_base
    ):
        result["failures"].append(
            failure("source_head_match", "Source HEAD differs from receipt base.")
        )
    if policy["require_workspace_absent"] and workspace.exists():
        result["failures"].append(failure("workspace_absent", "Workspace path must remain absent."))
    if policy["require_workspace_unregistered"] and workspace_registered(
        source_before["worktrees"],
        workspace,
    ):
        result["failures"].append(
            failure(
                "workspace_unregistered",
                "Workspace must remain absent from Git registrations.",
            )
        )
    if result["failures"]:
        return result

    validator_bindings = validate_disposable_worktree.binding_records(policy["validator_bindings"])
    source_after = prepare_disposable_worktree.source_snapshot(source_root, timeout)
    refreshed_bindings = validate_disposable_worktree.binding_records(policy["validator_bindings"])
    if (
        preparation_receipt.read_bytes() != preparation_bytes
        or cleanup_receipt.read_bytes() != cleanup_bytes
        or workspace.exists()
        or workspace_registered(source_after["worktrees"], workspace)
        or not validate_disposable_worktree.exact_equal(source_after, source_before)
        or not validate_disposable_worktree.exact_equal(refreshed_bindings, validator_bindings)
    ):
        result["failures"].append(
            failure("state_changed", "Receipt, source, workspace, or validator changed.")
        )
        return result
    result.update(valid=True, validator_bindings=validator_bindings)
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--preparation-receipt", type=Path, required=True)
    parser.add_argument("--preparation-receipt-sha256", required=True)
    parser.add_argument("--cleanup-receipt", type=Path, required=True)
    parser.add_argument("--cleanup-receipt-sha256", required=True)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def format_text(result: dict[str, Any]) -> str:
    status = "VALID" if result["valid"] else "INVALID"
    lines = [
        f"disposable-worktree-cleanup-validation: {status}",
        "workspace_use_authorized=false",
        "agent_invocation_authorized=false",
    ]
    lines.extend(f"- {item['rule']}: {item['message']}" for item in result["failures"])
    return "\n".join(lines)


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = validate(
            args.source,
            args.workspace,
            args.preparation_receipt,
            args.preparation_receipt_sha256,
            args.cleanup_receipt,
            args.cleanup_receipt_sha256,
            load_policy(),
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        print(f"disposable-worktree-cleanup-validation: ERROR\n- {error}", file=sys.stderr)
        return 1
    if args.format == "json":
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(format_text(result))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
