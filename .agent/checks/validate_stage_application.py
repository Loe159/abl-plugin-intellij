#!/usr/bin/env python3
"""Validate one exact stage-application receipt without authorizing anything."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import apply_stage_output
import build_stage_context
import diff_policy
import initialize_portable_run
import validate_artifacts


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / ".agent" / "policies" / "stage-application-validation.json"
SHA256 = re.compile(r"[0-9a-f]{64}")

EXPECTED_POLICY: dict[str, Any] = {
    "version": 1,
    "purpose": "stage_application_receipt_validation",
    "mode": "validation-only",
    "require_external_run": True,
    "require_external_application_receipt": True,
    "require_application_receipt_outside_run": True,
    "require_clean_worktree": True,
    "require_repo_head_match": True,
    "validator_bindings": [
        ".agent/checks/validate_stage_application.py",
        ".agent/policies/stage-application-validation.json",
    ],
}


def load_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    policy = json.loads(path.read_text(encoding="utf-8"))
    if policy != EXPECTED_POLICY:
        raise ValueError("Stage-application-validation policy does not match the contract")
    return policy


def load_policies() -> dict[str, Any]:
    return {
        **apply_stage_output.load_policies(),
        "application_validation": load_policy(),
    }


def failure(rule: str, message: str) -> dict[str, str]:
    return {"rule": rule, "message": message}


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


def valid_sha256(value: Any) -> bool:
    return type(value) is str and SHA256.fullmatch(value) is not None


def base_result(expected_sha256: str) -> dict[str, Any]:
    return {
        "valid": False,
        "authorized": False,
        "stage_authorized": False,
        "publication_authorized": False,
        "run_mutated": False,
        "response_applied": False,
        "copy_confirmed": False,
        "application_receipt_sha256": expected_sha256,
        "reviewer_declaration": None,
        "stage": None,
        "artifact": None,
        "status": None,
        "issue": None,
        "risk": None,
        "base_commit": None,
        "bundle_sha256": None,
        "pre_application_run_snapshot_sha256": None,
        "post_application_run_snapshot_sha256": None,
        "response_sha256": None,
        "replaced_sha256": None,
        "failures": [],
    }


def validate_receipt_value(
    value: Any,
    run: Path,
    application_receipt: Path,
    artifacts: dict[str, validate_artifacts.Artifact],
    policies: dict[str, Any],
) -> list[dict[str, str]]:
    failures: list[dict[str, str]] = []
    expected_fields = {
        "stage_application_receipt_version",
        "purpose",
        "mode",
        "authorized",
        "stage_authorized",
        "publication_authorized",
        "run_mutated",
        "response_applied",
        "copy_confirmed",
        "reviewer_declaration",
        "stage",
        "artifact",
        "status",
        "issue",
        "risk",
        "base_commit",
        "run",
        "application_receipt",
        "bundle_sha256",
        "pre_application_run_snapshot_sha256",
        "post_application_run_snapshot_sha256",
        "response_sha256",
        "replaced_sha256",
        "confirmation_sha256",
        "bindings",
    }
    if not isinstance(value, dict) or set(value) != expected_fields:
        return [failure("receipt_schema", "Stage-application receipt fields do not match.")]
    application = policies["application"]
    if (
        type(value["stage_application_receipt_version"]) is not int
        or value["stage_application_receipt_version"] != application["version"]
        or value["purpose"] != application["purpose"]
        or value["mode"] != application["mode"]
        or value["authorized"] is not False
        or value["stage_authorized"] is not False
        or value["publication_authorized"] is not False
        or value["run_mutated"] is not True
        or value["response_applied"] is not True
        or value["copy_confirmed"] is not True
    ):
        failures.append(failure("receipt_metadata", "Stage-application receipt state does not match."))
    reviewer = value["reviewer_declaration"]
    stage = value["stage"]
    artifact = value["artifact"]
    if (
        type(reviewer) is not str
        or not apply_stage_output.REVIEWER.fullmatch(reviewer)
        or len(reviewer) > application["max_reviewer_chars"]
        or stage not in application["stages"]
        or artifact != application["stages"].get(stage, {}).get("target_artifact")
        or artifact not in artifacts
    ):
        failures.append(failure("receipt_identity", "Receipt stage or reviewer identity is invalid."))
        return failures
    task = artifacts["task.md"].frontmatter
    target = artifacts[artifact].frontmatter
    if (
        value["status"] != target["status"]
        or value["issue"] != int(task["issue"])
        or value["risk"] != task["risk"]
        or value["base_commit"] != task["base_commit"]
        or value["run"] != str(run)
        or value["application_receipt"] != str(application_receipt)
        or target["issue"] != task["issue"]
        or target["base_commit"] != task["base_commit"]
    ):
        failures.append(failure("receipt_identity", "Receipt identity does not match the run."))
    digest_fields = (
        "bundle_sha256",
        "pre_application_run_snapshot_sha256",
        "post_application_run_snapshot_sha256",
        "response_sha256",
        "replaced_sha256",
        "confirmation_sha256",
    )
    if any(not valid_sha256(value[field]) for field in digest_fields):
        failures.append(failure("receipt_digest", "Receipt digest fields are not valid SHA-256."))
        return failures
    post_snapshot = apply_stage_output.run_snapshot_sha256(
        run,
        list(policies["artifact"]["artifacts"]),
    )
    target_sha256 = apply_stage_output.sha256_bytes((run / artifact).read_bytes())
    bindings, bindings_sha256 = apply_stage_output.application_bindings(application)
    confirmation = (
        f"{application['confirmation_prefix']} "
        f"stage={stage} artifact={artifact} "
        f"bundle_sha256={value['bundle_sha256']} "
        f"run_snapshot_sha256={value['pre_application_run_snapshot_sha256']} "
        f"post_run_snapshot_sha256={post_snapshot} "
        f"response_sha256={target_sha256} replace_sha256={value['replaced_sha256']} "
        f"application_bindings_sha256={bindings_sha256} "
        f"application_receipt={application_receipt}"
    )
    if (
        value["post_application_run_snapshot_sha256"] != post_snapshot
        or value["response_sha256"] != target_sha256
        or value["confirmation_sha256"]
        != apply_stage_output.sha256_bytes(confirmation.encode("utf-8"))
    ):
        failures.append(
            failure("application_mismatch", "Receipt does not match the current applied run.")
        )
    if not exact_equal(value["bindings"], bindings):
        failures.append(
            failure("trusted_binding_mismatch", "Receipt bindings differ from trusted bytes.")
        )
    return failures


def validate(
    repo: Path,
    run: Path,
    application_receipt: Path,
    expected_sha256: str,
    policies: dict[str, Any],
) -> dict[str, Any]:
    result = base_result(expected_sha256)
    if SHA256.fullmatch(expected_sha256) is None:
        raise ValueError("Expected receipt SHA-256 must be 64 lowercase hexadecimal characters")
    if repo.is_symlink() or run.is_symlink() or application_receipt.is_symlink():
        raise ValueError(
            "Repository, run, and stage-application receipt symbolic links are not allowed"
        )
    repo_root = Path(
        diff_policy.run_git(repo, "rev-parse", "--show-toplevel").decode("utf-8").strip()
    ).resolve()
    run = run.resolve()
    application_receipt = application_receipt.resolve()
    policy = policies["application_validation"]
    if "\n" in str(application_receipt) or "\r" in str(application_receipt):
        raise ValueError("Stage-application receipt path must not contain line breaks")
    if not run.is_dir() or not application_receipt.is_file():
        raise ValueError("Run and stage-application receipt must exist")
    if policy["require_external_run"] and build_stage_context.is_within(run, repo_root):
        raise ValueError("Portable run must be outside the Git checkout")
    if policy["require_external_application_receipt"] and build_stage_context.is_within(
        application_receipt,
        repo_root,
    ):
        raise ValueError("Stage-application receipt must be outside the Git checkout")
    if policy["require_application_receipt_outside_run"] and build_stage_context.is_within(
        application_receipt,
        run,
    ):
        raise ValueError("Stage-application receipt must be outside the portable run")
    artifact_names = list(policies["artifact"]["artifacts"])
    if any((run / name).is_symlink() for name in artifact_names):
        raise ValueError("Run artifact symbolic links are not allowed")
    contract = validate_artifacts.validate_directory(run, policies["artifact"], False)
    if not contract["valid"]:
        result["failures"].append(failure("run_contract", "Run does not satisfy the contract."))
        return result
    receipt_bytes = application_receipt.read_bytes()
    if len(receipt_bytes) > policies["application"]["max_application_receipt_bytes"]:
        result["failures"].append(failure("max_receipt_bytes", "Receipt exceeds the byte limit."))
        return result
    if apply_stage_output.sha256_bytes(receipt_bytes) != expected_sha256:
        result["failures"].append(
            failure("receipt_sha256", "Receipt does not match its expected SHA-256.")
        )
        return result
    artifacts = {name: validate_artifacts.parse_artifact(run / name) for name in artifact_names}
    value = json.loads(receipt_bytes.decode("utf-8-sig"))
    result["failures"].extend(
        validate_receipt_value(value, run, application_receipt, artifacts, policies)
    )
    if not isinstance(value, dict):
        return result
    result.update(
        run_mutated=value.get("run_mutated") is True,
        response_applied=value.get("response_applied") is True,
        copy_confirmed=value.get("copy_confirmed") is True,
        reviewer_declaration=value.get("reviewer_declaration"),
        stage=value.get("stage"),
        artifact=value.get("artifact"),
        status=value.get("status"),
        issue=artifacts["task.md"].frontmatter.get("issue"),
        risk=artifacts["task.md"].frontmatter.get("risk"),
        base_commit=artifacts["task.md"].frontmatter.get("base_commit"),
        bundle_sha256=value.get("bundle_sha256"),
        pre_application_run_snapshot_sha256=value.get("pre_application_run_snapshot_sha256"),
        post_application_run_snapshot_sha256=apply_stage_output.run_snapshot_sha256(
            run,
            artifact_names,
        ),
        response_sha256=(
            apply_stage_output.sha256_bytes((run / value["artifact"]).read_bytes())
            if isinstance(value.get("artifact"), str) and (run / value["artifact"]).is_file()
            else None
        ),
        replaced_sha256=value.get("replaced_sha256"),
    )
    detections = build_stage_context.detect_secrets(
        [
            build_stage_context.content_record(name, (run / name).read_text(encoding="utf-8-sig"))
            for name in artifact_names
        ]
        + [
            build_stage_context.content_record(
                "reviewer",
                str(result["reviewer_declaration"] or ""),
            )
        ],
        policies["diff"],
    )
    if detections:
        result["reviewer_declaration"] = None
        result["failures"].append(
            failure(
                "high_confidence_secret",
                "Run or reviewer declaration contains a high-confidence secret signature.",
            )
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
        application_receipt.read_bytes() != receipt_bytes
        or apply_stage_output.run_snapshot_sha256(run, artifact_names)
        != result["post_application_run_snapshot_sha256"]
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
    parser.add_argument("--application-receipt", type=Path, required=True)
    parser.add_argument("--application-receipt-sha256", required=True)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def format_text(result: dict[str, Any]) -> str:
    status = "VALID" if result["valid"] else "INVALID"
    lines = [
        f"stage-application-validation: {status}",
        f"response_applied={str(result['response_applied']).lower()}",
        f"copy_confirmed={str(result['copy_confirmed']).lower()}",
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
            args.application_receipt,
            args.application_receipt_sha256,
            load_policies(),
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        print(f"stage-application-validation: ERROR\n- {error}", file=sys.stderr)
        return 1
    if args.format == "json":
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(format_text(result))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
