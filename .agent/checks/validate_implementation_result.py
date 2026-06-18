#!/usr/bin/env python3
"""Validate one captured implementation result against an exact session identity."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

import build_stage_context
import diff_policy
import initialize_portable_run


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / ".agent" / "policies" / "implementation-result-validation.json"
SCHEMA_PATH = REPO_ROOT / ".agent" / "schemas" / "implementation-result.schema.json"
DIFF_POLICY_PATH = REPO_ROOT / ".agent" / "policies" / "diff-policy.json"
FALSE_FIELDS = (
    "authorized",
    "agent_invocation_authorized",
    "implementation_authorized",
    "repository_mutation_authorized",
    "network_authorized",
    "publication_authorized",
    "runner_selected",
    "session_start_authorized",
)
SHA1 = re.compile(r"[0-9a-f]{40}")
SHA256 = re.compile(r"[0-9a-f]{64}")
RUNNER_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}")
RESULT_FIELDS = {
    "result_version",
    "purpose",
    "mode",
    "status",
    "issue",
    "risk",
    "base_commit",
    "workspace",
    "runner_id",
    "preflight_sha256",
    "start_authorization_receipt_sha256",
    "summary",
    "workspace_changed",
    "patch_generated",
    "deterministic_checks_run",
    "publication_requested",
    "network_requested",
    "next_action",
}
SESSION_FIELDS = {
    "issue",
    "risk",
    "base_commit",
    "workspace",
    "runner_id",
    "preflight_sha256",
    "start_authorization_receipt_sha256",
}

EXPECTED_POLICY: dict[str, Any] = {
    "version": 1,
    "purpose": "implementation_result_contract_validation",
    "mode": "validation-only",
    "max_result_bytes": 16384,
    "max_summary_chars": 1000,
    "allowed_statuses": ["completed", "blocked", "failed"],
    "candidate_ready_status": "completed",
    "status_next_actions": {
        "completed": "deterministic_patch_generation",
        "blocked": "human_review",
        "failed": "human_review",
    },
    "require_complete_capture": True,
    "require_completed_execution": True,
    "require_direct_child_reaped": True,
    "require_no_kill_requested": True,
    "require_zero_protocol_exit": True,
    "require_empty_stderr": True,
    "require_exact_capture_byte_counts": True,
    "require_workspace_change_for_candidate": True,
    "required_false_fields": [
        "patch_generated",
        "deterministic_checks_run",
        "publication_requested",
        "network_requested",
    ],
    "bindings": [
        ".agent/checks/validate_implementation_result.py",
        ".agent/policies/implementation-result-validation.json",
        ".agent/schemas/implementation-result.schema.json",
    ],
}

EXPECTED_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://local.invalid/agent/implementation-result.schema.json",
    "title": "Implementation Session Result",
    "type": "object",
    "additionalProperties": False,
    "required": [
        "result_version",
        "purpose",
        "mode",
        "status",
        "issue",
        "risk",
        "base_commit",
        "workspace",
        "runner_id",
        "preflight_sha256",
        "start_authorization_receipt_sha256",
        "summary",
        "workspace_changed",
        "patch_generated",
        "deterministic_checks_run",
        "publication_requested",
        "network_requested",
        "next_action",
    ],
    "properties": {
        "result_version": {"const": 1},
        "purpose": {"const": "implementation_session_result"},
        "mode": {"const": "untrusted-runner-output"},
        "status": {"enum": ["completed", "blocked", "failed"]},
        "issue": {"type": "integer", "minimum": 1},
        "risk": {"enum": ["low", "medium", "high"]},
        "base_commit": {"type": "string", "pattern": "^[0-9a-f]{40}$"},
        "workspace": {"type": "string", "minLength": 1},
        "runner_id": {
            "type": "string",
            "pattern": "^[a-z0-9][a-z0-9._-]{0,63}$",
        },
        "preflight_sha256": {
            "type": "string",
            "pattern": "^[0-9a-f]{64}$",
        },
        "start_authorization_receipt_sha256": {
            "type": "string",
            "pattern": "^[0-9a-f]{64}$",
        },
        "summary": {
            "type": "string",
            "minLength": 1,
            "maxLength": 1000,
        },
        "workspace_changed": {"type": "boolean"},
        "patch_generated": {"const": False},
        "deterministic_checks_run": {"const": False},
        "publication_requested": {"const": False},
        "network_requested": {"const": False},
        "next_action": {
            "enum": ["deterministic_patch_generation", "human_review"],
        },
    },
}


def load_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    policy = json.loads(path.read_text(encoding="utf-8"))
    if policy != EXPECTED_POLICY:
        raise ValueError("Implementation-result validation policy does not match")
    return policy


def load_schema(path: Path = SCHEMA_PATH) -> dict[str, Any]:
    schema = json.loads(path.read_text(encoding="utf-8"))
    if schema != EXPECTED_SCHEMA:
        raise ValueError("Implementation-result schema does not match")
    return schema


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def canonical_result_bytes(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, separators=(",", ":"), sort_keys=True) + "\n").encode("utf-8")


def failure(rule: str, message: str) -> dict[str, str]:
    return {"rule": rule, "message": message}


def validate_expected_session(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != SESSION_FIELDS:
        raise ValueError("Expected implementation session fields do not match")
    workspace = Path(value["workspace"]) if isinstance(value["workspace"], str) else None
    if (
        type(value["issue"]) is not int
        or value["issue"] < 1
        or value["risk"] not in {"low", "medium", "high"}
        or type(value["base_commit"]) is not str
        or SHA1.fullmatch(value["base_commit"]) is None
        or type(value["workspace"]) is not str
        or not value["workspace"]
        or workspace is None
        or not workspace.is_absolute()
        or workspace.is_symlink()
        or not workspace.resolve().is_dir()
        or str(workspace.resolve()) != value["workspace"]
        or "\n" in value["workspace"]
        or "\r" in value["workspace"]
        or type(value["runner_id"]) is not str
        or RUNNER_ID.fullmatch(value["runner_id"]) is None
        or type(value["preflight_sha256"]) is not str
        or SHA256.fullmatch(value["preflight_sha256"]) is None
        or type(value["start_authorization_receipt_sha256"]) is not str
        or SHA256.fullmatch(value["start_authorization_receipt_sha256"]) is None
    ):
        raise ValueError("Expected implementation session identity is invalid")
    return value


def exact_equal(actual: Any, expected: Any) -> bool:
    return type(actual) is type(expected) and actual == expected


def validate_result_value(
    value: Any,
    expected_session: dict[str, Any],
    policy: dict[str, Any],
) -> list[dict[str, str]]:
    if not isinstance(value, dict) or set(value) != RESULT_FIELDS:
        return [failure("result_schema", "Implementation result fields do not match.")]
    failures: list[dict[str, str]] = []
    if (
        type(value["result_version"]) is not int
        or value["result_version"] != policy["version"]
        or value["purpose"] != "implementation_session_result"
        or value["mode"] != "untrusted-runner-output"
    ):
        failures.append(
            failure("result_metadata", "Implementation result metadata does not match.")
        )
    if any(
        not exact_equal(value[field], expected_session[field])
        for field in SESSION_FIELDS
    ):
        failures.append(
            failure("session_identity", "Implementation result session identity does not match.")
        )
    status = value["status"]
    if type(status) is not str or status not in policy["allowed_statuses"]:
        failures.append(failure("status", "Implementation result status is not allowed."))
    elif value["next_action"] != policy["status_next_actions"][status]:
        failures.append(
            failure("next_action", "Implementation result next action does not match status.")
        )
    summary = value["summary"]
    if (
        type(summary) is not str
        or not summary.strip()
        or len(summary) > policy["max_summary_chars"]
        or any(character in summary for character in "\r\n\x00")
    ):
        failures.append(
            failure("summary", "Implementation result summary is not bounded plain text.")
        )
    if type(value["workspace_changed"]) is not bool:
        failures.append(
            failure("workspace_changed", "Workspace-change declaration must be boolean.")
        )
    if any(value[field] is not False for field in policy["required_false_fields"]):
        failures.append(
            failure(
                "forbidden_claim",
                "Implementation result claimed a deferred deterministic or external action.",
            )
        )
    if (
        status == policy["candidate_ready_status"]
        and policy["require_workspace_change_for_candidate"]
        and value["workspace_changed"] is not True
    ):
        failures.append(
            failure(
                "workspace_change_required",
                "Completed implementation result must declare a changed workspace.",
            )
        )
    return failures


def base_result() -> dict[str, Any]:
    return {
        "valid": False,
        "implementation_candidate_ready": False,
        **{field: False for field in FALSE_FIELDS},
        "validation_complete": True,
        "status": None,
        "issue": None,
        "risk": None,
        "base_commit": None,
        "workspace": None,
        "runner_id": None,
        "result_sha256": None,
        "result_size_bytes": None,
        "failures": [],
    }


def validate_execution(
    execution: dict[str, Any],
    expected_session: dict[str, Any],
    policy: dict[str, Any],
    secret_policy: dict[str, Any],
) -> dict[str, Any]:
    expected_session = validate_expected_session(expected_session)
    result = base_result()
    result.update(
        issue=expected_session["issue"],
        risk=expected_session["risk"],
        base_commit=expected_session["base_commit"],
        workspace=expected_session["workspace"],
        runner_id=expected_session["runner_id"],
    )
    stdout = execution.get("stdout")
    stderr = execution.get("stderr")
    if not isinstance(stdout, bytes) or not isinstance(stderr, bytes):
        raise ValueError("Captured implementation output must be bytes")
    result.update(result_sha256=sha256_bytes(stdout), result_size_bytes=len(stdout))
    if (
        policy["require_completed_execution"]
        and execution.get("completed") is not True
    ):
        result["failures"].append(
            failure("execution_completed", "Implementation execution did not complete.")
        )
    if policy["require_complete_capture"] and execution.get("capture_complete") is not True:
        result["failures"].append(
            failure("capture_complete", "Implementation result capture is incomplete.")
        )
    if execution.get("timed_out") is not False:
        result["failures"].append(
            failure("timed_out", "Implementation process exceeded its deadline.")
        )
    if execution.get("output_limit_exceeded") is not False:
        result["failures"].append(
            failure("output_limit", "Implementation process exceeded its output limit.")
        )
    if (
        policy["require_direct_child_reaped"]
        and execution.get("direct_child_reaped") is not True
    ):
        result["failures"].append(
            failure("direct_child_reaped", "Implementation process was not reaped.")
        )
    if (
        policy["require_no_kill_requested"]
        and execution.get("kill_requested") is not False
    ):
        result["failures"].append(
            failure("kill_requested", "Implementation result followed a kill request.")
        )
    if (
        policy["require_zero_protocol_exit"]
        and execution.get("returncode") != 0
    ):
        result["failures"].append(
            failure("protocol_exit", "Implementation result protocol exited nonzero.")
        )
    if policy["require_empty_stderr"] and stderr:
        result["failures"].append(
            failure("stderr", "Implementation result protocol wrote to stderr.")
        )
    if policy["require_exact_capture_byte_counts"] and (
        execution.get("captured_stdout_bytes") != len(stdout)
        or execution.get("captured_stderr_bytes") != len(stderr)
    ):
        result["failures"].append(
            failure("capture_byte_counts", "Captured output byte counts do not match.")
        )
    if len(stdout) > policy["max_result_bytes"]:
        result["failures"].append(
            failure("max_result_bytes", "Implementation result exceeds its byte limit.")
        )
        return result
    try:
        value = json.loads(stdout.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        result["failures"].append(
            failure("result_json", "Implementation result is not one UTF-8 JSON object.")
        )
        return result
    if not isinstance(value, dict):
        result["failures"].append(
            failure("result_json", "Implementation result must be one JSON object.")
        )
        return result
    if stdout != canonical_result_bytes(value):
        result["failures"].append(
            failure("canonical_json", "Implementation result is not canonical JSON.")
        )
    result["failures"].extend(validate_result_value(value, expected_session, policy))
    detections = build_stage_context.detect_secrets(
        [build_stage_context.content_record("implementation-result.json", stdout.decode("utf-8"))],
        secret_policy,
    )
    if detections:
        result["failures"].append(
            failure(
                "high_confidence_secret",
                "Implementation result contains a high-confidence secret signature.",
            )
        )
    result["status"] = value.get("status")
    if result["failures"]:
        return result
    result["valid"] = True
    result["implementation_candidate_ready"] = (
        value["status"] == policy["candidate_ready_status"]
        and value["workspace_changed"] is True
    )
    result["bindings"] = initialize_portable_run.binding_records(policy["bindings"])
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--expected-session", type=Path, required=True)
    parser.add_argument("--stderr", type=Path)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def format_text(result: dict[str, Any]) -> str:
    status = "VALID" if result["valid"] else "INVALID"
    lines = [
        f"implementation-result-validation: {status}",
        f"implementation_candidate_ready={str(result['implementation_candidate_ready']).lower()}",
        "publication_authorized=false",
        "session_start_authorized=false",
    ]
    lines.extend(f"- {item['rule']}: {item['message']}" for item in result["failures"])
    return "\n".join(lines)


def main() -> int:
    args = build_parser().parse_args()
    try:
        policy = load_policy()
        load_schema()
        stdout = args.result.read_bytes()
        stderr = args.stderr.read_bytes() if args.stderr else b""
        expected_session = json.loads(args.expected_session.read_text(encoding="utf-8-sig"))
        execution = {
            "completed": True,
            "stdout": stdout,
            "stderr": stderr,
            "capture_complete": True,
            "timed_out": False,
            "output_limit_exceeded": False,
            "kill_requested": False,
            "direct_child_reaped": True,
            "returncode": 0,
            "captured_stdout_bytes": len(stdout),
            "captured_stderr_bytes": len(stderr),
        }
        result = validate_execution(
            execution,
            expected_session,
            policy,
            diff_policy.load_policy(DIFF_POLICY_PATH),
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        print(f"implementation-result-validation: ERROR\n- {error}", file=sys.stderr)
        return 1
    if args.format == "json":
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(format_text(result))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
