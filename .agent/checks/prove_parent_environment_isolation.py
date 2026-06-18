#!/usr/bin/env python3
"""Prove the exact launcher excludes sensitive parent-environment variables."""

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
POLICY_PATH = REPO_ROOT / ".agent" / "policies" / "parent-environment-isolation-proof.json"
FALSE_FIELDS = (
    "authorized",
    "agent_invocation_authorized",
    "implementation_authorized",
    "runner_selected",
    "session_start_authorized",
)

EXPECTED_POLICY: dict[str, Any] = {
    "version": 1,
    "purpose": "parent_environment_credential_isolation_proof",
    "mode": "enforcement-proof",
    "timeout_seconds": 5.0,
    "sensitive_variable_names": [
        "AWS_SECRET_ACCESS_KEY",
        "AZURE_CLIENT_SECRET",
        "CODEX_HOME",
        "GH_TOKEN",
        "GITHUB_TOKEN",
        "OPENAI_API_KEY",
    ],
    "required_child_variables": [
        "AGENT_RUNNER_ENVIRONMENT_MODE",
        "PYTHONIOENCODING",
        "PYTHONUTF8",
    ],
    "expected_child_environment_mode": "isolated",
    "proven_control": "parent_environment_credential_isolation",
    "unproven_controls": [
        "provider_credential_descendant_noninheritance",
        "credential_file_isolation",
        "operating_system_credential_store_isolation",
    ],
    "bindings": [
        ".agent/checks/isolated_process.py",
        ".agent/policies/parent-environment-isolation.json",
        ".agent/checks/prove_parent_environment_isolation.py",
        ".agent/policies/parent-environment-isolation-proof.json",
    ],
}


def load_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    policy = json.loads(path.read_text(encoding="utf-8"))
    if policy != EXPECTED_POLICY:
        raise ValueError("Parent-environment isolation proof policy does not match")
    return policy


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def probe_script() -> str:
    return (
        "import json,os,sys;"
        "names=json.loads(sys.argv[1]);"
        "required=json.loads(sys.argv[2]);"
        "print(json.dumps({'sensitive_present':[n for n in names if n in os.environ],"
        "'required_present':[n for n in required if n in os.environ],"
        "'mode':os.environ.get('AGENT_RUNNER_ENVIRONMENT_MODE')},sort_keys=True))"
    )


def fixture_parent_environment(
    parent: dict[str, str],
    sensitive_names: list[str],
) -> dict[str, str]:
    fixture = dict(parent)
    for index, name in enumerate(sensitive_names):
        fixture[name] = f"synthetic-isolation-marker-{index}"
    return fixture


def prove(
    repo: Path,
    policy: dict[str, Any],
    parent_environment: dict[str, str] | None = None,
    process_runner: Callable[..., dict[str, Any]] = isolated_process.run,
) -> dict[str, Any]:
    repo = repo.resolve()
    if not repo.is_dir():
        raise ValueError("Repository path must be an existing directory")
    launcher_policy = isolated_process.load_policy()
    sensitive_names = policy["sensitive_variable_names"]
    required_names = policy["required_child_variables"]
    source_parent = (
        {
            name: os.environ[name]
            for name in launcher_policy["allowed_parent_variables"]
            if name in os.environ
        }
        if parent_environment is None
        else parent_environment
    )
    parent = fixture_parent_environment(source_parent, sensitive_names)
    command = [
        str(Path(sys.executable).resolve()),
        "-I",
        "-S",
        "-B",
        "-c",
        probe_script(),
        json.dumps(sensitive_names),
        json.dumps(required_names),
    ]
    execution = process_runner(
        command,
        repo,
        parent,
        launcher_policy,
        policy["timeout_seconds"],
    )
    observation = {
        "completed": execution.get("completed") is True,
        "timed_out": execution.get("timed_out") is True,
        "returncode": execution.get("returncode"),
        "capture_complete": execution.get("capture_complete") is True,
        "sensitive_names_tested": len(sensitive_names),
        "sensitive_names_present": [],
        "required_names_present": [],
        "mode": None,
        "stdout_sha256": sha256_bytes(execution.get("stdout", b"")),
        "stderr_sha256": sha256_bytes(execution.get("stderr", b"")),
    }
    parsed: dict[str, Any] | None = None
    if (
        observation["completed"]
        and not observation["timed_out"]
        and observation["returncode"] == 0
        and observation["capture_complete"]
    ):
        try:
            parsed = json.loads(execution["stdout"].decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError):
            parsed = None
    if isinstance(parsed, dict):
        observation["sensitive_names_present"] = parsed.get("sensitive_present", [])
        observation["required_names_present"] = parsed.get("required_present", [])
        observation["mode"] = parsed.get("mode")
    verified = (
        parsed is not None
        and observation["sensitive_names_present"] == []
        and observation["required_names_present"] == required_names
        and observation["mode"] == policy["expected_child_environment_mode"]
    )
    bindings = initialize_portable_run.binding_records(policy["bindings"])
    return {
        "proof_version": policy["version"],
        "purpose": policy["purpose"],
        "mode": policy["mode"],
        **{field: False for field in FALSE_FIELDS},
        "proof_complete": True,
        "scope": {
            "exact_launcher": ".agent/checks/isolated_process.py",
            "parent_environment_reconstructed": True,
            "uses_shell": False,
            "invokes_agent": False,
            "compares_sensitive_values": False,
            "emits_sensitive_values": False,
            "provider_descendant_boundary_tested": False,
        },
        "observation": observation,
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
        f"parent-environment-isolation-proof: {assessment.upper()}",
        "runner_selected=false",
        "agent_invocation_authorized=false",
        f"- sensitive_names_tested: {result['observation']['sensitive_names_tested']}",
        f"- sensitive_names_present: {len(result['observation']['sensitive_names_present'])}",
    ]
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
        print(f"parent-environment-isolation-proof: ERROR\n- {error}", file=sys.stderr)
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
