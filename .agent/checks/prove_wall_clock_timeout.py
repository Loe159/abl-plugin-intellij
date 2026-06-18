#!/usr/bin/env python3
"""Prove a bounded post-spawn timeout for one harmless direct child process."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / ".agent" / "policies" / "wall-clock-timeout-proof.json"
FALSE_FIELDS = (
    "authorized",
    "agent_invocation_authorized",
    "implementation_authorized",
    "runner_selected",
    "session_start_authorized",
)

EXPECTED_POLICY: dict[str, Any] = {
    "version": 1,
    "purpose": "post_spawn_direct_child_timeout_proof",
    "mode": "fixture-only",
    "timeout_seconds": 0.5,
    "cleanup_timeout_seconds": 2.0,
    "max_observed_seconds": 3.0,
    "fixtures": [
        {
            "id": "fast_control",
            "script": "raise SystemExit(0)",
            "expected": "completed",
        },
        {
            "id": "sleeping_child",
            "script": "import time; time.sleep(10)",
            "expected": "timed_out_and_reaped",
        },
    ],
    "proven_control": "post_spawn_direct_child_timeout",
    "unproven_controls": [
        "descendant_process_tree_timeout",
        "implementation_session_wall_clock_timeout",
        "process_spawn_timeout",
    ],
}


def load_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    policy = json.loads(path.read_text(encoding="utf-8"))
    if policy != EXPECTED_POLICY:
        raise ValueError("Wall-clock-timeout proof policy does not match the fixture-only contract")
    return policy


def child_command(script: str) -> list[str]:
    return [sys.executable, "-I", "-S", "-B", "-c", script]


def observe_fixture(
    fixture: dict[str, str],
    repo: Path,
    policy: dict[str, Any],
    popen: Callable[..., subprocess.Popen[Any]] = subprocess.Popen,
    clock: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    try:
        process = popen(
            child_command(fixture["script"]),
            cwd=repo,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=False,
        )
    except OSError:
        return {
            "id": fixture["id"],
            "expected": fixture["expected"],
            "observation": "spawn_error",
            "matched": False,
            "timed_out": False,
            "kill_requested": False,
            "direct_child_reaped": False,
            "returncode": None,
            "observed_seconds": None,
            "within_observed_bound": False,
        }

    started = clock()
    timed_out = False
    kill_requested = False
    direct_child_reaped = False
    returncode = None
    observation = "completed"
    try:
        returncode = process.wait(timeout=policy["timeout_seconds"])
        direct_child_reaped = True
        if returncode != 0:
            observation = "nonzero"
    except subprocess.TimeoutExpired:
        timed_out = True
        observation = "timed_out"
        try:
            process.kill()
            kill_requested = True
            returncode = process.wait(timeout=policy["cleanup_timeout_seconds"])
            direct_child_reaped = True
            observation = "timed_out_and_reaped"
        except (OSError, subprocess.TimeoutExpired):
            observation = "cleanup_failed"
    elapsed = clock() - started
    within_bound = elapsed <= policy["max_observed_seconds"]
    matched = observation == fixture["expected"] and within_bound
    return {
        "id": fixture["id"],
        "expected": fixture["expected"],
        "observation": observation,
        "matched": matched,
        "timed_out": timed_out,
        "kill_requested": kill_requested,
        "direct_child_reaped": direct_child_reaped,
        "returncode": returncode,
        "observed_seconds": round(elapsed, 6),
        "within_observed_bound": within_bound,
    }


def prove(
    repo: Path,
    policy: dict[str, Any],
    popen: Callable[..., subprocess.Popen[Any]] = subprocess.Popen,
    clock: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    repo = repo.resolve()
    if not repo.is_dir():
        raise ValueError("Repository path must be an existing directory")
    observations = [
        observe_fixture(fixture, repo, policy, popen, clock) for fixture in policy["fixtures"]
    ]
    verified = all(item["matched"] for item in observations)
    return {
        "proof_version": policy["version"],
        "purpose": policy["purpose"],
        "mode": policy["mode"],
        **{field: False for field in FALSE_FIELDS},
        "proof_complete": True,
        "scope": {
            "starts_after_process_spawn": True,
            "direct_child_only": True,
            "uses_shell": False,
            "invokes_agent": False,
            "writes_files": False,
        },
        "fixtures": observations,
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
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def format_text(result: dict[str, Any]) -> str:
    assessment = result["control_assessments"][0]["assessment"]
    lines = [
        f"wall-clock-timeout-proof: {assessment.upper()}",
        "runner_selected=false",
        "agent_invocation_authorized=false",
    ]
    lines.extend(
        f"- {item['id']}: {item['observation']}" for item in result["fixtures"]
    )
    lines.extend(
        f"- {item['id']}: {item['assessment']}" for item in result["control_assessments"][1:]
    )
    return "\n".join(lines)


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = prove(args.repo, load_policy())
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        print(f"wall-clock-timeout-proof: ERROR\n- {error}", file=sys.stderr)
        return 1
    if args.format == "json":
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(format_text(result))
    return 0 if result["control_assessments"][0]["assessment"] == "verified_fixture" else 2


if __name__ == "__main__":
    raise SystemExit(main())
