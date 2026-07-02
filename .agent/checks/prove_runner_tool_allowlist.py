#!/usr/bin/env python3
"""Prove supervised-runner adapter command allowlisting on bounded fixtures."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any
from unittest import mock

import initialize_portable_run
import run_supervised_implementation


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / ".agent" / "policies" / "runner-tool-allowlist-proof.json"
FALSE_FIELDS = (
    "authorized",
    "agent_invocation_authorized",
    "implementation_authorized",
    "runner_selected",
    "session_start_authorized",
    "publication_authorized",
    "network_authorized",
    "merge_authorized",
)

EXPECTED_POLICY: dict[str, Any] = {
    "version": 1,
    "purpose": "runner_tool_allowlist_enforcement_proof",
    "mode": "enforcement-proof",
    "proven_control": "tool_allowlist",
    "bindings": [
        ".agent/checks/prove_runner_tool_allowlist.py",
        ".agent/policies/runner-tool-allowlist-proof.json",
        ".agent/checks/run_supervised_implementation.py",
        ".agent/policies/supervised-implementation-runner.json",
        ".agent/adapters/local_implementation_adapter.py",
        ".agent/policies/local-implementation-adapter.json",
    ],
}


def load_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    policy = json.loads(path.read_text(encoding="utf-8"))
    if policy != EXPECTED_POLICY:
        raise ValueError("Runner tool-allowlist proof policy does not match")
    return policy


def output_paths(temp: Path) -> dict[str, Path]:
    out = temp / "out"
    out.mkdir(parents=True)
    return {
        "expected_session": out / "expected-session.json",
        "result": out / "result.json",
        "patch": out / "patch.diff",
        "patch_receipt": out / "patch-receipt.json",
        "quality_gate": out / "quality-gate.json",
        "final": out / "final-receipt.json",
        "gradle_home": out / "gradle-home",
    }


def allowed_adapter_command() -> list[str]:
    return [
        sys.executable,
        str(REPO_ROOT / ".agent" / "adapters" / "local_implementation_adapter.py"),
    ]


def blocked_before_consumption(temp: Path) -> dict[str, Any]:
    outputs = output_paths(temp / "blocked")
    workspace = temp / "workspace"
    workspace.mkdir()
    consumption_runner = mock.Mock()
    adapter_runner = mock.Mock()
    result = run_supervised_implementation.run_supervised(
        REPO_ROOT,
        temp / "proposal.json",
        "0" * 64,
        workspace,
        temp / "worktree.json",
        "1" * 64,
        temp / "approval.json",
        "2" * 64,
        temp / "preflight.json",
        "3" * 64,
        temp / "authorization.json",
        "4" * 64,
        ["not-allowlisted-adapter"],
        outputs["expected_session"],
        outputs["result"],
        outputs["patch"],
        outputs["patch_receipt"],
        outputs["quality_gate"],
        outputs["final"],
        outputs["gradle_home"],
        run_supervised_implementation.load_policy(),
        consumption_runner=consumption_runner,
        adapter_runner=adapter_runner,
        quality_gate_executor=mock.Mock(),
    )
    receipt = json.loads(outputs["final"].read_text(encoding="utf-8"))
    matched = (
        result["stage"] == "adapter_command"
        and result["authorization_consumed"] is False
        and result["adapter_executed"] is False
        and outputs["final"].is_file()
        and receipt["stage"] == "adapter_command"
        and not consumption_runner.called
        and not adapter_runner.called
    )
    return {
        "id": "non_allowlisted_adapter_blocked_before_consumption",
        "matched": matched,
        "stage": result["stage"],
        "authorization_consumed": result["authorization_consumed"],
        "adapter_executed": result["adapter_executed"],
        "final_receipt_written": outputs["final"].is_file(),
    }


def allowlisted_entrypoint_resolves() -> dict[str, Any]:
    entrypoint, normalized_command = run_supervised_implementation.adapter_entrypoint(
        REPO_ROOT,
        [sys.executable, ".agent/adapters/local_implementation_adapter.py"],
        run_supervised_implementation.load_policy(),
    )
    expected_path = str((REPO_ROOT / ".agent" / "adapters" / "local_implementation_adapter.py").resolve())
    matched = (
        entrypoint == ".agent/adapters/local_implementation_adapter.py"
        and normalized_command[1] == expected_path
    )
    return {
        "id": "allowlisted_local_adapter_entrypoint_resolves",
        "matched": matched,
        "entrypoint": entrypoint,
        "entrypoint_path_sha256": run_supervised_implementation.validate_implementation_result.sha256_bytes(
            normalized_command[1].encode("utf-8")
        ),
    }


def prove(repo: Path, policy: dict[str, Any]) -> dict[str, Any]:
    repo = repo.resolve()
    if not repo.is_dir():
        raise ValueError("Repository path must be an existing directory")
    with tempfile.TemporaryDirectory() as temp_dir:
        temp = Path(temp_dir)
        blocked = blocked_before_consumption(temp)
        allowed = allowlisted_entrypoint_resolves()
    enforcement_verified = blocked["matched"] is True and allowed["matched"] is True
    return {
        "proof_version": policy["version"],
        "purpose": policy["purpose"],
        "mode": policy["mode"],
        **{field: False for field in FALSE_FIELDS},
        "proof_complete": True,
        "scope": {
            "executes_adapter": False,
            "invokes_agent": False,
            "consumes_authorization": False,
            "proves_provider_command_behavior": False,
            "proves_network_isolation": False,
        },
        "fixtures": [blocked, allowed],
        "control_assessments": [
            {
                "id": policy["proven_control"],
                "assessment": "verified_enforcement" if enforcement_verified else "not_proven",
            }
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
        f"runner-tool-allowlist-proof: {assessment.upper()}",
        "agent_invocation_authorized=false",
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
        print(f"runner-tool-allowlist-proof: ERROR\n- {error}", file=sys.stderr)
        return 1
    if args.format == "json":
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(format_text(result))
    return 0 if result["control_assessments"][0]["assessment"] == "verified_enforcement" else 2


if __name__ == "__main__":
    raise SystemExit(main())
