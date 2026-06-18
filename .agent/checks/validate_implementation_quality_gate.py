#!/usr/bin/env python3
"""Validate one exact implementation quality-gate receipt."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import build_stage_context
import diff_policy
import generate_complete_patch
import initialize_portable_run
import run_implementation_quality_gate
import validate_implementation_patch
import validate_implementation_patch_receipt
import validate_implementation_result


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = (
    REPO_ROOT
    / ".agent"
    / "policies"
    / "implementation-quality-gate-validation.json"
)
SHA256 = re.compile(r"[0-9a-f]{64}")
FALSE_FIELDS = validate_implementation_result.FALSE_FIELDS

EXPECTED_POLICY: dict[str, Any] = {
    "version": 1,
    "purpose": "implementation_quality_gate_receipt_validation",
    "mode": "validation-only",
    "max_receipt_bytes": 100000,
    "require_external_receipt": True,
    "require_receipt_outside_workspace": True,
    "require_canonical_receipt": True,
    "require_valid_patch_receipt": True,
    "require_patch_candidate_ready": True,
    "require_current_gradle_cache": True,
    "trusted_receipt_bindings": run_implementation_quality_gate.EXPECTED_POLICY[
        "bindings"
    ],
    "validator_bindings": [
        ".agent/checks/validate_implementation_quality_gate.py",
        ".agent/policies/implementation-quality-gate-validation.json",
    ],
}


def load_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    policy = json.loads(path.read_text(encoding="utf-8"))
    if policy != EXPECTED_POLICY:
        raise ValueError("Implementation quality-gate validation policy does not match")
    return policy


def failure(rule: str, message: str) -> dict[str, str]:
    return {"rule": rule, "message": message}


def exact_equal(actual: Any, expected: Any) -> bool:
    return validate_implementation_patch_receipt.exact_equal(actual, expected)


def valid_sha256(value: Any) -> bool:
    return type(value) is str and SHA256.fullmatch(value) is not None


def base_result(expected_sha256: str) -> dict[str, Any]:
    return {
        "valid": False,
        "execution_attempted": False,
        "quality_gate_passed": False,
        **{field: False for field in FALSE_FIELDS},
        "receipt_sha256": expected_sha256,
        "patch_candidate_ready": False,
        "commands": [],
        "failures": [],
    }


def validate_receipt_path(
    source_root: Path,
    workspace: Path,
    receipt: Path,
    policy: dict[str, Any],
) -> Path:
    if receipt.is_symlink():
        raise ValueError("Quality-gate receipt symbolic links are not allowed")
    receipt = receipt.resolve()
    if "\n" in str(receipt) or "\r" in str(receipt):
        raise ValueError("Quality-gate receipt path must not contain line breaks")
    if not receipt.is_file():
        raise ValueError("Quality-gate receipt must be an existing regular file")
    if policy["require_external_receipt"] and build_stage_context.is_within(
        receipt,
        source_root,
    ):
        raise ValueError("Quality-gate receipt must be outside the source checkout")
    if policy["require_receipt_outside_workspace"] and build_stage_context.is_within(
        receipt,
        workspace,
    ):
        raise ValueError("Quality-gate receipt must be outside the workspace")
    return receipt


def validate_executed_record(
    value: Any,
    command: dict[str, Any],
    execution_policy: dict[str, Any],
) -> list[dict[str, str]]:
    fields = {
        "id",
        "tasks",
        "status",
        "passed",
        "returncode",
        "timed_out",
        "output_limit_exceeded",
        "tree_kill_requested",
        "tree_kill_returncode",
        "direct_kill_requested",
        "root_reaped",
        "capture_complete",
        "stdout_bytes",
        "stderr_bytes",
        "stdout_sha256",
        "stderr_sha256",
        "duration_seconds",
    }
    if not isinstance(value, dict) or set(value) != fields:
        return [failure("command_schema", "Executed command fields do not match.")]
    failures: list[dict[str, str]] = []
    passed = value["status"] == "passed"
    if (
        value["id"] != command["id"]
        or not exact_equal(value["tasks"], command["tasks"])
        or value["status"] not in {"passed", "failed"}
        or type(value["passed"]) is not bool
        or value["passed"] is not passed
        or (value["returncode"] is not None and type(value["returncode"]) is not int)
        or type(value["timed_out"]) is not bool
        or type(value["output_limit_exceeded"]) is not bool
        or type(value["tree_kill_requested"]) is not bool
        or (
            value["tree_kill_returncode"] is not None
            and type(value["tree_kill_returncode"]) is not int
        )
        or type(value["direct_kill_requested"]) is not bool
        or type(value["root_reaped"]) is not bool
        or type(value["capture_complete"]) is not bool
        or type(value["stdout_bytes"]) is not int
        or value["stdout_bytes"] < 0
        or type(value["stderr_bytes"]) is not int
        or value["stderr_bytes"] < 0
        or (
            value["capture_complete"]
            and (
                not valid_sha256(value["stdout_sha256"])
                or not valid_sha256(value["stderr_sha256"])
            )
        )
        or (
            not value["capture_complete"]
            and (
                value["stdout_sha256"] is not None
                or value["stderr_sha256"] is not None
            )
        )
        or isinstance(value["duration_seconds"], bool)
        or not isinstance(value["duration_seconds"], (int, float))
        or value["duration_seconds"] < 0
        or value["duration_seconds"] > execution_policy["command_timeout_seconds"]
        or value["stdout_bytes"] + value["stderr_bytes"]
        > execution_policy["max_captured_output_bytes"]
    ):
        failures.append(
            failure("command_record", "Executed command record is invalid or out of bounds.")
        )
        return failures
    if passed and (
        value["returncode"] != 0
        or value["timed_out"]
        or value["output_limit_exceeded"]
        or value["tree_kill_requested"]
        or value["tree_kill_returncode"] is not None
        or value["direct_kill_requested"]
        or not value["root_reaped"]
        or not value["capture_complete"]
    ):
        failures.append(
            failure("passed_command", "Passed command runtime state is inconsistent.")
        )
    if not passed and value["returncode"] == 0 and not (
        value["timed_out"]
        or value["output_limit_exceeded"]
        or value["direct_kill_requested"]
        or not value["capture_complete"]
        or not value["root_reaped"]
    ):
        failures.append(
            failure("failed_command", "Failed command has no recorded failure condition.")
        )
    return failures


def validate_not_run_record(
    value: Any,
    command: dict[str, Any],
    expected_reason: str,
) -> list[dict[str, str]]:
    expected = {
        "id": command["id"],
        "tasks": command["tasks"],
        "status": "not_run",
        "passed": False,
        "reason": expected_reason,
    }
    if not exact_equal(value, expected):
        return [failure("not_run_command", "Not-run command record does not match.")]
    return []


def validate_command_sequence(
    commands: Any,
    quality_gate_passed: Any,
    execution_policy: dict[str, Any],
) -> list[dict[str, str]]:
    expected = execution_policy["commands"]
    if not isinstance(commands, list) or len(commands) != len(expected):
        return [failure("commands_schema", "Quality-gate command count does not match.")]
    failures: list[dict[str, str]] = []
    stopped = False
    stop_reason = "previous_failure"
    total_duration = 0.0
    for record, command in zip(commands, expected, strict=True):
        if stopped:
            failures.extend(validate_not_run_record(record, command, stop_reason))
            continue
        if isinstance(record, dict) and record.get("status") == "not_run":
            failures.extend(validate_not_run_record(record, command, "total_timeout"))
            stopped = True
            stop_reason = "previous_failure"
            continue
        record_failures = validate_executed_record(record, command, execution_policy)
        failures.extend(record_failures)
        if not record_failures:
            total_duration += float(record["duration_seconds"])
            if record["status"] == "failed":
                stopped = execution_policy["stop_after_first_failure"]
    expected_passed = (
        not failures
        and all(
            isinstance(record, dict) and record.get("status") == "passed"
            for record in commands
        )
    )
    if type(quality_gate_passed) is not bool or quality_gate_passed is not expected_passed:
        failures.append(
            failure("quality_gate_passed", "Quality-gate pass state does not match commands.")
        )
    if total_duration > execution_policy["max_total_seconds"]:
        failures.append(
            failure("total_duration", "Quality-gate command duration exceeds total bound.")
        )
    return failures


def validate_receipt_value(
    value: Any,
    expected_session: dict[str, Any],
    patch: Path,
    patch_receipt_sha256: str,
    gradle_user_home: Path,
    patch_validation: dict[str, Any],
    policy: dict[str, Any],
) -> list[dict[str, str]]:
    expected_fields = {
        "quality_gate_receipt_version",
        "purpose",
        "mode",
        *FALSE_FIELDS,
        "execution_attempted",
        "quality_gate_passed",
        "network_requested",
        "identity",
        "patch_receipt_sha256",
        "patch_sha256",
        "gradle_user_home",
        "commands",
        "workspace_git_state_unchanged",
        "bindings",
    }
    if not isinstance(value, dict) or set(value) != expected_fields:
        return [failure("receipt_schema", "Quality-gate receipt fields do not match.")]
    execution_policy = run_implementation_quality_gate.EXPECTED_POLICY
    failures: list[dict[str, str]] = []
    if (
        type(value["quality_gate_receipt_version"]) is not int
        or value["quality_gate_receipt_version"] != execution_policy["version"]
        or value["purpose"] != execution_policy["purpose"]
        or value["mode"] != execution_policy["mode"]
        or any(value[field] is not False for field in FALSE_FIELDS)
        or value["execution_attempted"] is not True
        or value["network_requested"] is not False
        or value["workspace_git_state_unchanged"] is not True
    ):
        failures.append(failure("receipt_metadata", "Quality-gate metadata does not match."))
    expected_identity = {
        field: expected_session[field]
        for field in sorted(validate_implementation_result.SESSION_FIELDS)
    }
    if (
        not exact_equal(value["identity"], expected_identity)
        or value["patch_receipt_sha256"] != patch_receipt_sha256
        or value["patch_sha256"]
        != validate_implementation_result.sha256_bytes(patch.read_bytes())
        or value["gradle_user_home"] != str(gradle_user_home)
        or patch_validation["valid"] is not True
        or patch_validation["patch_candidate_ready"] is not True
    ):
        failures.append(failure("receipt_identity", "Quality-gate identity does not match."))
    failures.extend(
        validate_command_sequence(
            value["commands"],
            value["quality_gate_passed"],
            execution_policy,
        )
    )
    trusted_bindings = initialize_portable_run.binding_records(
        policy["trusted_receipt_bindings"]
    )
    if not exact_equal(value["bindings"], trusted_bindings):
        failures.append(
            failure(
                "trusted_binding_mismatch",
                "Quality-gate receipt bindings differ from current trusted bytes.",
            )
        )
    return failures


def validate(
    source_checkout: Path,
    result_path: Path,
    expected_session_path: Path,
    patch: Path,
    patch_receipt: Path,
    patch_receipt_sha256: str,
    quality_gate_receipt: Path,
    quality_gate_receipt_sha256: str,
    gradle_user_home: Path,
    policy: dict[str, Any],
) -> dict[str, Any]:
    result = base_result(quality_gate_receipt_sha256)
    if not valid_sha256(quality_gate_receipt_sha256):
        raise ValueError(
            "Expected quality-gate receipt SHA-256 must be lowercase hexadecimal"
        )
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
    quality_gate_receipt = validate_receipt_path(
        source_root,
        workspace,
        quality_gate_receipt,
        policy,
    )
    gradle_user_home = run_implementation_quality_gate.validate_gradle_user_home(
        source_root,
        workspace,
        gradle_user_home,
        run_implementation_quality_gate.load_policy(),
    )
    input_paths = [
        result_path.resolve(),
        expected_session_path.resolve(),
        patch.resolve(),
        patch_receipt.resolve(),
        quality_gate_receipt,
    ]
    if len(set(input_paths)) != len(input_paths):
        raise ValueError("Quality-gate validation inputs must use distinct paths")
    workspace_before = generate_complete_patch.repository_snapshot(workspace)
    input_bytes = {str(path): path.read_bytes() for path in input_paths}
    receipt_bytes = input_bytes[str(quality_gate_receipt)]
    if len(receipt_bytes) > policy["max_receipt_bytes"]:
        result["failures"].append(
            failure("max_receipt_bytes", "Quality-gate receipt exceeds byte limit.")
        )
        return result
    if validate_implementation_result.sha256_bytes(receipt_bytes) != quality_gate_receipt_sha256:
        result["failures"].append(
            failure("receipt_sha256", "Quality-gate receipt digest does not match.")
        )
        return result
    value = json.loads(receipt_bytes.decode("utf-8"))
    if (
        policy["require_canonical_receipt"]
        and receipt_bytes != validate_implementation_patch.canonical_bytes(value)
    ):
        result["failures"].append(
            failure("canonical_receipt", "Quality-gate receipt is not canonical JSON.")
        )
        return result
    patch_validation = validate_implementation_patch_receipt.validate(
        source_root,
        result_path,
        expected_session_path,
        patch,
        patch_receipt,
        patch_receipt_sha256,
        validate_implementation_patch_receipt.load_policy(),
    )
    result["patch_candidate_ready"] = patch_validation["patch_candidate_ready"]
    if policy["require_valid_patch_receipt"] and not patch_validation["valid"]:
        result["failures"].append(
            failure("patch_receipt", "Quality-gate validation requires a valid patch receipt.")
        )
    if policy["require_patch_candidate_ready"] and not patch_validation[
        "patch_candidate_ready"
    ]:
        result["failures"].append(
            failure("patch_candidate", "Quality-gate validation requires a candidate patch.")
        )
    result["failures"].extend(
        validate_receipt_value(
            value,
            expected_session,
            patch,
            patch_receipt_sha256,
            gradle_user_home,
            patch_validation,
            policy,
        )
    )
    if isinstance(value, dict):
        result.update(
            execution_attempted=value.get("execution_attempted") is True,
            quality_gate_passed=value.get("quality_gate_passed") is True,
            commands=value.get("commands", []),
        )
    if result["failures"]:
        return result
    validator_bindings = initialize_portable_run.binding_records(
        policy["validator_bindings"]
    )
    refreshed_bindings = initialize_portable_run.binding_records(
        policy["validator_bindings"]
    )
    refreshed_inputs = {str(path): path.read_bytes() for path in input_paths}
    if (
        refreshed_inputs != input_bytes
        or generate_complete_patch.repository_snapshot(workspace) != workspace_before
        or not exact_equal(refreshed_bindings, validator_bindings)
    ):
        result["failures"].append(
            failure(
                "state_changed",
                "Quality-gate evidence, workspace, or validator changed.",
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
    parser.add_argument("--patch-receipt", type=Path, required=True)
    parser.add_argument("--patch-receipt-sha256", required=True)
    parser.add_argument("--quality-gate-receipt", type=Path, required=True)
    parser.add_argument("--quality-gate-receipt-sha256", required=True)
    parser.add_argument("--gradle-user-home", type=Path, required=True)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def format_text(result: dict[str, Any]) -> str:
    status = "VALID" if result["valid"] else "INVALID"
    lines = [
        f"implementation-quality-gate-validation: {status}",
        f"quality_gate_passed={str(result['quality_gate_passed']).lower()}",
        "implementation_approved=false",
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
            args.patch_receipt,
            args.patch_receipt_sha256,
            args.quality_gate_receipt,
            args.quality_gate_receipt_sha256,
            args.gradle_user_home,
            load_policy(),
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        print(f"implementation-quality-gate-validation: ERROR\n- {error}", file=sys.stderr)
        return 1
    if args.format == "json":
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(format_text(result))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
