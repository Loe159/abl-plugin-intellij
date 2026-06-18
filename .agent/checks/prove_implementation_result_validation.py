#!/usr/bin/env python3
"""Prove the exact implementation-result contract against adversarial fixtures."""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Any

import diff_policy
import initialize_portable_run
import validate_implementation_result


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = (
    REPO_ROOT
    / ".agent"
    / "policies"
    / "implementation-result-validation-proof.json"
)
FALSE_FIELDS = validate_implementation_result.FALSE_FIELDS
EXPECTED_POLICY: dict[str, Any] = {
    "version": 1,
    "purpose": "implementation_result_contract_validation_proof",
    "mode": "enforcement-proof",
    "proven_control": "implementation_result_contract_validation",
    "unproven_controls": [
        "runner_enforced_output_post_validation",
        "implementation_patch_post_validation",
        "real_agent_result_compatibility",
    ],
    "bindings": [
        ".agent/checks/validate_implementation_result.py",
        ".agent/policies/implementation-result-validation.json",
        ".agent/schemas/implementation-result.schema.json",
        ".agent/checks/prove_implementation_result_validation.py",
        ".agent/policies/implementation-result-validation-proof.json",
    ],
}


def load_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    policy = json.loads(path.read_text(encoding="utf-8"))
    if policy != EXPECTED_POLICY:
        raise ValueError("Implementation-result validation proof policy does not match")
    return policy


def expected_session(repo: Path) -> dict[str, Any]:
    return {
        "issue": 57,
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
        "summary": "Implemented the reviewed local change; deterministic validation remains pending.",
        "workspace_changed": True,
        "patch_generated": False,
        "deterministic_checks_run": False,
        "publication_requested": False,
        "network_requested": False,
        "next_action": "deterministic_patch_generation",
    }


def execution(stdout: bytes, **changes: Any) -> dict[str, Any]:
    value = {
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
    value.update(changes)
    if "stderr" in changes and "captured_stderr_bytes" not in changes:
        value["captured_stderr_bytes"] = len(changes["stderr"])
    return value


def prove(repo: Path, policy: dict[str, Any]) -> dict[str, Any]:
    repo = repo.resolve()
    if not repo.is_dir():
        raise ValueError("Repository path must be an existing directory")
    validation_policy = validate_implementation_result.load_policy()
    validate_implementation_result.load_schema()
    secret_policy = diff_policy.load_policy(
        validate_implementation_result.DIFF_POLICY_PATH
    )
    session = expected_session(repo)
    valid_value = result_value(session)
    valid_execution = execution(
        validate_implementation_result.canonical_result_bytes(valid_value)
    )
    valid = validate_implementation_result.validate_execution(
        valid_execution,
        session,
        validation_policy,
        secret_policy,
    )

    fixtures: list[dict[str, Any]] = [
        {
            "id": "canonical_completed_result",
            "matched": valid["valid"] is True
            and valid["implementation_candidate_ready"] is True,
            "accepted": valid["valid"],
            "candidate_ready": valid["implementation_candidate_ready"],
        }
    ]
    mutations: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
    wrong_session = copy.deepcopy(valid_value)
    wrong_session["start_authorization_receipt_sha256"] = "4" * 64
    mutations.append(("wrong_session_identity", wrong_session, {}))
    extra_field = copy.deepcopy(valid_value)
    extra_field["unexpected"] = True
    mutations.append(("extra_result_field", extra_field, {}))
    secret = copy.deepcopy(valid_value)
    secret["summary"] = "Rejected marker ghp_" + ("A" * 36)
    mutations.append(("high_confidence_secret", secret, {}))
    overclaim = copy.deepcopy(valid_value)
    overclaim["patch_generated"] = True
    mutations.append(("deferred_action_overclaim", overclaim, {}))
    no_change = copy.deepcopy(valid_value)
    no_change["workspace_changed"] = False
    mutations.append(("completed_without_workspace_change", no_change, {}))
    for fixture_id, value, execution_changes in mutations:
        rejected = validate_implementation_result.validate_execution(
            execution(
                validate_implementation_result.canonical_result_bytes(value),
                **execution_changes,
            ),
            session,
            validation_policy,
            secret_policy,
        )
        fixtures.append(
            {
                "id": fixture_id,
                "matched": rejected["valid"] is False,
                "accepted": rejected["valid"],
                "failure_rules": [item["rule"] for item in rejected["failures"]],
            }
        )
    incomplete = validate_implementation_result.validate_execution(
        execution(
            validate_implementation_result.canonical_result_bytes(valid_value),
            capture_complete=False,
        ),
        session,
        validation_policy,
        secret_policy,
    )
    fixtures.append(
        {
            "id": "incomplete_capture",
            "matched": incomplete["valid"] is False,
            "accepted": incomplete["valid"],
            "failure_rules": [item["rule"] for item in incomplete["failures"]],
        }
    )
    stderr = validate_implementation_result.validate_execution(
        execution(
            validate_implementation_result.canonical_result_bytes(valid_value),
            stderr=b"untrusted diagnostic",
        ),
        session,
        validation_policy,
        secret_policy,
    )
    fixtures.append(
        {
            "id": "nonempty_stderr",
            "matched": stderr["valid"] is False,
            "accepted": stderr["valid"],
            "failure_rules": [item["rule"] for item in stderr["failures"]],
        }
    )
    verified = all(item["matched"] for item in fixtures)
    return {
        "proof_version": policy["version"],
        "purpose": policy["purpose"],
        "mode": policy["mode"],
        **{field: False for field in FALSE_FIELDS},
        "proof_complete": True,
        "scope": {
            "validates_exact_captured_result_contract": True,
            "binds_expected_session_identity": True,
            "rejects_high_confidence_secret_signatures": True,
            "invokes_agent": False,
            "generates_or_validates_patch": False,
            "proves_runner_calls_validator": False,
        },
        "fixtures": fixtures,
        "control_assessments": [
            {
                "id": policy["proven_control"],
                "assessment": "verified_enforcement" if verified else "not_proven",
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
        f"implementation-result-validation-proof: {assessment.upper()}",
        "runner_enforced_output_post_validation=not_proven",
        "implementation_patch_post_validation=not_proven",
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
        print(
            f"implementation-result-validation-proof: ERROR\n- {error}",
            file=sys.stderr,
        )
        return 1
    if args.format == "json":
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(format_text(result))
    return (
        0
        if result["control_assessments"][0]["assessment"] == "verified_enforcement"
        else 2
    )


if __name__ == "__main__":
    raise SystemExit(main())
