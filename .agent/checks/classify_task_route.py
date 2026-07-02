#!/usr/bin/env python3
"""Classify the declared task risk route from a validated portable run."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import initialize_portable_run
import validate_artifacts


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / ".agent" / "policies" / "task-risk-route.json"
FALSE_FIELDS = initialize_portable_run.FALSE_FIELDS

EXPECTED_POLICY: dict[str, Any] = {
    "version": 1,
    "purpose": "declared_task_risk_route",
    "mode": "portable-run-frontmatter-only",
    "risk_to_route": {
        "low": "A",
        "medium": "B",
        "high": "C",
    },
    "required_artifact": "task.md",
    "requires_valid_portable_artifacts": True,
    "authorizes": False,
    "bindings": [
        ".agent/checks/classify_task_route.py",
        ".agent/policies/task-risk-route.json",
        ".agent/checks/validate_artifacts.py",
        ".agent/policies/artifact-contract.json",
    ],
}


def load_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    policy = json.loads(path.read_text(encoding="utf-8"))
    if policy != EXPECTED_POLICY:
        raise ValueError("Task risk-route policy does not match")
    return policy


def base_result() -> dict[str, Any]:
    return {
        "classified": False,
        **{field: False for field in FALSE_FIELDS},
        "task_approved": False,
        "task_status": None,
        "risk": None,
        "route": None,
        "source": "task.md frontmatter",
        "errors": [],
    }


def classify(run: Path, policy: dict[str, Any]) -> dict[str, Any]:
    result = base_result()
    contract = validate_artifacts.load_contract(
        REPO_ROOT / ".agent" / "policies" / "artifact-contract.json"
    )
    validation = validate_artifacts.validate_directory(run, contract, False)
    if not validation["valid"]:
        result["errors"] = validation["errors"]
        return result
    task = validate_artifacts.parse_artifact(run / policy["required_artifact"])
    status = task.frontmatter["status"]
    risk = task.frontmatter["risk"]
    result.update(
        classified=True,
        task_approved=status == "approved",
        task_status=status,
        risk=risk,
        route=policy["risk_to_route"][risk],
        policy_bindings=initialize_portable_run.binding_records(policy["bindings"]),
    )
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--format", choices=("text", "json"), default="json")
    return parser


def format_text(result: dict[str, Any]) -> str:
    if not result["classified"]:
        lines = ["task-risk-route: INVALID", "authorized=false"]
        lines.extend(f"- {item}" for item in result["errors"])
        return "\n".join(lines)
    return "\n".join(
        [
            "task-risk-route: CLASSIFIED",
            f"risk={result['risk']}",
            f"route={result['route']}",
            f"task_status={result['task_status']}",
            f"task_approved={str(result['task_approved']).lower()}",
            "authorized=false",
        ]
    )


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = classify(args.run, load_policy())
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        print(f"task-risk-route: ERROR\n- {error}", file=sys.stderr)
        return 1
    if args.format == "json":
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(format_text(result))
    return 0 if result["classified"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
