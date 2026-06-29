#!/usr/bin/env python3
"""Prove only the bounded process mechanism used by the implementation quality gate."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

import initialize_portable_run
import run_implementation_quality_gate
import validate_implementation_result


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / ".agent" / "policies" / "implementation-quality-gate-proof.json"
FALSE_FIELDS = validate_implementation_result.FALSE_FIELDS

EXPECTED_POLICY: dict[str, Any] = {
    "version": 1,
    "purpose": "implementation_quality_gate_execution_mechanism_proof",
    "mode": "fixture-only",
    "timeout_seconds": 0.2,
    "cleanup_timeout_seconds": 1.0,
    "capture_limit_bytes": 32768,
    "proven_control": "bounded_quality_gate_execution_fixture",
    "unproven_controls": [
        "implementation_quality_gate_execution",
        "quality_gate_receipt_validation",
        "real_gradle_quality_gate_execution",
        "quality_gate_descendant_cleanup",
    ],
    "bindings": [
        ".agent/checks/run_implementation_quality_gate.py",
        ".agent/policies/implementation-quality-gate.json",
        ".agent/checks/prove_implementation_quality_gate.py",
        ".agent/policies/implementation-quality-gate-proof.json",
    ],
}


def load_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    policy = json.loads(path.read_text(encoding="utf-8"))
    if policy != EXPECTED_POLICY:
        raise ValueError("Implementation quality-gate proof policy does not match")
    return policy


def fixture_python_executable() -> Path:
    candidate = Path(sys.prefix) / "python.exe"
    if os.name == "nt" and candidate.is_file() and not candidate.is_symlink():
        return candidate.resolve()
    return Path(sys.executable).resolve()


def python_command(script: str) -> list[str]:
    return [
        str(fixture_python_executable()),
        "-I",
        "-S",
        "-B",
        "-c",
        script,
    ]


def environment(policy: dict[str, Any]) -> dict[str, str]:
    parent = {
        name: os.environ[name]
        for name in policy["allowed_parent_variables"]
        if name in os.environ
    }
    return run_implementation_quality_gate.child_environment(parent, policy)


def prove(repo: Path, policy: dict[str, Any]) -> dict[str, Any]:
    repo = repo.resolve()
    if not repo.is_dir():
        raise ValueError("Repository path must be an existing directory")
    execution_policy = json.loads(
        json.dumps(run_implementation_quality_gate.load_policy())
    )
    execution_policy["cleanup_timeout_seconds"] = policy["cleanup_timeout_seconds"]
    execution_policy["max_captured_output_bytes"] = policy["capture_limit_bytes"]
    taskkill = shutil.which(execution_policy["tree_terminator"])
    supported = os.name == "nt" and taskkill is not None
    if supported and taskkill is not None:
        child_environment = environment(execution_policy)
        success = run_implementation_quality_gate.run_bounded(
            python_command(
                "import sys;sys.stdout.buffer.write(b'O'*4096);"
                "sys.stderr.buffer.write(b'E'*4096)"
            ),
            repo,
            child_environment,
            execution_policy,
            3.0,
            taskkill,
        )
        timeout = run_implementation_quality_gate.run_bounded(
            python_command("import time;time.sleep(10)"),
            repo,
            child_environment,
            execution_policy,
            policy["timeout_seconds"],
            taskkill,
        )
        output_limit = run_implementation_quality_gate.run_bounded(
            python_command(
                "import sys;sys.stdout.buffer.write(b'X'*131072);sys.stdout.flush()"
            ),
            repo,
            child_environment,
            execution_policy,
            3.0,
            taskkill,
        )
    else:
        success = timeout = output_limit = {}
    fixtures = [
        {
            "id": "bounded_dual_stream",
            "matched": (
                success.get("completed") is True
                and success.get("capture_complete") is True
                and success.get("returncode") == 0
                and success.get("captured_stdout_bytes") == 4096
                and success.get("captured_stderr_bytes") == 4096
            ),
        },
        {
            "id": "wall_clock_timeout",
            "matched": (
                timeout.get("timed_out") is True
                and timeout.get("tree_kill_requested") is True
                and timeout.get("root_reaped") is True
                and timeout.get("capture_complete") is False
            ),
            "tree_kill_returncode": timeout.get("tree_kill_returncode"),
            "direct_kill_requested": timeout.get("direct_kill_requested") is True,
        },
        {
            "id": "output_limit",
            "matched": (
                output_limit.get("output_limit_exceeded") is True
                and output_limit.get("tree_kill_requested") is True
                and output_limit.get("root_reaped") is True
                and output_limit.get("capture_complete") is False
                and not output_limit.get("stdout")
                and not output_limit.get("stderr")
            ),
            "tree_kill_returncode": output_limit.get("tree_kill_returncode"),
            "direct_kill_requested": output_limit.get("direct_kill_requested") is True,
        },
    ]
    verified = supported and all(item["matched"] for item in fixtures)
    return {
        "proof_version": policy["version"],
        "purpose": policy["purpose"],
        "mode": policy["mode"],
        **{field: False for field in FALSE_FIELDS},
        "proof_complete": True,
        "scope": {
            "platform": "Windows",
            "bounded_stdout_stderr": True,
            "wall_clock_timeout": True,
            "root_process_reaped": True,
            "descendant_cleanup_proven": False,
            "runs_gradle": False,
            "validates_candidate": False,
            "validates_quality_gate_receipt": False,
            "invokes_agent": False,
            "publishes": False,
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
        f"implementation-quality-gate-proof: {assessment.upper()}",
        "implementation_quality_gate_execution=not_proven",
        "quality_gate_receipt_validation=not_proven",
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
        print(f"implementation-quality-gate-proof: ERROR\n- {error}", file=sys.stderr)
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
