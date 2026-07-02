#!/usr/bin/env python3
"""Validate one exact implementation patch post-validation receipt."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import build_stage_context
import classify_patch_risk
import diff_policy
import generate_complete_patch
import initialize_portable_run
import validate_implementation_patch
import validate_implementation_result


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = (
    REPO_ROOT
    / ".agent"
    / "policies"
    / "implementation-patch-post-validation-validation.json"
)
SHA256 = re.compile(r"[0-9a-f]{64}")
FALSE_FIELDS = validate_implementation_result.FALSE_FIELDS

EXPECTED_POLICY: dict[str, Any] = {
    "version": 1,
    "purpose": "implementation_patch_post_validation_receipt_validation",
    "mode": "validation-only",
    "max_patch_bytes": 10000000,
    "max_receipt_bytes": 250000,
    "require_external_result": True,
    "require_external_expected_session": True,
    "require_external_patch": True,
    "require_external_receipt": True,
    "require_inputs_outside_workspace": True,
    "require_distinct_inputs": True,
    "require_retained_patch": True,
    "require_candidate_ready_result": True,
    "require_canonical_receipt": True,
    "trusted_receipt_bindings": validate_implementation_patch.EXPECTED_POLICY[
        "bindings"
    ],
    "validator_bindings": [
        ".agent/checks/validate_implementation_patch_receipt.py",
        ".agent/policies/implementation-patch-post-validation-validation.json",
    ],
}


def load_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    policy = json.loads(path.read_text(encoding="utf-8"))
    if policy != EXPECTED_POLICY:
        raise ValueError(
            "Implementation patch receipt validation policy does not match"
        )
    return policy


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


def base_result(expected_sha256: str) -> dict[str, Any]:
    return {
        "valid": False,
        "post_validation_complete": False,
        "patch_candidate_ready": False,
        **{field: False for field in FALSE_FIELDS},
        "receipt_sha256": expected_sha256,
        "implementation_result_valid": False,
        "patch_policy_allowed": False,
        "risk": None,
        "route": None,
        "quality_gate": {
            "required": True,
            "completed": False,
            "passed": False,
        },
        "failures": [],
    }


def validate_input_path(
    path: Path,
    source_checkout: Path,
    workspace: Path,
    require_external: bool,
    require_outside_workspace: bool,
    label: str,
) -> Path:
    if path.is_symlink():
        raise ValueError(f"{label} symbolic links are not allowed")
    path = path.resolve()
    if "\n" in str(path) or "\r" in str(path):
        raise ValueError(f"{label} path must not contain line breaks")
    if not path.is_file():
        raise ValueError(f"{label} must be an existing regular file")
    if require_external and build_stage_context.is_within(path, source_checkout):
        raise ValueError(f"{label} must be outside the source checkout")
    if require_outside_workspace and build_stage_context.is_within(path, workspace):
        raise ValueError(f"{label} must be outside the implementation workspace")
    return path


def current_patch_record(
    workspace: Path,
    base_commit: str,
    patch: Path,
    patch_bytes: bytes,
) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        patch_text = patch_bytes.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("Implementation patch is not valid UTF-8") from error
    repo_root, resolved_base, expected_paths = diff_policy.collect_worktree_paths(
        workspace,
        base_commit,
    )
    policy_result = diff_policy.evaluate_patch(
        patch_text,
        diff_policy.load_policy(validate_implementation_patch.DIFF_POLICY_PATH),
        expected_paths,
    )
    contains_secret = any(
        item["rule"] == "high_confidence_secret"
        for item in policy_result["violations"]
    )
    if patch_text.strip() and not diff_policy.parse_patch(patch_text).malformed:
        if not contains_secret:
            policy_result["violations"].extend(
                diff_policy.verify_patch_content(repo_root, resolved_base, patch)
            )
    policy_result["allowed"] = not policy_result["violations"]
    generated = {
        **policy_result,
        "artifact": {
            "patch": str(patch),
            "retained": True,
            "sha256": validate_implementation_result.sha256_bytes(patch_bytes),
            "size_bytes": len(patch_bytes),
        },
        "worktree": {
            "repo": str(repo_root),
            "base_commit": resolved_base,
            "unchanged_after_generation": True,
        },
    }
    risk = classify_patch_risk.classify(
        generated,
        classify_patch_risk.load_risk_policy(
            validate_implementation_patch.RISK_POLICY_PATH
        ),
    )
    return validate_implementation_patch.compact_patch_record(generated), risk


def validate_receipt_value(
    value: Any,
    expected_session: dict[str, Any],
    result_validation: dict[str, Any],
    patch_record: dict[str, Any],
    risk: dict[str, Any],
    policy: dict[str, Any],
) -> list[dict[str, str]]:
    expected_fields = {
        "post_validation_version",
        "purpose",
        "mode",
        *FALSE_FIELDS,
        "post_validation_complete",
        "patch_candidate_ready",
        "identity",
        "implementation_result",
        "patch",
        "risk",
        "quality_gate",
        "bindings",
    }
    if not isinstance(value, dict) or set(value) != expected_fields:
        return [failure("receipt_schema", "Post-validation receipt fields do not match.")]
    failures: list[dict[str, str]] = []
    producer = validate_implementation_patch.EXPECTED_POLICY
    if (
        type(value["post_validation_version"]) is not int
        or value["post_validation_version"] != producer["version"]
        or value["purpose"] != producer["purpose"]
        or value["mode"] != producer["mode"]
        or any(value[field] is not False for field in FALSE_FIELDS)
        or value["post_validation_complete"] is not True
    ):
        failures.append(
            failure("receipt_metadata", "Post-validation receipt metadata does not match.")
        )
    expected_identity = {
        field: expected_session[field]
        for field in sorted(validate_implementation_result.SESSION_FIELDS)
    }
    expected_result = {
        "status": result_validation["status"],
        "sha256": result_validation["result_sha256"],
        "size_bytes": result_validation["result_size_bytes"],
        "valid": result_validation["valid"],
        "candidate_ready": result_validation["implementation_candidate_ready"],
    }
    if not exact_equal(value["identity"], expected_identity):
        failures.append(
            failure("session_identity", "Receipt session identity does not match.")
        )
    if not exact_equal(value["implementation_result"], expected_result):
        failures.append(
            failure(
                "implementation_result",
                "Receipt implementation-result record does not match current evidence.",
            )
        )
    if not exact_equal(value["patch"], patch_record):
        failures.append(
            failure("patch_record", "Receipt patch record does not match current evidence.")
        )
    if not exact_equal(value["risk"], risk):
        failures.append(
            failure("risk_record", "Receipt risk record does not match current evidence.")
        )
    expected_quality_gate = {
        "required": producer["quality_gate_execution_required"],
        "completed": False,
        "passed": False,
    }
    if not exact_equal(value["quality_gate"], expected_quality_gate):
        failures.append(
            failure("quality_gate", "Receipt quality-gate state does not match.")
        )
    expected_candidate = (
        result_validation["implementation_candidate_ready"] is True
        and (
            patch_record["nonempty"] is True
            or not producer["require_nonempty_patch_for_candidate"]
        )
        and patch_record["retained"] is True
        and patch_record["policy_allowed"] is True
    )
    if value["patch_candidate_ready"] is not expected_candidate:
        failures.append(
            failure(
                "patch_candidate_ready",
                "Receipt candidate state does not match deterministic evidence.",
            )
        )
    trusted_bindings = initialize_portable_run.binding_records(
        policy["trusted_receipt_bindings"]
    )
    if not exact_equal(value["bindings"], trusted_bindings):
        failures.append(
            failure(
                "trusted_binding_mismatch",
                "Receipt bindings differ from current trusted bytes.",
            )
        )
    return failures


def validate(
    source_checkout: Path,
    result_path: Path,
    expected_session_path: Path,
    patch: Path,
    receipt: Path,
    expected_receipt_sha256: str,
    policy: dict[str, Any],
) -> dict[str, Any]:
    result = base_result(expected_receipt_sha256)
    if SHA256.fullmatch(expected_receipt_sha256) is None:
        raise ValueError(
            "Expected receipt SHA-256 must be 64 lowercase hexadecimal characters"
        )
    if source_checkout.is_symlink() or expected_session_path.is_symlink():
        raise ValueError("Source checkout and expected-session symlinks are not allowed")
    source_root = Path(
        diff_policy.run_git(source_checkout, "rev-parse", "--show-toplevel")
        .decode("utf-8")
        .strip()
    ).resolve()
    expected_session_bytes = expected_session_path.read_bytes()
    expected_session = validate_implementation_result.validate_expected_session(
        json.loads(expected_session_bytes.decode("utf-8-sig"))
    )
    workspace = Path(expected_session["workspace"]).resolve()
    paths = [
        validate_input_path(
            result_path,
            source_root,
            workspace,
            policy["require_external_result"],
            policy["require_inputs_outside_workspace"],
            "Implementation result",
        ),
        validate_input_path(
            expected_session_path,
            source_root,
            workspace,
            policy["require_external_expected_session"],
            policy["require_inputs_outside_workspace"],
            "Expected session",
        ),
        validate_input_path(
            patch,
            source_root,
            workspace,
            policy["require_external_patch"],
            policy["require_inputs_outside_workspace"],
            "Implementation patch",
        ),
        validate_input_path(
            receipt,
            source_root,
            workspace,
            policy["require_external_receipt"],
            policy["require_inputs_outside_workspace"],
            "Post-validation receipt",
        ),
    ]
    result_path, expected_session_path, patch, receipt = paths
    if policy["require_distinct_inputs"] and len(set(paths)) != len(paths):
        raise ValueError("Validation inputs must use distinct paths")

    workspace_before = generate_complete_patch.repository_snapshot(workspace)
    result_bytes = result_path.read_bytes()
    patch_bytes = patch.read_bytes()
    receipt_bytes = receipt.read_bytes()
    if len(patch_bytes) > policy["max_patch_bytes"]:
        result["failures"].append(
            failure("max_patch_bytes", "Implementation patch exceeds byte limit.")
        )
        return result
    if len(receipt_bytes) > policy["max_receipt_bytes"]:
        result["failures"].append(
            failure("max_receipt_bytes", "Post-validation receipt exceeds byte limit.")
        )
        return result
    if validate_implementation_result.sha256_bytes(receipt_bytes) != expected_receipt_sha256:
        result["failures"].append(
            failure("receipt_sha256", "Receipt does not match its expected SHA-256.")
        )
        return result
    value = json.loads(receipt_bytes.decode("utf-8"))
    if (
        policy["require_canonical_receipt"]
        and receipt_bytes != validate_implementation_patch.canonical_bytes(value)
    ):
        result["failures"].append(
            failure("canonical_receipt", "Receipt is not canonical JSON.")
        )
        return result
    result_validation = validate_implementation_result.validate_execution(
        validate_implementation_patch.captured_execution(result_bytes, b""),
        expected_session,
        validate_implementation_result.load_policy(),
        diff_policy.load_policy(validate_implementation_patch.DIFF_POLICY_PATH),
    )
    result["implementation_result_valid"] = result_validation["valid"]
    if (
        policy["require_candidate_ready_result"]
        and result_validation["implementation_candidate_ready"] is not True
    ):
        result["failures"].append(
            failure(
                "implementation_result",
                "Receipt validation requires a candidate-ready implementation result.",
            )
        )
    patch_record, risk = current_patch_record(
        workspace,
        expected_session["base_commit"],
        patch,
        patch_bytes,
    )
    if policy["require_retained_patch"] and patch_record["retained"] is not True:
        result["failures"].append(
            failure("retained_patch", "Receipt validation requires a retained patch.")
        )
    result.update(
        patch_policy_allowed=patch_record["policy_allowed"],
        risk=risk["risk"],
        route=risk["route"],
    )
    result["failures"].extend(
        validate_receipt_value(
            value,
            expected_session,
            result_validation,
            patch_record,
            risk,
            policy,
        )
    )
    if isinstance(value, dict):
        result.update(
            post_validation_complete=value.get("post_validation_complete") is True,
            patch_candidate_ready=value.get("patch_candidate_ready") is True,
        )
    if result["failures"]:
        return result

    validator_bindings = initialize_portable_run.binding_records(
        policy["validator_bindings"]
    )
    refreshed_bindings = initialize_portable_run.binding_records(
        policy["validator_bindings"]
    )
    if (
        result_path.read_bytes() != result_bytes
        or expected_session_path.read_bytes() != expected_session_bytes
        or patch.read_bytes() != patch_bytes
        or receipt.read_bytes() != receipt_bytes
        or generate_complete_patch.repository_snapshot(workspace) != workspace_before
        or not exact_equal(refreshed_bindings, validator_bindings)
    ):
        result["failures"].append(
            failure(
                "state_changed",
                "Result, session, patch, receipt, workspace, or validator changed.",
            )
        )
        return result
    result.update(valid=True, validator_bindings=validator_bindings)
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--expected-session", type=Path, required=True)
    parser.add_argument("--patch", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--receipt-sha256", required=True)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def format_text(result: dict[str, Any]) -> str:
    status = "VALID" if result["valid"] else "INVALID"
    lines = [
        f"implementation-patch-receipt-validation: {status}",
        f"patch_candidate_ready={str(result['patch_candidate_ready']).lower()}",
        "implementation_quality_gate_execution=false",
        "publication_authorized=false",
    ]
    lines.extend(f"- {item['rule']}: {item['message']}" for item in result["failures"])
    return "\n".join(lines)


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = validate(
            args.repo,
            args.result,
            args.expected_session,
            args.patch,
            args.receipt,
            args.receipt_sha256,
            load_policy(),
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        print(f"implementation-patch-receipt-validation: ERROR\n- {error}", file=sys.stderr)
        return 1
    if args.format == "json":
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(format_text(result))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
