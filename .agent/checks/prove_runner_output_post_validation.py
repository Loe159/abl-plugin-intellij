#!/usr/bin/env python3
"""Prove a synthetic runner post-validates captured implementation output."""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Any, Callable

import diff_policy
import initialize_portable_run
import validate_implementation_result


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / ".agent" / "policies" / "runner-output-post-validation-proof.json"
FALSE_FIELDS = validate_implementation_result.FALSE_FIELDS
EXPECTED_POLICY: dict[str, Any] = {
    "version": 1,
    "purpose": "runner_output_post_validation_mechanism_proof",
    "mode": "fixture-only",
    "proven_control": "runner_output_post_validation_fixture",
    "unproven_controls": [
        "runner_enforced_output_post_validation",
        "real_agent_result_compatibility",
        "runner_invocation_enforcement",
    ],
    "bindings": [
        ".agent/checks/prove_runner_output_post_validation.py",
        ".agent/policies/runner-output-post-validation-proof.json",
        ".agent/checks/validate_implementation_result.py",
        ".agent/policies/implementation-result-validation.json",
        ".agent/schemas/implementation-result.schema.json",
    ],
}


def load_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    policy = json.loads(path.read_text(encoding="utf-8"))
    if policy != EXPECTED_POLICY:
        raise ValueError("Runner output post-validation proof policy does not match")
    return policy


def expected_session(repo: Path) -> dict[str, Any]:
    return {
        "issue": 72,
        "risk": "medium",
        "base_commit": "1" * 40,
        "workspace": str(repo.resolve()),
        "runner_id": "synthetic-runner",
        "preflight_sha256": "2" * 64,
        "start_authorization_receipt_sha256": "3" * 64,
    }


def result_value(session: dict[str, Any]) -> dict[str, Any]:
    return {
        "result_version": 1,
        "purpose": "implementation_session_result",
        "mode": "untrusted-runner-output",
        "status": "completed",
        **session,
        "summary": "Synthetic implementation output; post-validation fixture only.",
        "workspace_changed": True,
        "patch_generated": False,
        "deterministic_checks_run": False,
        "publication_requested": False,
        "network_requested": False,
        "next_action": "deterministic_patch_generation",
    }


def execution(stdout: bytes) -> dict[str, Any]:
    return {
        "completed": True,
        "timed_out": False,
        "output_limit_exceeded": False,
        "kill_requested": False,
        "direct_child_reaped": True,
        "returncode": 0,
        "stdout": stdout,
        "stderr": b"",
        "capture_complete": True,
        "captured_stdout_bytes": len(stdout),
        "captured_stderr_bytes": 0,
    }


def post_validate(
    captured: dict[str, Any],
    session: dict[str, Any],
    validation_policy: dict[str, Any],
    secret_policy: dict[str, Any],
    validator: Callable[..., dict[str, Any]] = validate_implementation_result.validate_execution,
) -> dict[str, Any]:
    validation = validator(captured, session, validation_policy, secret_policy)
    return {
        "validator_invoked": True,
        "accepted": validation.get("valid") is True,
        "candidate_ready": validation.get("implementation_candidate_ready") is True,
        "failure_rules": [item["rule"] for item in validation.get("failures", [])],
    }


def runner_record_enforced(record: dict[str, Any]) -> bool:
    return (
        record.get("validator_invoked") is True
        and type(record.get("accepted")) is bool
        and type(record.get("candidate_ready")) is bool
        and isinstance(record.get("failure_rules"), list)
    )


def prove(repo: Path, policy: dict[str, Any]) -> dict[str, Any]:
    repo = repo.resolve()
    if not repo.is_dir():
        raise ValueError("Repository path must be an existing directory")
    validation_policy = validate_implementation_result.load_policy()
    validate_implementation_result.load_schema()
    secret_policy = diff_policy.load_policy(validate_implementation_result.DIFF_POLICY_PATH)
    session = expected_session(repo)
    valid_result = result_value(session)
    valid_record = post_validate(
        execution(validate_implementation_result.canonical_result_bytes(valid_result)),
        session,
        validation_policy,
        secret_policy,
    )
    invalid_result = copy.deepcopy(valid_result)
    invalid_result["preflight_sha256"] = "4" * 64
    invalid_record = post_validate(
        execution(validate_implementation_result.canonical_result_bytes(invalid_result)),
        session,
        validation_policy,
        secret_policy,
    )
    bypass_record = {
        "validator_invoked": False,
        "accepted": True,
        "candidate_ready": True,
        "failure_rules": [],
    }
    fixtures = [
        {
            "id": "valid_capture_post_validated",
            "matched": (
                runner_record_enforced(valid_record)
                and valid_record["accepted"] is True
                and valid_record["candidate_ready"] is True
            ),
            **valid_record,
        },
        {
            "id": "invalid_capture_rejected_after_validation",
            "matched": (
                runner_record_enforced(invalid_record)
                and invalid_record["accepted"] is False
                and "session_identity" in invalid_record["failure_rules"]
            ),
            **invalid_record,
        },
        {
            "id": "missing_validator_invocation_detected",
            "matched": runner_record_enforced(bypass_record) is False,
            **bypass_record,
        },
    ]
    verified = all(item["matched"] for item in fixtures)
    return {
        "proof_version": policy["version"],
        "purpose": policy["purpose"],
        "mode": policy["mode"],
        **{field: False for field in FALSE_FIELDS},
        "proof_complete": True,
        "scope": {
            "uses_synthetic_runner_wrapper": True,
            "post_validates_captured_output": True,
            "invokes_agent": False,
            "proves_real_runner_enforcement": False,
            "proves_real_agent_result_compatibility": False,
        },
        "fixtures": fixtures,
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
        "bindings": initialize_portable_run.binding_records(policy["bindings"]),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def format_text(result: dict[str, Any]) -> str:
    assessment = result["control_assessments"][0]["assessment"]
    lines = [
        f"runner-output-post-validation-proof: {assessment.upper()}",
        "runner_enforced_output_post_validation=not_proven",
        "real_agent_result_compatibility=not_proven",
    ]
    lines.extend(
        f"- {fixture['id']}: {'matched' if fixture['matched'] else 'not_matched'}"
        for fixture in result["fixtures"]
    )
    return "\n".join(lines)


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = prove(args.repo, load_policy())
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        print(f"runner-output-post-validation-proof: ERROR\n- {error}", file=sys.stderr)
        return 1
    if args.format == "json":
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(format_text(result))
    return (
        0
        if result["control_assessments"][0]["assessment"] == "verified_fixture"
        else 2
    )


if __name__ == "__main__":
    raise SystemExit(main())
