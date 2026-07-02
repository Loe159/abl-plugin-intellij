#!/usr/bin/env python3
"""Validate one supervised implementation runner final receipt."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import initialize_portable_run
import validate_implementation_result


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / ".agent" / "policies" / "supervised-runner-receipt-validation.json"
SHA256 = validate_implementation_result.SHA256
FALSE_FIELDS = (
    "authorized",
    "publication_authorized",
    "network_authorized",
    "merge_authorized",
)

EXPECTED_POLICY: dict[str, Any] = {
    "version": 1,
    "purpose": "supervised_runner_final_receipt_validation",
    "mode": "validation-only",
    "max_receipt_bytes": 200000,
    "required_runner_bindings": [
        ".agent/checks/run_supervised_implementation.py",
        ".agent/policies/supervised-implementation-runner.json",
    ],
    "validator_bindings": [
        ".agent/checks/validate_supervised_runner_receipt.py",
        ".agent/policies/supervised-runner-receipt-validation.json",
    ],
}


def load_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    policy = json.loads(path.read_text(encoding="utf-8"))
    if policy != EXPECTED_POLICY:
        raise ValueError("Supervised-runner receipt validation policy does not match")
    return policy


def failure(rule: str, message: str) -> dict[str, str]:
    return {"rule": rule, "message": message}


def base_result(receipt_sha256: str) -> dict[str, Any]:
    return {
        "valid": False,
        "receipt_sha256": receipt_sha256,
        **{field: False for field in FALSE_FIELDS},
        "runner_complete": False,
        "stage": None,
        "failures": [],
    }


def read_receipt(path: Path, expected_sha256: str, max_bytes: int) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise ValueError("Final runner receipt must be an existing regular file")
    if SHA256.fullmatch(expected_sha256) is None:
        raise ValueError("Expected receipt SHA-256 must be 64 lowercase hexadecimal characters")
    content = path.read_bytes()
    if len(content) > max_bytes:
        raise ValueError("Final runner receipt exceeds max_receipt_bytes")
    if validate_implementation_result.sha256_bytes(content) != expected_sha256:
        raise ValueError("Final runner receipt SHA-256 does not match")
    return content


def validate_bindings(value: Any, policy: dict[str, Any]) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return [failure("bindings", "Final receipt bindings must be a list.")]
    names: list[str] = []
    for record in value:
        if set(record) != {"name", "sha256", "size_bytes"}:
            return [failure("bindings", "Final receipt binding fields do not match.")]
        if (
            not isinstance(record["name"], str)
            or not isinstance(record["sha256"], str)
            or SHA256.fullmatch(record["sha256"]) is None
            or not isinstance(record["size_bytes"], int)
            or isinstance(record["size_bytes"], bool)
            or record["size_bytes"] < 1
        ):
            return [failure("bindings", "Final receipt binding values are invalid.")]
        names.append(record["name"])
    required = policy["required_runner_bindings"]
    if any(name not in names for name in required):
        return [failure("bindings", "Final receipt is missing required runner bindings.")]
    trusted = initialize_portable_run.binding_records(names)
    if trusted != value:
        return [failure("binding_mismatch", "Final receipt bindings differ from current bytes.")]
    return []


def validate_artifacts(value: Any) -> list[dict[str, str]]:
    failures: list[dict[str, str]] = []
    if not isinstance(value, dict):
        return [failure("artifacts", "Final receipt artifacts must be a mapping.")]
    for name, record in value.items():
        if not isinstance(name, str) or not name:
            failures.append(failure("artifact_name", "Artifact names must be non-empty strings."))
            continue
        if not isinstance(record, dict) or set(record) != {"path", "sha256"}:
            failures.append(failure("artifact_record", f"Artifact {name} fields do not match."))
            continue
        artifact_path = record["path"]
        artifact_sha256 = record["sha256"]
        if (
            not isinstance(artifact_path, str)
            or not artifact_path
            or not isinstance(artifact_sha256, str)
            or SHA256.fullmatch(artifact_sha256) is None
        ):
            failures.append(failure("artifact_record", f"Artifact {name} values are invalid."))
            continue
        path = Path(artifact_path)
        if path.is_symlink() or not path.is_file():
            failures.append(failure("artifact_current_state", f"Artifact {name} is not a file."))
            continue
        if validate_implementation_result.sha256_bytes(path.read_bytes()) != artifact_sha256:
            failures.append(failure("artifact_sha256", f"Artifact {name} SHA-256 differs."))
    return failures


def validate_receipt_value(value: Any, policy: dict[str, Any]) -> tuple[list[dict[str, str]], dict[str, Any]]:
    failures: list[dict[str, str]] = []
    facts: dict[str, Any] = {"runner_complete": False, "stage": None}
    expected_fields = {
        "runner_receipt_version",
        "purpose",
        "mode",
        *FALSE_FIELDS,
        "runner_complete",
        "stage",
        "identity",
        "authorization_consumed",
        "launch_ready",
        "adapter_executed",
        "implementation_result_valid",
        "implementation_candidate_ready",
        "patch_post_validation_complete",
        "patch_candidate_ready",
        "quality_gate_executed",
        "quality_gate_passed",
        "quality_gate_receipt_valid",
        "network_requested",
        "publication_requested",
        "cleanup_performed",
        "cleanup_receipt_valid",
        "cleanup_required",
        "authorization_consumption_to_process_start_atomic",
        "cross_host_replay_prevention_enforced",
        "provider_credential_descendant_noninheritance_proven",
        "artifacts",
        "failures",
        "bindings",
    }
    if not isinstance(value, dict) or set(value) != expected_fields:
        return [failure("receipt_schema", "Final receipt fields do not match.")], facts
    facts["runner_complete"] = value["runner_complete"]
    facts["stage"] = value["stage"]
    if (
        type(value["runner_receipt_version"]) is not int
        or value["runner_receipt_version"] != 1
        or value["purpose"] != "supervised_local_implementation_runner"
        or value["mode"] != "bounded-local-orchestration"
        or any(value[field] is not False for field in FALSE_FIELDS)
    ):
        failures.append(failure("receipt_metadata", "Final receipt metadata does not match."))
    bool_fields = expected_fields - {
        "runner_receipt_version",
        "purpose",
        "mode",
        *FALSE_FIELDS,
        "stage",
        "identity",
        "artifacts",
        "failures",
        "bindings",
    }
    for field in bool_fields:
        if type(value[field]) is not bool:
            failures.append(failure("receipt_bool", f"{field} must be a boolean."))
    if not isinstance(value["stage"], str) or not value["stage"]:
        failures.append(failure("stage", "Final receipt stage must be a non-empty string."))
    if value["identity"] is not None and not isinstance(value["identity"], dict):
        failures.append(failure("identity", "Final receipt identity must be null or a mapping."))
    if not isinstance(value["failures"], list) or not all(
        isinstance(item, dict) and "rule" in item and "message" in item
        for item in value["failures"]
    ):
        failures.append(failure("failures", "Final receipt failures must contain rule/message records."))
    if value["runner_complete"] is True and value["stage"] != "complete":
        failures.append(failure("complete_stage", "A complete runner receipt must use stage=complete."))
    if value["runner_complete"] is False and value["stage"] == "complete":
        failures.append(failure("blocked_stage", "A blocked runner receipt must not use stage=complete."))
    if value["runner_complete"] is True and value["quality_gate_receipt_valid"] is not True:
        failures.append(failure("quality_gate_receipt", "Complete runner receipt requires valid quality gate receipt."))
    if value["cleanup_performed"] is True and value["cleanup_receipt_valid"] is not True:
        failures.append(failure("cleanup_receipt", "Performed cleanup requires a valid cleanup receipt."))
    if value["cleanup_performed"] is True and value["cleanup_required"] is True:
        failures.append(failure("cleanup_required", "Performed cleanup cannot leave cleanup_required=true."))
    failures.extend(validate_artifacts(value["artifacts"]))
    failures.extend(validate_bindings(value["bindings"], policy))
    return failures, facts


def validate(receipt: Path, receipt_sha256: str, policy: dict[str, Any]) -> dict[str, Any]:
    result = base_result(receipt_sha256)
    content = read_receipt(receipt, receipt_sha256, policy["max_receipt_bytes"])
    value = json.loads(content.decode("utf-8-sig"))
    failures, facts = validate_receipt_value(value, policy)
    result.update(facts)
    result["failures"].extend(failures)
    if result["failures"]:
        return result
    validator_bindings = initialize_portable_run.binding_records(policy["validator_bindings"])
    if receipt.read_bytes() != content:
        result["failures"].append(failure("state_changed", "Final receipt changed during validation."))
        return result
    result.update(valid=True, validator_bindings=validator_bindings)
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--receipt-sha256", required=True)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def format_text(result: dict[str, Any]) -> str:
    status = "VALID" if result["valid"] else "INVALID"
    lines = [
        f"supervised-runner-receipt-validation: {status}",
        *[f"{field}=false" for field in FALSE_FIELDS],
    ]
    lines.extend(f"- {item['rule']}: {item['message']}" for item in result["failures"])
    return "\n".join(lines)


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = validate(args.receipt, args.receipt_sha256, load_policy())
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        print(f"supervised-runner-receipt-validation: ERROR\n- {error}", file=sys.stderr)
        return 1
    if args.format == "json":
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(format_text(result))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
