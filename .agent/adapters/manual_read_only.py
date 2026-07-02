#!/usr/bin/env python3
"""Prepare and validate a manual read-only stage without executing an agent."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
CHECKS_DIR = REPO_ROOT / ".agent" / "checks"
sys.path.insert(0, str(CHECKS_DIR))

import build_stage_context  # noqa: E402
import check_stage_readiness  # noqa: E402
import diff_policy  # noqa: E402
import validate_artifacts  # noqa: E402
import validate_prompts  # noqa: E402
import validate_stage_output  # noqa: E402


def load_adapter_policy(
    path: Path,
    context_policy: dict[str, Any],
    output_policy: dict[str, Any],
) -> dict[str, Any]:
    policy = json.loads(path.read_text(encoding="utf-8"))
    if set(policy) != {"version", "adapter", "supported_stages", "safety"}:
        raise ValueError("Manual adapter policy fields do not match the contract")
    if (
        not isinstance(policy["version"], int)
        or isinstance(policy["version"], bool)
        or policy["version"] != 1
    ):
        raise ValueError(f"Unsupported manual adapter policy version: {policy['version']}")
    if policy["adapter"] != "manual-read-only":
        raise ValueError("Manual adapter name must be manual-read-only")
    expected_stages = sorted(context_policy["stages"])
    if (
        not isinstance(policy["supported_stages"], list)
        or not all(isinstance(stage, str) for stage in policy["supported_stages"])
        or len(policy["supported_stages"]) != len(set(policy["supported_stages"]))
        or sorted(policy["supported_stages"]) != expected_stages
        or sorted(output_policy["stages"]) != expected_stages
    ):
        raise ValueError("Manual adapter stages must exactly match read-only stage policies")
    expected_safety = {
        "invokes_agent": False,
        "mutates_run": False,
        "applies_response": False,
        "authorizes": False,
    }
    if policy["safety"] != expected_safety:
        raise ValueError("Manual adapter safety flags must all be explicitly false")
    return policy


def load_policies() -> dict[str, Any]:
    policy_dir = REPO_ROOT / ".agent" / "policies"
    artifact = validate_artifacts.load_contract(policy_dir / "artifact-contract.json")
    prompt = validate_prompts.load_prompt_contract(
        policy_dir / "prompt-contract.json",
        artifact,
    )
    context = build_stage_context.load_context_policy(
        policy_dir / "stage-context.json",
        prompt,
        artifact,
    )
    output = validate_stage_output.load_output_policy(
        policy_dir / "stage-output.json",
        context,
        prompt,
        artifact,
    )
    return {
        "artifact": artifact,
        "prompt": prompt,
        "readiness": check_stage_readiness.load_readiness_policy(
            policy_dir / "stage-readiness.json",
            artifact,
        ),
        "context": context,
        "output": output,
        "diff": diff_policy.load_policy(policy_dir / "diff-policy.json"),
        "adapter": load_adapter_policy(
            policy_dir / "manual-read-only-adapter.json",
            context,
            output,
        ),
    }


def envelope(policy: dict[str, Any], action: str, result: dict[str, Any]) -> dict[str, Any]:
    return {
        "adapter_contract_version": policy["version"],
        "adapter": policy["adapter"],
        "action": action,
        "mode": "read-only",
        "agent_invoked": False,
        "run_mutated": False,
        "response_applied": False,
        "authorized": False,
        "result": result,
    }


def prepare(args: argparse.Namespace, policies: dict[str, Any]) -> dict[str, Any]:
    result = build_stage_context.build_context(
        args.repo,
        args.run,
        args.stage,
        args.bundle,
        policies,
        REPO_ROOT / ".agent" / "prompts",
        args.approval_receipt,
        args.approval_receipt_sha256,
        args.application_receipt,
        args.application_receipt_sha256,
    )
    return envelope(policies["adapter"], "prepare", result)


def validate(args: argparse.Namespace, policies: dict[str, Any]) -> dict[str, Any]:
    result = validate_stage_output.validate_output(
        args.bundle,
        args.bundle_sha256,
        args.response,
        args.repo,
        policies,
        REPO_ROOT / ".agent" / "prompts",
    )
    return envelope(policies["adapter"], "validate", result)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="action", required=True)

    prepare_parser = subparsers.add_parser(
        "prepare",
        help="Build a bounded external bundle and report its digest",
    )
    prepare_parser.add_argument("--repo", type=Path, required=True)
    prepare_parser.add_argument("--run", type=Path, required=True)
    prepare_parser.add_argument(
        "--stage",
        choices=("research", "plan", "compact-progress", "review"),
        required=True,
    )
    prepare_parser.add_argument("--bundle", type=Path, required=True)
    prepare_parser.add_argument("--approval-receipt", type=Path)
    prepare_parser.add_argument("--approval-receipt-sha256")
    prepare_parser.add_argument("--application-receipt", type=Path)
    prepare_parser.add_argument("--application-receipt-sha256")

    validate_parser = subparsers.add_parser(
        "validate",
        help="Validate a captured response using an explicitly supplied bundle digest",
    )
    validate_parser.add_argument("--repo", type=Path, required=True)
    validate_parser.add_argument("--bundle", type=Path, required=True)
    validate_parser.add_argument("--bundle-sha256", required=True)
    validate_parser.add_argument("--response", type=Path, required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        policies = load_policies()
        result = prepare(args, policies) if args.action == "prepare" else validate(args, policies)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        print(f"manual-read-only: ERROR\n- {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    operation = result["result"]
    if args.action == "prepare":
        return 0 if operation["produced"] else 2
    return 0 if operation["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
