#!/usr/bin/env python3
"""Build a run-metrics observation from a validated supervised-runner receipt."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import build_stage_context
import record_run_metrics
import validate_supervised_runner_receipt


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / ".agent" / "policies" / "runner-metrics-observation.json"
FALSE_FIELDS = record_run_metrics.FALSE_FIELDS

EXPECTED_POLICY: dict[str, Any] = {
    "version": 1,
    "purpose": "runner_metrics_observation_builder",
    "mode": "receipt-derived-observation-only",
    "max_receipt_bytes": 50000,
    "require_external_receipt": True,
    "require_external_output": True,
    "require_absent_output": True,
    "default_tokens_status": "unavailable",
    "default_cost_status": "unavailable",
    "default_human_corrections_status": "not_assessed",
    "default_final_disposition": "pending",
    "default_regression_status": "not_assessed",
    "bindings": [
        ".agent/checks/build_runner_metrics_observation.py",
        ".agent/policies/runner-metrics-observation.json",
        ".agent/checks/validate_supervised_runner_receipt.py",
        ".agent/policies/supervised-runner-receipt-validation.json",
        ".agent/checks/record_run_metrics.py",
        ".agent/policies/run-metrics.json",
    ],
}


def load_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    policy = json.loads(path.read_text(encoding="utf-8"))
    if policy != EXPECTED_POLICY:
        raise ValueError("Runner metrics observation policy does not match")
    return policy


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def write_exclusive(path: Path, content: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())


def validate_paths(repo_root: Path, receipt: Path, output: Path, policy: dict[str, Any]) -> tuple[Path, Path]:
    if receipt.is_symlink() or not receipt.is_file():
        raise ValueError("Final receipt must be an existing regular file")
    if output.is_symlink():
        raise ValueError("Observation output symbolic links are not allowed")
    receipt = receipt.resolve()
    output = output.resolve()
    if policy["require_external_receipt"] and build_stage_context.is_within(receipt, repo_root):
        raise ValueError("Final receipt must be outside the Git checkout")
    if policy["require_external_output"] and build_stage_context.is_within(output, repo_root):
        raise ValueError("Observation output must be outside the Git checkout")
    if policy["require_absent_output"] and output.exists():
        raise ValueError("Observation output already exists")
    if not output.parent.is_dir():
        raise ValueError("Observation output parent must exist")
    return receipt, output


def load_valid_receipt(receipt: Path, receipt_sha256: str, policy: dict[str, Any]) -> dict[str, Any]:
    if len(receipt.read_bytes()) > policy["max_receipt_bytes"]:
        raise ValueError("Final receipt exceeds max_receipt_bytes")
    validation = validate_supervised_runner_receipt.validate(
        receipt,
        receipt_sha256,
        validate_supervised_runner_receipt.load_policy(),
    )
    if validation.get("valid") is not True:
        raise ValueError("Final receipt did not validate")
    content = receipt.read_bytes()
    if record_run_metrics.sha256_bytes(content) != receipt_sha256:
        raise ValueError("Final receipt SHA-256 does not match after validation")
    return json.loads(content.decode("utf-8-sig"))


def require_identity(receipt: dict[str, Any]) -> dict[str, Any]:
    identity = receipt.get("identity")
    if not isinstance(identity, dict):
        raise ValueError("Final receipt identity is required for metrics observation")
    required = {"issue", "base_commit", "runner_id"}
    if not required <= set(identity):
        raise ValueError("Final receipt identity is missing required metrics fields")
    if type(identity["issue"]) is not int or identity["issue"] < 1:
        raise ValueError("Final receipt issue is invalid")
    if (
        type(identity["base_commit"]) is not str
        or record_run_metrics.COMMIT.fullmatch(identity["base_commit"]) is None
    ):
        raise ValueError("Final receipt base_commit is invalid")
    record_run_metrics.require_identifier(identity["runner_id"], "identity.runner_id")
    return identity


def derive_outcome(receipt: dict[str, Any]) -> str:
    if receipt["runner_complete"] is True:
        return "succeeded"
    if receipt["stage"] in {"quality_gate", "quality_gate_validation", "cleanup", "cleanup_validation"}:
        return "failed"
    return "blocked"


def derive_patch(receipt: dict[str, Any]) -> tuple[str, str | None]:
    artifacts = receipt.get("artifacts")
    if not isinstance(artifacts, dict) or "patch" not in artifacts:
        return "not_applicable", None
    patch = artifacts["patch"]
    if not isinstance(patch, dict) or type(patch.get("sha256")) is not str:
        raise ValueError("Final receipt patch artifact is malformed")
    patch_sha256 = patch["sha256"]
    if record_run_metrics.SHA256.fullmatch(patch_sha256) is None:
        raise ValueError("Final receipt patch SHA-256 is invalid")
    return "measured", patch_sha256


def build_observation(
    repo: Path,
    receipt: Path,
    receipt_sha256: str,
    output: Path,
    run_id: str,
    started_at: str,
    completed_at: str,
    model_provider: str,
    model_id: str,
    policy: dict[str, Any],
) -> tuple[dict[str, Any], bytes]:
    repo_root = Path(
        record_run_metrics.diff_policy.run_git(repo, "rev-parse", "--show-toplevel")
        .decode("utf-8")
        .strip()
    ).resolve()
    receipt, _output = validate_paths(repo_root, receipt, output, policy)
    if record_run_metrics.RUN_ID.fullmatch(run_id) is None:
        raise ValueError("run-id must match the run metrics contract")
    record_run_metrics.parse_timestamp(started_at, "started-at")
    record_run_metrics.parse_timestamp(completed_at, "completed-at")
    record_run_metrics.require_identifier(model_provider, "model-provider")
    record_run_metrics.require_identifier(model_id, "model-id")

    final_receipt = load_valid_receipt(receipt, receipt_sha256, policy)
    identity = require_identity(final_receipt)
    diff_status, patch_sha256 = derive_patch(final_receipt)
    observation = {
        "observation_version": record_run_metrics.EXPECTED_POLICY["version"],
        "purpose": "agentic_run_metrics_observation",
        "mode": "post-run-observation",
        "run_id": run_id,
        "issue": identity["issue"],
        "stage": "implement",
        "base_commit": identity["base_commit"],
        "adapter": {
            "id": identity["runner_id"],
            "version": "supervised-runner-final-receipt",
        },
        "model": {
            "provider": model_provider,
            "id": model_id,
        },
        "timing": {
            "started_at": started_at,
            "completed_at": completed_at,
        },
        "tokens": {
            "status": policy["default_tokens_status"],
            "source": "unavailable",
            "input_tokens": None,
            "output_tokens": None,
        },
        "cost": {
            "status": policy["default_cost_status"],
            "source": "unavailable",
            "amount_microunits": None,
            "currency": None,
        },
        "outcome": {
            "status": derive_outcome(final_receipt),
        },
        "human_corrections": {
            "status": policy["default_human_corrections_status"],
            "count": None,
        },
        "final_disposition": policy["default_final_disposition"],
        "regression_status": policy["default_regression_status"],
        "diff_status": diff_status,
        "patch_sha256": patch_sha256,
    }
    record_run_metrics.validate_observation(json.loads(json.dumps(observation)), record_run_metrics.load_policy())
    content = canonical_bytes(observation)
    if len(content) > record_run_metrics.load_policy()["max_observation_bytes"]:
        raise ValueError("Derived observation exceeds max_observation_bytes")
    return observation, content


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--final-receipt", type=Path, required=True)
    parser.add_argument("--final-receipt-sha256", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--started-at", required=True)
    parser.add_argument("--completed-at", required=True)
    parser.add_argument("--model-provider", required=True)
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def format_text(result: dict[str, Any]) -> str:
    return "\n".join(
        [
            "runner-metrics-observation: PRODUCED",
            f"run_id={result['observation']['run_id']}",
            f"outcome={result['observation']['outcome']['status']}",
            f"diff_status={result['observation']['diff_status']}",
            f"observation_sha256={result['observation_sha256']}",
            "authorized=false",
        ]
    )


def main() -> int:
    args = build_parser().parse_args()
    try:
        policy = load_policy()
        observation, content = build_observation(
            args.repo,
            args.final_receipt,
            args.final_receipt_sha256,
            args.output,
            args.run_id,
            args.started_at,
            args.completed_at,
            args.model_provider,
            args.model_id,
            policy,
        )
        write_exclusive(args.output.resolve(), content)
        result = {
            "produced": True,
            "output": str(args.output.resolve()),
            "observation_sha256": record_run_metrics.sha256_bytes(content),
            "observation_size_bytes": len(content),
            "observation": observation,
            **{field: False for field in FALSE_FIELDS},
        }
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        print(f"runner-metrics-observation: ERROR\n- {error}", file=sys.stderr)
        return 1
    if args.format == "json":
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(format_text(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
