#!/usr/bin/env python3
"""Prove one local exclusive claim-before-spawn fixture."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable

import isolated_process
import validate_implementation_result


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = (
    REPO_ROOT
    / ".agent"
    / "policies"
    / "implementation-launch-transaction-proof.json"
)
FALSE_FIELDS = (
    "authorized",
    "agent_invocation_authorized",
    "implementation_authorized",
    "runner_selected",
    "session_start_authorized",
)

EXPECTED_POLICY: dict[str, Any] = {
    "version": 1,
    "purpose": "implementation_launch_transaction_mechanism_proof",
    "mode": "fixture-only",
    "claim_suffix": ".launch-claimed.json",
    "marker_content": "synthetic-valid-consumption-marker\n",
    "child_stdout": "synthetic-launch-child-started\n",
    "child_timeout_seconds": 2.0,
    "max_claim_bytes": 4000,
    "proven_control": "local_exclusive_claim_before_direct_child_spawn_fixture",
    "unproven_controls": [
        "authorization_consumption_to_process_start",
        "agent_process_invocation",
        "crash_atomicity",
        "cross_host_replay_prevention",
    ],
}


def load_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    policy = json.loads(path.read_text(encoding="utf-8"))
    if policy != EXPECTED_POLICY:
        raise ValueError("Implementation launch-transaction proof policy does not match")
    return policy


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def claim_path(marker: Path, policy: dict[str, Any]) -> Path:
    return marker.with_name(marker.name + policy["claim_suffix"])


def claim_then_spawn(
    marker: Path,
    expected_marker_sha256: str,
    command: list[str],
    cwd: Path,
    policy: dict[str, Any],
    process_runner: Callable[..., dict[str, Any]] = isolated_process.run,
) -> dict[str, Any]:
    if marker.is_symlink() or not marker.is_file():
        raise ValueError("Synthetic consumption marker must be a regular file")
    marker_bytes = marker.read_bytes()
    if validate_implementation_result.sha256_bytes(marker_bytes) != expected_marker_sha256:
        return {
            "claimed": False,
            "spawn_attempted": False,
            "execution": None,
            "failure": "marker_sha256",
        }
    claim = claim_path(marker, policy)
    if claim.is_symlink():
        raise ValueError("Synthetic launch claim symlinks are not allowed")
    claim_value = {
        "claim_version": policy["version"],
        "purpose": policy["purpose"],
        "mode": policy["mode"],
        **{field: False for field in FALSE_FIELDS},
        "marker": str(marker.resolve()),
        "marker_sha256": expected_marker_sha256,
        "claim_created": True,
        "direct_child_spawn_requested": True,
    }
    claim_bytes = canonical_bytes(claim_value)
    if len(claim_bytes) > policy["max_claim_bytes"]:
        raise ValueError("Synthetic launch claim exceeds byte limit")
    try:
        with claim.open("xb") as stream:
            stream.write(claim_bytes)
    except FileExistsError:
        return {
            "claimed": False,
            "spawn_attempted": False,
            "execution": None,
            "failure": "already_claimed",
        }
    execution = process_runner(
        command,
        cwd,
        os.environ,
        isolated_process.load_policy(),
        policy["child_timeout_seconds"],
    )
    return {
        "claimed": True,
        "spawn_attempted": True,
        "execution": execution,
        "failure": None,
        "claim": str(claim),
        "claim_sha256": validate_implementation_result.sha256_bytes(claim_bytes),
    }


def child_command(policy: dict[str, Any]) -> list[str]:
    output = policy["child_stdout"].encode("utf-8")
    script = f"import sys; sys.stdout.buffer.write({output!r})"
    return [sys.executable, "-I", "-S", "-B", "-c", script]


def prove(repo: Path, policy: dict[str, Any]) -> dict[str, Any]:
    repo = repo.resolve()
    if not repo.is_dir():
        raise ValueError("Repository path must be an existing directory")
    with tempfile.TemporaryDirectory() as temp_dir:
        temp = Path(temp_dir)
        marker = temp / "authorization.consumed.json"
        marker_bytes = policy["marker_content"].encode("utf-8")
        marker.write_bytes(marker_bytes)
        marker_sha256 = validate_implementation_result.sha256_bytes(marker_bytes)
        command = child_command(policy)
        first = claim_then_spawn(marker, marker_sha256, command, temp, policy)
        second = claim_then_spawn(marker, marker_sha256, command, temp, policy)

        execution = first.get("execution") or {}
        first_matched = (
            first.get("claimed") is True
            and first.get("spawn_attempted") is True
            and execution.get("completed") is True
            and execution.get("capture_complete") is True
            and execution.get("returncode") == 0
            and execution.get("stdout") == policy["child_stdout"].encode("utf-8")
            and execution.get("stderr") == b""
        )
        replay_matched = (
            second.get("claimed") is False
            and second.get("spawn_attempted") is False
            and second.get("failure") == "already_claimed"
        )
        claim = claim_path(marker, policy)
        claim_preserved = claim.is_file()
    verified = first_matched and replay_matched and claim_preserved
    return {
        "proof_version": policy["version"],
        "purpose": policy["purpose"],
        "mode": policy["mode"],
        **{field: False for field in FALSE_FIELDS},
        "proof_complete": True,
        "scope": {
            "synthetic_marker_only": True,
            "exclusive_local_claim": True,
            "claim_precedes_spawn": True,
            "direct_child_only": True,
            "uses_isolated_process": True,
            "invokes_agent": False,
            "cross_host": False,
            "crash_atomic": False,
        },
        "observations": {
            "first_claim_and_spawn_matched": first_matched,
            "ordinary_replay_blocked_before_spawn": replay_matched,
            "claim_preserved_after_child": claim_preserved,
        },
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
        f"implementation-launch-transaction-proof: {assessment.upper()}",
        "runner_selected=false",
        "agent_invocation_authorized=false",
    ]
    lines.extend(
        f"- {name}: {str(value).lower()}"
        for name, value in result["observations"].items()
    )
    return "\n".join(lines)


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = prove(args.repo, load_policy())
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        print(f"implementation-launch-transaction-proof: ERROR\n- {error}", file=sys.stderr)
        return 1
    if args.format == "json":
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(format_text(result))
    return 0 if result["control_assessments"][0]["assessment"] == "verified_fixture" else 2


if __name__ == "__main__":
    raise SystemExit(main())
