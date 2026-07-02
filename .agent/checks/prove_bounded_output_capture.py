#!/usr/bin/env python3
"""Prove bounded concurrent stdout and stderr capture for the exact launcher."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Callable

import initialize_portable_run
import isolated_process


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / ".agent" / "policies" / "bounded-output-capture-proof.json"
FALSE_FIELDS = (
    "authorized",
    "agent_invocation_authorized",
    "implementation_authorized",
    "runner_selected",
    "session_start_authorized",
)

EXPECTED_POLICY: dict[str, Any] = {
    "version": 1,
    "purpose": "bounded_stream_output_capture_proof",
    "mode": "enforcement-proof",
    "timeout_seconds": 5.0,
    "fixtures": {
        "dual_stream": {
            "stdout_bytes": 49152,
            "stderr_bytes": 49152,
        },
        "output_limit": {
            "attempted_stdout_bytes": 262144,
        },
    },
    "proven_control": "bounded_output_capture",
    "unproven_controls": [
        "implementation_result_contract_validation",
        "runner_enforced_output_post_validation",
        "descendant_process_tree_cleanup_after_output_limit",
        "cross_platform_capture_equivalence",
    ],
    "bindings": [
        ".agent/checks/isolated_process.py",
        ".agent/policies/parent-environment-isolation.json",
        ".agent/checks/prove_bounded_output_capture.py",
        ".agent/policies/bounded-output-capture-proof.json",
    ],
}


def load_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    policy = json.loads(path.read_text(encoding="utf-8"))
    if policy != EXPECTED_POLICY:
        raise ValueError("Bounded-output capture proof policy does not match")
    return policy


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def parent_environment(launcher_policy: dict[str, Any]) -> dict[str, str]:
    return {
        name: os.environ[name]
        for name in launcher_policy["allowed_parent_variables"]
        if name in os.environ
    }


def fixture_python() -> Path:
    candidate = Path(sys.prefix) / "python.exe"
    if candidate.is_file():
        return candidate.resolve()
    return Path(sys.executable).resolve()


def python_command(script: str) -> list[str]:
    return [
        str(fixture_python()),
        "-I",
        "-S",
        "-B",
        "-c",
        script,
    ]


def prove(
    repo: Path,
    policy: dict[str, Any],
    process_runner: Callable[..., dict[str, Any]] = isolated_process.run,
) -> dict[str, Any]:
    repo = repo.resolve()
    if not repo.is_dir():
        raise ValueError("Repository path must be an existing directory")
    launcher_policy = isolated_process.load_policy()
    environment = parent_environment(launcher_policy)
    dual = policy["fixtures"]["dual_stream"]
    dual_execution = process_runner(
        python_command(
            "import sys;"
            f"sys.stdout.buffer.write(b'O'*{dual['stdout_bytes']});"
            "sys.stdout.buffer.flush();"
            f"sys.stderr.buffer.write(b'E'*{dual['stderr_bytes']});"
            "sys.stderr.buffer.flush()"
        ),
        repo,
        environment,
        launcher_policy,
        policy["timeout_seconds"],
    )
    expected_stdout = b"O" * dual["stdout_bytes"]
    expected_stderr = b"E" * dual["stderr_bytes"]
    dual_matched = (
        dual_execution.get("completed") is True
        and dual_execution.get("capture_complete") is True
        and dual_execution.get("returncode") == 0
        and dual_execution.get("stdout") == expected_stdout
        and dual_execution.get("stderr") == expected_stderr
        and dual_execution.get("captured_stdout_bytes") == len(expected_stdout)
        and dual_execution.get("captured_stderr_bytes") == len(expected_stderr)
    )
    limit_fixture = policy["fixtures"]["output_limit"]
    limit_execution = process_runner(
        python_command(
            "import sys;"
            f"sys.stdout.buffer.write(b'X'*{limit_fixture['attempted_stdout_bytes']});"
            "sys.stdout.buffer.flush()"
        ),
        repo,
        environment,
        launcher_policy,
        policy["timeout_seconds"],
    )
    captured_before_rejection = limit_execution.get("captured_stdout_bytes", 0) + (
        limit_execution.get("captured_stderr_bytes", 0)
    )
    limit_matched = (
        limit_execution.get("output_limit_exceeded") is True
        and limit_execution.get("capture_complete") is False
        and limit_execution.get("direct_child_reaped") is True
        and limit_execution.get("stdout") == b""
        and limit_execution.get("stderr") == b""
        and captured_before_rejection <= launcher_policy["max_captured_output_bytes"]
    )
    verified = dual_matched and limit_matched
    bindings = initialize_portable_run.binding_records(policy["bindings"])
    return {
        "proof_version": policy["version"],
        "purpose": policy["purpose"],
        "mode": policy["mode"],
        **{field: False for field in FALSE_FIELDS},
        "proof_complete": True,
        "scope": {
            "exact_launcher": ".agent/checks/isolated_process.py",
            "concurrent_stdout_stderr": True,
            "bounded_pending_chunk_queue": True,
            "uses_shell": False,
            "invokes_agent": False,
            "validates_implementation_output": False,
            "descendant_process_tree_cleanup_tested": False,
        },
        "fixtures": [
            {
                "id": "dual_stream",
                "matched": dual_matched,
                "capture_complete": dual_execution.get("capture_complete") is True,
                "returncode": dual_execution.get("returncode"),
                "stdout_bytes": dual_execution.get("captured_stdout_bytes"),
                "stderr_bytes": dual_execution.get("captured_stderr_bytes"),
                "stdout_sha256": sha256_bytes(dual_execution.get("stdout", b"")),
                "stderr_sha256": sha256_bytes(dual_execution.get("stderr", b"")),
            },
            {
                "id": "output_limit",
                "matched": limit_matched,
                "output_limit_exceeded": (
                    limit_execution.get("output_limit_exceeded") is True
                ),
                "direct_child_reaped": limit_execution.get("direct_child_reaped") is True,
                "partial_output_returned": bool(
                    limit_execution.get("stdout") or limit_execution.get("stderr")
                ),
                "captured_bytes_before_rejection": captured_before_rejection,
                "configured_capture_limit_bytes": (
                    launcher_policy["max_captured_output_bytes"]
                ),
                "capture_memory_bound_bytes": (
                    limit_execution.get("capture_memory_bound_bytes")
                ),
            },
        ],
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
        "bindings": bindings,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def format_text(result: dict[str, Any]) -> str:
    assessment = result["control_assessments"][0]["assessment"]
    lines = [
        f"bounded-output-capture-proof: {assessment.upper()}",
        "runner_selected=false",
        "agent_invocation_authorized=false",
    ]
    lines.extend(
        f"- {fixture['id']}: {'matched' if fixture['matched'] else 'not_matched'}"
        for fixture in result["fixtures"]
    )
    lines.extend(
        f"- {item['id']}: {item['assessment']}"
        for item in result["control_assessments"][1:]
    )
    return "\n".join(lines)


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = prove(args.repo, load_policy())
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        print(f"bounded-output-capture-proof: ERROR\n- {error}", file=sys.stderr)
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
