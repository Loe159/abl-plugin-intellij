#!/usr/bin/env python3
"""Validate one exact initialized portable run without approving or authorizing it."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

import build_stage_context
import check_stage_readiness
import diff_policy
import initialize_portable_run
import validate_artifacts


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / ".agent" / "policies" / "portable-run-initialization-validation.json"
SHA256 = re.compile(r"[0-9a-f]{64}")
FALSE_FIELDS = initialize_portable_run.FALSE_FIELDS

EXPECTED_POLICY: dict[str, Any] = {
    "version": 1,
    "purpose": "portable_run_initialization_validation",
    "mode": "validation-only",
    "require_external_run": True,
    "require_external_receipt": True,
    "require_receipt_outside_run": True,
    "require_clean_worktree": True,
    "require_repo_head_match": True,
    "validator_bindings": [
        ".agent/checks/validate_portable_run_initialization.py",
        ".agent/policies/portable-run-initialization-validation.json",
    ],
}


def load_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    policy = json.loads(path.read_text(encoding="utf-8"))
    if policy != EXPECTED_POLICY:
        raise ValueError(
            "Portable-run initialization-validation policy does not match the contract"
        )
    return policy


def load_policies() -> dict[str, Any]:
    return {
        **initialize_portable_run.load_policies(),
        "validation": load_policy(),
    }


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def failure(rule: str, message: str) -> dict[str, str]:
    return {"rule": rule, "message": message}


def base_result(expected_sha256: str) -> dict[str, Any]:
    return {
        "valid": False,
        **{field: False for field in FALSE_FIELDS},
        "run_initialized": False,
        "task_approved": False,
        "research_ready": False,
        "receipt_sha256": expected_sha256,
        "input_sha256": None,
        "issue": None,
        "risk": None,
        "base_commit": None,
        "run_snapshot_sha256": None,
        "failures": [],
    }


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


def run_snapshot_sha256(run: Path, artifact_names: list[str]) -> str:
    snapshot = b"".join(
        name.encode("utf-8")
        + b"\0"
        + sha256_bytes((run / name).read_bytes()).encode("ascii")
        + b"\n"
        for name in sorted(artifact_names)
    )
    return sha256_bytes(snapshot)


def validate_receipt_value(
    value: Any,
    run: Path,
    artifacts: dict[str, validate_artifacts.Artifact],
    policies: dict[str, Any],
) -> list[dict[str, str]]:
    failures: list[dict[str, str]] = []
    expected_fields = {
        "initialization_receipt_version",
        "purpose",
        "mode",
        *FALSE_FIELDS,
        "run_initialized",
        "task_approved",
        "research_ready",
        "source",
        "issue",
        "risk",
        "base_commit",
        "input_sha256",
        "run",
        "manifest",
        "bindings",
    }
    if not isinstance(value, dict) or set(value) != expected_fields:
        return [failure("receipt_schema", "Initialization receipt fields do not match.")]
    initialization = policies["initialization"]
    if (
        type(value["initialization_receipt_version"]) is not int
        or value["initialization_receipt_version"] != initialization["version"]
        or value["purpose"] != initialization["purpose"]
        or value["mode"] != initialization["mode"]
        or value["run_initialized"] is not True
        or value["task_approved"] is not False
        or value["research_ready"] is not False
        or any(value[field] is not False for field in FALSE_FIELDS)
    ):
        failures.append(failure("receipt_metadata", "Initialization receipt state does not match."))
    source = value["source"]
    if (
        not isinstance(source, dict)
        or set(source) != {"kind", "reference"}
        or source["kind"] != initialization["source_kind"]
        or type(source["reference"]) is not str
        or not source["reference"].strip()
        or len(source["reference"]) > initialization["max_source_reference_characters"]
    ):
        failures.append(failure("receipt_source", "Initialization receipt source does not match."))
    task = artifacts["task.md"].frontmatter
    if (
        value["issue"] != int(task["issue"])
        or value["risk"] != task["risk"]
        or value["base_commit"] != task["base_commit"]
        or value["run"] != str(run)
        or type(value["input_sha256"]) is not str
        or SHA256.fullmatch(value["input_sha256"]) is None
    ):
        failures.append(failure("receipt_identity", "Receipt identity does not match the run."))
    artifact_names = list(policies["artifact"]["artifacts"])
    manifest = initialize_portable_run.manifest(run, artifact_names)
    if (
        not exact_equal(value["manifest"], manifest)
        or {record["name"]: record["status"] for record in manifest}
        != initialization["initial_statuses"]
    ):
        failures.append(failure("receipt_manifest", "Receipt manifest does not match initial run."))
    trusted_bindings = initialize_portable_run.binding_records(initialization["bindings"])
    if not exact_equal(value["bindings"], trusted_bindings):
        failures.append(
            failure("trusted_binding_mismatch", "Receipt bindings differ from trusted bytes.")
        )
    return failures


def validate(
    repo: Path,
    run: Path,
    receipt: Path,
    expected_sha256: str,
    policies: dict[str, Any],
) -> dict[str, Any]:
    result = base_result(expected_sha256)
    if SHA256.fullmatch(expected_sha256) is None:
        raise ValueError("Expected receipt SHA-256 must be 64 lowercase hexadecimal characters")
    if repo.is_symlink() or run.is_symlink() or receipt.is_symlink():
        raise ValueError("Repository, run, and receipt symbolic links are not allowed")
    repo_root = Path(
        diff_policy.run_git(repo, "rev-parse", "--show-toplevel").decode("utf-8").strip()
    ).resolve()
    run = run.resolve()
    receipt = receipt.resolve()
    policy = policies["validation"]
    if not run.is_dir() or not receipt.is_file():
        raise ValueError("Run and initialization receipt must exist")
    if policy["require_external_run"] and build_stage_context.is_within(run, repo_root):
        raise ValueError("Portable run must be outside the Git checkout")
    if policy["require_external_receipt"] and build_stage_context.is_within(receipt, repo_root):
        raise ValueError("Initialization receipt must be outside the Git checkout")
    if policy["require_receipt_outside_run"] and build_stage_context.is_within(receipt, run):
        raise ValueError("Initialization receipt must be outside the portable run")
    artifact_names = list(policies["artifact"]["artifacts"])
    if any((run / name).is_symlink() for name in artifact_names):
        raise ValueError("Run artifact symbolic links are not allowed")
    contract = validate_artifacts.validate_directory(run, policies["artifact"], False)
    if not contract["valid"]:
        result["failures"].append(failure("run_contract", "Run does not satisfy the contract."))
        return result
    receipt_bytes = receipt.read_bytes()
    if len(receipt_bytes) > policies["initialization"]["max_receipt_bytes"]:
        result["failures"].append(failure("max_receipt_bytes", "Receipt exceeds the byte limit."))
        return result
    if sha256_bytes(receipt_bytes) != expected_sha256:
        result["failures"].append(
            failure("receipt_sha256", "Receipt does not match its expected SHA-256.")
        )
        return result
    artifacts = {name: validate_artifacts.parse_artifact(run / name) for name in artifact_names}
    value = json.loads(receipt_bytes.decode("utf-8-sig"))
    result["failures"].extend(validate_receipt_value(value, run, artifacts, policies))
    if not isinstance(value, dict):
        return result
    result.update(
        run_initialized=value.get("run_initialized") is True,
        input_sha256=value.get("input_sha256"),
        issue=int(artifacts["task.md"].frontmatter["issue"]),
        risk=artifacts["task.md"].frontmatter["risk"],
        base_commit=artifacts["task.md"].frontmatter["base_commit"],
        run_snapshot_sha256=run_snapshot_sha256(run, artifact_names),
    )
    readiness = check_stage_readiness.check_readiness(
        run,
        "research",
        policies["artifact"],
        policies["readiness"],
    )
    if readiness["ready"]:
        result["failures"].append(
            failure("unexpected_readiness", "Initial run unexpectedly reports research ready.")
        )
    secrets = build_stage_context.detect_secrets(
        [
            build_stage_context.content_record(name, (run / name).read_text(encoding="utf-8-sig"))
            for name in artifact_names
        ],
        policies["diff"],
    )
    if secrets:
        result["failures"].append(
            failure("high_confidence_secret", "Run contains a high-confidence secret signature.")
        )
    head = diff_policy.run_git(repo_root, "rev-parse", "HEAD").decode("ascii").strip()
    status = diff_policy.run_git_with_environment(
        repo_root,
        {"GIT_OPTIONAL_LOCKS": "0"},
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
    )
    if policy["require_repo_head_match"] and head != result["base_commit"]:
        result["failures"].append(failure("repo_head_match", "Repository HEAD differs from base."))
    if policy["require_clean_worktree"] and status:
        result["failures"].append(failure("clean_worktree", "Repository worktree must be clean."))
    if result["failures"]:
        return result
    validator_bindings = initialize_portable_run.binding_records(policy["validator_bindings"])
    refreshed_bindings = initialize_portable_run.binding_records(policy["validator_bindings"])
    if (
        receipt.read_bytes() != receipt_bytes
        or run_snapshot_sha256(run, artifact_names) != result["run_snapshot_sha256"]
        or diff_policy.run_git(repo_root, "rev-parse", "HEAD").decode("ascii").strip() != head
        or diff_policy.run_git_with_environment(
            repo_root,
            {"GIT_OPTIONAL_LOCKS": "0"},
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
        )
        != status
        or not exact_equal(refreshed_bindings, validator_bindings)
    ):
        result["failures"].append(
            failure("state_changed", "Receipt, run, repository, or validator changed.")
        )
        return result
    result.update(valid=True, validator_bindings=validator_bindings)
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--receipt-sha256", required=True)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def format_text(result: dict[str, Any]) -> str:
    status = "VALID" if result["valid"] else "INVALID"
    lines = [
        f"portable-run-initialization-validation: {status}",
        "task_approved=false",
        "research_ready=false",
        "authorized=false",
    ]
    lines.extend(f"- {item['rule']}: {item['message']}" for item in result["failures"])
    return "\n".join(lines)


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = validate(
            args.repo,
            args.run,
            args.receipt,
            args.receipt_sha256,
            load_policies(),
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        print(f"portable-run-initialization-validation: ERROR\n- {error}", file=sys.stderr)
        return 1
    if args.format == "json":
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(format_text(result))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
