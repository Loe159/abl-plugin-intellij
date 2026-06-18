#!/usr/bin/env python3
"""Check research readiness with independently validated task-approval provenance."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import check_stage_readiness
import initialize_portable_run
import validate_task_approval


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / ".agent" / "policies" / "research-readiness.json"
FALSE_FIELDS = initialize_portable_run.FALSE_FIELDS

EXPECTED_POLICY: dict[str, Any] = {
    "version": 1,
    "purpose": "provenance_aware_research_readiness",
    "mode": "readiness-only",
    "stage": "research",
    "require_declared_readiness": True,
    "require_valid_task_approval": True,
    "bindings": [
        ".agent/checks/check_research_readiness.py",
        ".agent/checks/check_stage_readiness.py",
        ".agent/checks/validate_task_approval.py",
        ".agent/policies/research-readiness.json",
        ".agent/policies/stage-readiness.json",
        ".agent/policies/task-approval-validation.json",
    ],
}


def load_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    policy = json.loads(path.read_text(encoding="utf-8"))
    if policy != EXPECTED_POLICY:
        raise ValueError("Research-readiness policy does not match the contract")
    return policy


def load_policies() -> dict[str, Any]:
    return {
        **validate_task_approval.load_policies(),
        "research_readiness": load_policy(),
    }


def check(
    repo: Path,
    run: Path,
    approval_receipt: Path,
    approval_receipt_sha256: str,
    policies: dict[str, Any],
) -> dict[str, Any]:
    policy = policies["research_readiness"]
    bindings = initialize_portable_run.binding_records(policy["bindings"])
    declared = check_stage_readiness.check_readiness(
        run,
        policy["stage"],
        policies["artifact"],
        policies["readiness"],
    )
    if approval_receipt.is_file():
        approval = validate_task_approval.validate(
            repo,
            run,
            approval_receipt,
            approval_receipt_sha256,
            policies,
        )
    else:
        approval = {
            "valid": False,
            "failures": [
                {
                    "rule": "approval_receipt_missing",
                    "message": "Task-approval receipt does not exist.",
                }
            ],
        }
    failures: list[dict[str, Any]] = []
    if policy["require_declared_readiness"] and not declared["ready"]:
        failures.append(
            {
                "rule": "declared_readiness",
                "message": "Declared research prerequisites are not ready.",
                "details": declared["failures"],
            }
        )
    if policy["require_valid_task_approval"] and not approval["valid"]:
        failures.append(
            {
                "rule": "task_approval_provenance",
                "message": "Task-approval provenance is not valid.",
                "details": approval["failures"],
            }
        )
    refreshed_bindings = initialize_portable_run.binding_records(policy["bindings"])
    if refreshed_bindings != bindings:
        failures.append(
            {
                "rule": "readiness_controls_changed",
                "message": "Research-readiness controls changed during the check.",
            }
        )
    return {
        "ready": not failures,
        **{field: False for field in FALSE_FIELDS},
        "stage": policy["stage"],
        "risk": declared["risk"],
        "directory": declared["directory"],
        "declared_ready": declared["ready"],
        "task_approval_valid": approval["valid"],
        "approval_receipt_sha256": approval_receipt_sha256,
        "bindings": bindings,
        "failures": failures,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--approval-receipt", type=Path, required=True)
    parser.add_argument("--approval-receipt-sha256", required=True)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def format_text(result: dict[str, Any]) -> str:
    status = "READY" if result["ready"] else "NOT_READY"
    lines = [
        f"research-readiness: {status}",
        f"declared_ready={str(result['declared_ready']).lower()}",
        f"task_approval_valid={str(result['task_approval_valid']).lower()}",
        "authorized=false",
    ]
    lines.extend(f"- {item['rule']}: {item['message']}" for item in result["failures"])
    return "\n".join(lines)


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = check(
            args.repo,
            args.run,
            args.approval_receipt,
            args.approval_receipt_sha256,
            load_policies(),
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        print(f"research-readiness: ERROR\n- {error}", file=sys.stderr)
        return 1
    if args.format == "json":
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(format_text(result))
    return 0 if result["ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
