#!/usr/bin/env python3
"""Prove the local implementation adapter filters provider env vars for its child."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any
from unittest import mock

import initialize_portable_run
import validate_implementation_result


REPO_ROOT = Path(__file__).resolve().parents[2]
ADAPTER_PATH = REPO_ROOT / ".agent" / "adapters" / "local_implementation_adapter.py"
POLICY_PATH = REPO_ROOT / ".agent" / "policies" / "local-adapter-environment-filter-proof.json"
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
SENSITIVE_NAMES = (
    "ANTHROPIC_API_KEY",
    "AZURE_OPENAI_API_KEY",
    "GITHUB_TOKEN",
    "OPENAI_API_KEY",
)

EXPECTED_POLICY: dict[str, Any] = {
    "version": 1,
    "purpose": "local_adapter_environment_filter_proof",
    "mode": "enforcement-proof",
    "related_control": "provider_credential_descendant_noninheritance",
    "proven_control": "local_adapter_child_environment_filter",
    "sensitive_variable_names": list(SENSITIVE_NAMES),
    "bindings": [
        ".agent/checks/prove_local_adapter_environment_filter.py",
        ".agent/policies/local-adapter-environment-filter-proof.json",
        ".agent/adapters/local_implementation_adapter.py",
        ".agent/policies/local-implementation-adapter.json",
        ".agent/checks/isolated_process.py",
        ".agent/policies/parent-environment-isolation.json",
    ],
}


def load_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    policy = json.loads(path.read_text(encoding="utf-8"))
    if policy != EXPECTED_POLICY:
        raise ValueError("Local adapter environment-filter proof policy does not match")
    return policy


def load_adapter() -> Any:
    spec = importlib.util.spec_from_file_location("local_implementation_adapter", ADAPTER_PATH)
    if spec is None or spec.loader is None:
        raise ValueError("Local implementation adapter module could not be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def init_workspace(parent: Path) -> tuple[Path, Path]:
    workspace = parent / "workspace"
    workspace.mkdir()
    git(workspace, "init")
    git(workspace, "config", "user.email", "adapter-env@example.invalid")
    git(workspace, "config", "user.name", "Adapter Env")
    (workspace / "README.md").write_text("base\n", encoding="utf-8")
    git(workspace, "add", ".")
    git(workspace, "commit", "-m", "base")
    session = {
        "issue": 1,
        "risk": "low",
        "base_commit": git(workspace, "rev-parse", "HEAD"),
        "workspace": str(workspace.resolve()),
        "runner_id": "local-adapter-fixture",
        "preflight_sha256": "1" * 64,
        "start_authorization_receipt_sha256": "2" * 64,
    }
    expected = parent / "expected-session.json"
    expected.write_text(json.dumps(session), encoding="utf-8")
    return workspace, expected


def prove(repo: Path, policy: dict[str, Any]) -> dict[str, Any]:
    repo = repo.resolve()
    if not repo.is_dir():
        raise ValueError("Repository path must be an existing directory")
    adapter = load_adapter()
    with tempfile.TemporaryDirectory() as temp_dir:
        temp = Path(temp_dir)
        workspace, expected = init_workspace(temp)
        script = (
            "import os, sys; "
            f"blocked={list(policy['sensitive_variable_names'])!r}; "
            "present=[name for name in blocked if name in os.environ]; "
            "sys.exit(7) if present else None; "
            "from pathlib import Path; Path('changed.txt').write_text('changed\\n')"
        )
        env = {name: f"fixture-{name.lower()}" for name in policy["sensitive_variable_names"]}
        with mock.patch.dict(os.environ, env):
            content = adapter.run_adapter(
                expected,
                [sys.executable, "-c", script],
                workspace,
                adapter.load_policy(),
            )
        value = json.loads(content.decode("utf-8"))
        matched = value["status"] == "completed" and value["workspace_changed"] is True
    return {
        "proof_version": policy["version"],
        "purpose": policy["purpose"],
        "mode": policy["mode"],
        **{field: False for field in FALSE_FIELDS},
        "proof_complete": True,
        "scope": {
            "executes_local_adapter": True,
            "executes_fixture_child_command": True,
            "checks_environment_variables_only": True,
            "proves_provider_filesystem_credentials_blocked": False,
            "proves_os_credential_store_blocked": False,
            "invokes_agent": False,
            "authorizes_session": False,
        },
        "control_assessments": [
            {
                "id": policy["proven_control"],
                "assessment": "verified_enforcement" if matched else "not_proven",
            }
        ],
        "related_controls": [
            {
                "id": policy["related_control"],
                "assessment": "related_evidence_only" if matched else "not_proven",
            }
        ],
        "fixture": {
            "id": "provider_env_vars_filtered_from_local_adapter_child",
            "matched": matched,
            "sensitive_variable_count": len(policy["sensitive_variable_names"]),
        },
        "bindings": initialize_portable_run.binding_records(policy["bindings"]),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def format_text(result: dict[str, Any]) -> str:
    assessment = result["control_assessments"][0]["assessment"]
    return "\n".join(
        [
            f"local-adapter-environment-filter-proof: {assessment.upper()}",
            "provider_credential_descendant_noninheritance=related_evidence_only",
            "agent_invocation_authorized=false",
        ]
    )


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = prove(args.repo, load_policy())
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        print(f"local-adapter-environment-filter-proof: ERROR\n- {error}", file=sys.stderr)
        return 1
    if args.format == "json":
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(format_text(result))
    return 0 if result["control_assessments"][0]["assessment"] == "verified_enforcement" else 2


if __name__ == "__main__":
    raise SystemExit(main())
