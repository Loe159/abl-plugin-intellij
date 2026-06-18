#!/usr/bin/env python3
"""Build a deterministic non-authorizing supervised implementation proposal."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

import apply_stage_output
import build_implementation_handoff
import build_stage_context
import diff_policy
import validate_disposable_worktree
import validate_artifacts


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_DIR = REPO_ROOT / ".agent" / "policies"
PROMPTS_DIR = REPO_ROOT / ".agent" / "prompts"
SHA256 = re.compile(r"[0-9a-f]{64}")
COMMIT = re.compile(r"[0-9a-f]{40}")
RISKS = {"low", "medium", "high"}
FALSE_AUTHORIZATION_FIELDS = (
    "authorized",
    "agent_invocation_authorized",
    "implementation_authorized",
    "repository_mutation_authorized",
    "network_authorized",
    "publication_authorized",
)


def matches_typed_mapping(actual: Any, expected: dict[str, Any]) -> bool:
    return (
        isinstance(actual, dict)
        and set(actual) == set(expected)
        and all(type(actual[key]) is type(value) and actual[key] == value for key, value in expected.items())
    )


def load_session_policy(path: Path, diff_config: dict[str, Any]) -> dict[str, Any]:
    policy = json.loads(path.read_text(encoding="utf-8"))
    required = {
        "version",
        "purpose",
        "mode",
        "max_handoff_bytes",
        "max_prompt_bytes",
        "max_proposal_bytes",
        "require_external_handoff",
        "require_external_output",
        "require_clean_worktree",
        "require_repo_head_match",
        "require_valid_disposable_worktree",
        "prompt",
        "prompt_required_sections",
        "prompt_required_literals",
        "policy_bindings",
        "workspace",
        "capabilities",
        "budgets",
        "required_external_controls",
    }
    if set(policy) != required:
        raise ValueError("Implementation-session policy fields do not match the contract")
    if (
        not isinstance(policy["version"], int)
        or isinstance(policy["version"], bool)
        or policy["version"] != 2
    ):
        raise ValueError(f"Unsupported implementation-session policy version: {policy['version']}")
    if (
        policy["purpose"] != "supervised_implementation_session_proposal"
        or policy["mode"] != "proposal-only"
    ):
        raise ValueError("purpose and mode must match the non-authorizing proposal contract")
    expected_sizes = {
        "max_handoff_bytes": 70000,
        "max_prompt_bytes": 12000,
        "max_proposal_bytes": 150000,
    }
    if any(
        not isinstance(policy[field], int)
        or isinstance(policy[field], bool)
        or policy[field] != value
        for field, value in expected_sizes.items()
    ):
        raise ValueError("size limits must match the bounded pilot contract")
    for field in (
        "require_external_handoff",
        "require_external_output",
        "require_clean_worktree",
        "require_repo_head_match",
        "require_valid_disposable_worktree",
    ):
        if policy[field] is not True:
            raise ValueError(f"{field} must explicitly be true during the pilot")
    if policy["prompt"] != "implementation/implement.md":
        raise ValueError("prompt must be implementation/implement.md")
    for field in (
        "prompt_required_sections",
        "prompt_required_literals",
        "policy_bindings",
        "required_external_controls",
    ):
        values = policy[field]
        if (
            not isinstance(values, list)
            or not values
            or not all(isinstance(value, str) and value for value in values)
            or len(values) != len(set(values))
        ):
            raise ValueError(f"{field} must be a non-empty unique list of strings")
    expected_sections = [
        "Objective",
        "Trusted Inputs",
        "Required Process",
        "Workspace Permissions",
        "Required Output",
        "Stop Conditions",
        "Prohibited Actions",
    ]
    if policy["prompt_required_sections"] != expected_sections:
        raise ValueError("prompt_required_sections must match the implementation prompt contract")
    expected_literals = [
        "AGENTS.md",
        ".agents/skills/proparse-research/",
        "disposable Git workspace",
        "Do not access the network",
        "Do not mutate the external run",
        "Do not claim completion",
        "diff-policy budget",
    ]
    if policy["prompt_required_literals"] != expected_literals:
        raise ValueError("prompt_required_literals must match the implementation prompt contract")
    expected_bindings = [
        "AGENTS.md",
        ".agent/policies/artifact-contract.json",
        ".agent/policies/diff-policy.json",
        ".agent/policies/implementation-session.json",
        ".agent/policies/risk-rules.json",
        ".agent/checks/validate_disposable_worktree.py",
        ".agent/policies/disposable-worktree-validation.json",
        ".agents/skills/proparse-research/SKILL.md",
    ]
    if policy["policy_bindings"] != expected_bindings:
        raise ValueError("policy_bindings must match the bounded implementation contract")
    expected_workspace = {
        "kind": "disposable-git-worktree",
        "require_clean_start": True,
        "require_exact_base_commit": True,
        "repository_file_writes": True,
        "git_index_writes": False,
        "git_commits": False,
        "branch_operations": False,
    }
    if not matches_typed_mapping(policy["workspace"], expected_workspace):
        raise ValueError("workspace must match the bounded supervised-write contract")
    expected_capabilities = {
        "repository_reads": True,
        "repository_file_writes": True,
        "local_commands": True,
        "network_access": False,
        "external_service_writes": False,
        "external_run_writes": False,
        "handoff_writes": False,
        "proposal_writes": False,
        "publication": False,
    }
    if not matches_typed_mapping(policy["capabilities"], expected_capabilities):
        raise ValueError("capabilities must match the bounded supervised-write contract")
    budgets = policy["budgets"]
    expected_budgets = {
        "max_turns": 12,
        "max_duration_minutes": 30,
        "max_changed_files": diff_config["max_files"],
        "max_changed_lines": diff_config["max_changed_lines"],
    }
    if not matches_typed_mapping(budgets, expected_budgets):
        raise ValueError("budgets must match the bounded session and diff-policy limits")
    if (
        budgets["max_changed_files"] != diff_config["max_files"]
        or budgets["max_changed_lines"] != diff_config["max_changed_lines"]
    ):
        raise ValueError("patch budgets must match diff-policy limits")
    required_controls = [
        "complete_patch_generation",
        "diff_policy_validation",
        "patch_risk_classification",
        "disposable_worktree_validation",
        "focused_tests",
        "human_implementation_review",
    ]
    if policy["required_external_controls"] != required_controls:
        raise ValueError("required_external_controls must match the pilot contract")
    return policy


def load_policies() -> dict[str, Any]:
    diff_config = diff_policy.load_policy(POLICY_DIR / "diff-policy.json")
    return {
        "diff": diff_config,
        "session": load_session_policy(POLICY_DIR / "implementation-session.json", diff_config),
    }


def failure(rule: str, message: str, **details: Any) -> dict[str, Any]:
    return {"rule": rule, "message": message, **details}


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def validate_prompt(path: Path, policy: dict[str, Any]) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ValueError("Implementation prompt must be an existing regular file")
    content = path.read_bytes()
    if len(content) > policy["max_prompt_bytes"]:
        raise ValueError("Implementation prompt exceeds max_prompt_bytes")
    text = content.decode("utf-8-sig")
    prompt = validate_artifacts.parse_artifact_text(path.name, text)
    if prompt.frontmatter != {
        "prompt_version": "1",
        "stage": "implement",
        "mode": "supervised-write",
        "input": "implementation-session-proposal.json",
    }:
        raise ValueError("Implementation prompt frontmatter does not match the contract")
    if list(prompt.sections) != policy["prompt_required_sections"]:
        raise ValueError("Implementation prompt sections do not match the contract")
    missing = [literal for literal in policy["prompt_required_literals"] if literal not in text]
    if missing:
        raise ValueError(f"Implementation prompt is missing required literals: {', '.join(missing)}")
    if validate_artifacts.PLACEHOLDER.search(text):
        raise ValueError("Implementation prompt contains unresolved placeholders")
    return {
        "name": path.name,
        "sha256": sha256_bytes(content),
        "size_bytes": len(content),
        "content": text,
    }


def manifest_snapshot_sha256(manifest: list[dict[str, Any]]) -> str:
    snapshot = b"".join(
        record["name"].encode("utf-8")
        + b"\0"
        + record["sha256"].encode("ascii")
        + b"\n"
        for record in sorted(manifest, key=lambda item: item["name"])
    )
    return sha256_bytes(snapshot)


def validate_handoff(path: Path, expected_sha256: str, max_bytes: int) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ValueError("Implementation handoff must be an existing regular file")
    if not SHA256.fullmatch(expected_sha256):
        raise ValueError("Expected handoff SHA-256 must be 64 lowercase hexadecimal characters")
    content = path.read_bytes()
    if len(content) > max_bytes:
        raise ValueError("Implementation handoff exceeds max_handoff_bytes")
    if sha256_bytes(content) != expected_sha256:
        raise ValueError("Implementation handoff SHA-256 does not match the expected digest")
    handoff = json.loads(content.decode("utf-8-sig"))
    expected_fields = {
        "handoff_version",
        "purpose",
        "mode",
        *FALSE_AUTHORIZATION_FIELDS,
        "issue",
        "risk",
        "base_commit",
        "repo_head",
        "run_snapshot_sha256",
        "plan_approval_receipt_sha256",
        "run_manifest",
        "artifacts",
    }
    if set(handoff) != expected_fields:
        raise ValueError("Implementation handoff fields do not match the contract")
    if (
        not isinstance(handoff["handoff_version"], int)
        or isinstance(handoff["handoff_version"], bool)
        or handoff["handoff_version"] != 2
        or handoff["purpose"] != "implementation_handoff"
        or handoff["mode"] != "handoff-only"
        or any(handoff[field] is not False for field in FALSE_AUTHORIZATION_FIELDS)
    ):
        raise ValueError("Implementation handoff metadata does not match the contract")
    if (
        not isinstance(handoff["issue"], int)
        or isinstance(handoff["issue"], bool)
        or handoff["issue"] < 1
        or handoff["risk"] not in RISKS
        or not COMMIT.fullmatch(handoff["base_commit"])
        or handoff["repo_head"] != handoff["base_commit"]
        or not SHA256.fullmatch(handoff["run_snapshot_sha256"])
        or not SHA256.fullmatch(handoff["plan_approval_receipt_sha256"])
    ):
        raise ValueError("Implementation handoff identity does not match the contract")

    artifact_contract = validate_artifacts.load_contract(POLICY_DIR / "artifact-contract.json")
    manifest = handoff["run_manifest"]
    artifact_names = list(artifact_contract["artifacts"])
    if (
        not isinstance(manifest, list)
        or not all(isinstance(record, dict) for record in manifest)
        or [record.get("name") for record in manifest] != artifact_names
    ):
        raise ValueError("Implementation handoff manifest does not match the artifact contract")
    manifest_by_name: dict[str, dict[str, Any]] = {}
    for record in manifest:
        if set(record) != {"name", "status", "sha256", "size_bytes"}:
            raise ValueError("Implementation handoff manifest record fields do not match")
        if (
            not isinstance(record["status"], str)
            or record["status"]
            not in artifact_contract["artifacts"][record["name"]]["allowed_statuses"]
            or not isinstance(record["sha256"], str)
            or not SHA256.fullmatch(record["sha256"])
            or not isinstance(record["size_bytes"], int)
            or isinstance(record["size_bytes"], bool)
            or record["size_bytes"] < 1
        ):
            raise ValueError("Implementation handoff manifest record is invalid")
        manifest_by_name[record["name"]] = record
    if manifest_snapshot_sha256(manifest) != handoff["run_snapshot_sha256"]:
        raise ValueError("Implementation handoff run snapshot does not match its manifest")

    artifacts = handoff["artifacts"]
    if (
        not isinstance(artifacts, list)
        or not all(isinstance(record, dict) for record in artifacts)
        or [record.get("name") for record in artifacts] != ["task.md", "research.md", "plan.md"]
    ):
        raise ValueError("Implementation handoff content artifacts do not match the contract")
    for record in artifacts:
        if set(record) != {"name", "status", "sha256", "size_bytes", "content"}:
            raise ValueError("Implementation handoff content record fields do not match")
        if (
            not isinstance(record["content"], str)
            or not isinstance(record["status"], str)
            or not isinstance(record["sha256"], str)
            or not isinstance(record["size_bytes"], int)
            or isinstance(record["size_bytes"], bool)
        ):
            raise ValueError("Implementation handoff content record types do not match")
        encoded = record["content"].encode("utf-8")
        if (
            sha256_bytes(encoded) != record["sha256"]
            or len(encoded) != record["size_bytes"]
            or {
                "status": record["status"],
                "sha256": record["sha256"],
                "size_bytes": record["size_bytes"],
            }
            != {
                "status": manifest_by_name[record["name"]]["status"],
                "sha256": manifest_by_name[record["name"]]["sha256"],
                "size_bytes": manifest_by_name[record["name"]]["size_bytes"],
            }
        ):
            raise ValueError("Implementation handoff content record does not match its manifest")
        artifact = validate_artifacts.parse_artifact_text(
            record["name"],
            record["content"].removeprefix("\ufeff"),
        )
        specification = artifact_contract["artifacts"][record["name"]]
        required_frontmatter = set(artifact_contract["common_frontmatter"]) | set(
            specification["required_frontmatter"]
        )
        if (
            artifact.frontmatter.get("artifact") != specification["artifact"]
            or artifact.frontmatter.get("artifact_version") != str(artifact_contract["version"])
            or artifact.frontmatter.get("status") not in specification["allowed_statuses"]
            or not required_frontmatter.issubset(artifact.frontmatter)
            or any(
                section not in artifact.sections or not artifact.sections[section]
                for section in specification["required_sections"]
            )
            or validate_artifacts.PLACEHOLDER.search(artifact.text)
        ):
            raise ValueError("Implementation handoff artifact does not satisfy its contract")
        if (
            artifact.frontmatter.get("issue") != str(handoff["issue"])
            or artifact.frontmatter.get("base_commit") != handoff["base_commit"]
            or artifact.frontmatter.get("status") != record["status"]
        ):
            raise ValueError("Implementation handoff artifact identity does not match")
        if record["name"] == "task.md" and artifact.frontmatter.get("risk") != handoff["risk"]:
            raise ValueError("Implementation handoff task risk does not match")
    if manifest_by_name["plan.md"]["status"] != "approved":
        raise ValueError("Implementation handoff plan must be approved")
    return handoff


def binding_record(repo_root: Path, name: str) -> dict[str, Any]:
    path = repo_root / name
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"Bound policy source must be an existing regular file: {name}")
    content = path.read_bytes()
    return {"name": name, "sha256": sha256_bytes(content), "size_bytes": len(content)}


def binding_records(repo_root: Path, names: list[str]) -> list[dict[str, Any]]:
    return [binding_record(repo_root, name) for name in names]


def validate_prepared_workspace(
    source_repo: Path,
    workspace: Path,
    receipt: Path,
    receipt_sha256: str,
    base_commit: str,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    validation = validate_disposable_worktree.validate(
        source_repo,
        workspace,
        receipt,
        receipt_sha256,
        validate_disposable_worktree.load_policy(),
    )
    if not validation["valid"]:
        return None, validation
    if validation["base_commit"] != base_commit:
        return None, {
            **validation,
            "valid": False,
            "failures": [
                *validation["failures"],
                failure(
                    "workspace_base_commit",
                    "Prepared workspace base differs from the handoff base commit.",
                ),
            ],
        }
    return {
        "kind": "validated-disposable-git-worktree",
        "path": str(workspace.resolve()),
        "receipt_sha256": receipt_sha256,
        "base_commit": validation["base_commit"],
        "validator_bindings": validation["validator_bindings"],
    }, validation


def base_result() -> dict[str, Any]:
    return {
        "produced": False,
        **{field: False for field in FALSE_AUTHORIZATION_FIELDS},
        "session_start_authorized": False,
        "issue": None,
        "risk": None,
        "base_commit": None,
        "handoff_sha256": None,
        "failures": [],
    }


def build_proposal(
    repo: Path,
    handoff_path: Path,
    handoff_sha256: str,
    workspace: Path,
    worktree_receipt: Path,
    worktree_receipt_sha256: str,
    output: Path,
    policies: dict[str, Any],
) -> dict[str, Any]:
    result = base_result()
    repo_root = Path(
        diff_policy.run_git(repo, "rev-parse", "--show-toplevel").decode("utf-8").strip()
    ).resolve()
    if handoff_path.is_symlink():
        raise ValueError("Implementation handoff symbolic links are not allowed")
    handoff_path = handoff_path.resolve()
    output = output.resolve()
    if policies["session"]["require_external_handoff"] and build_stage_context.is_within(
        handoff_path,
        repo_root,
    ):
        raise ValueError("Implementation handoff must be outside the Git checkout")
    if policies["session"]["require_external_output"] and build_stage_context.is_within(
        output,
        repo_root,
    ):
        raise ValueError("Implementation session proposal output must be outside the Git checkout")
    if output.exists():
        raise ValueError("Implementation session proposal output already exists")

    handoff = validate_handoff(
        handoff_path,
        handoff_sha256,
        policies["session"]["max_handoff_bytes"],
    )
    result.update(
        issue=handoff["issue"],
        risk=handoff["risk"],
        base_commit=handoff["base_commit"],
        handoff_sha256=handoff_sha256,
    )
    head = diff_policy.run_git(repo_root, "rev-parse", "HEAD").decode("ascii").strip()
    if policies["session"]["require_repo_head_match"] and head != handoff["base_commit"]:
        result["failures"].append(
            failure("repo_head_match", "Repository HEAD differs from the handoff base commit.")
        )
    status = build_implementation_handoff.repository_status(repo_root)
    if policies["session"]["require_clean_worktree"] and status:
        result["failures"].append(
            failure("clean_worktree", "Repository worktree must be clean.")
        )
    if result["failures"]:
        return result

    prepared_workspace: dict[str, Any] | None = None
    if policies["session"]["require_valid_disposable_worktree"]:
        prepared_workspace, workspace_validation = validate_prepared_workspace(
            repo_root,
            workspace,
            worktree_receipt,
            worktree_receipt_sha256,
            handoff["base_commit"],
        )
        if prepared_workspace is None:
            result["failures"].append(
                failure(
                    "disposable_worktree_validation",
                    "Prepared disposable worktree did not validate.",
                    validation=workspace_validation,
                )
            )
            return result

    prompt = validate_prompt(PROMPTS_DIR / policies["session"]["prompt"], policies["session"])
    bindings = binding_records(repo_root, policies["session"]["policy_bindings"])
    trusted_bindings = binding_records(REPO_ROOT, policies["session"]["policy_bindings"])
    if bindings != trusted_bindings:
        result["failures"].append(
            failure(
                "bound_policy_mismatch",
                "Workspace policy bindings differ from the trusted builder repository.",
            )
        )
        return result
    secret_records = [
        build_stage_context.content_record("implementation-handoff.json", json.dumps(handoff)),
        build_stage_context.content_record(prompt["name"], prompt["content"]),
    ]
    detections = build_stage_context.detect_secrets(secret_records, policies["diff"])
    if detections:
        result["failures"].append(
            failure(
                "high_confidence_secret",
                "Proposal source contains a high-confidence secret signature.",
                detections=detections,
            )
        )
        return result

    proposal = {
        "proposal_version": policies["session"]["version"],
        "purpose": policies["session"]["purpose"],
        "mode": policies["session"]["mode"],
        **{field: False for field in FALSE_AUTHORIZATION_FIELDS},
        "session_start_authorized": False,
        "issue": handoff["issue"],
        "risk": handoff["risk"],
        "base_commit": handoff["base_commit"],
        "repo_head": head,
        "handoff": {
            "sha256": handoff_sha256,
            "size_bytes": handoff_path.stat().st_size,
            "content": handoff,
        },
        "prompt": prompt,
        "policy_bindings": bindings,
        "workspace": policies["session"]["workspace"],
        "prepared_workspace": prepared_workspace,
        "capabilities": policies["session"]["capabilities"],
        "budgets": policies["session"]["budgets"],
        "required_external_controls": policies["session"]["required_external_controls"],
    }
    proposal_bytes = (json.dumps(proposal, indent=2, sort_keys=True) + "\n").encode("utf-8")
    if len(proposal_bytes) > policies["session"]["max_proposal_bytes"]:
        result["failures"].append(
            failure(
                "max_proposal_bytes",
                "Implementation session proposal exceeds the configured byte limit.",
                actual=len(proposal_bytes),
                limit=policies["session"]["max_proposal_bytes"],
            )
        )
        return result

    refreshed_handoff = sha256_bytes(handoff_path.read_bytes())
    refreshed_head = diff_policy.run_git(repo_root, "rev-parse", "HEAD").decode("ascii").strip()
    refreshed_status = build_implementation_handoff.repository_status(repo_root)
    refreshed_bindings = binding_records(repo_root, policies["session"]["policy_bindings"])
    refreshed_prepared_workspace = None
    if policies["session"]["require_valid_disposable_worktree"]:
        refreshed_prepared_workspace, refreshed_workspace_validation = validate_prepared_workspace(
            repo_root,
            workspace,
            worktree_receipt,
            worktree_receipt_sha256,
            handoff["base_commit"],
        )
    refreshed_prompt = validate_prompt(
        PROMPTS_DIR / policies["session"]["prompt"],
        policies["session"],
    )
    if (
        refreshed_handoff != handoff_sha256
        or refreshed_head != head
        or refreshed_status != status
        or refreshed_bindings != bindings
        or refreshed_prepared_workspace != prepared_workspace
        or refreshed_prompt != prompt
    ):
        result["failures"].append(
            failure(
                "state_changed",
                "Handoff, repository, prepared workspace, prompt, or bound policy changed.",
            )
        )
        return result

    build_stage_context.write_atomic(output, proposal_bytes)
    result.update(
        produced=True,
        output=str(output),
        sha256=sha256_bytes(proposal_bytes),
        size_bytes=len(proposal_bytes),
        bound_policies=[record["name"] for record in bindings],
    )
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--handoff", type=Path, required=True)
    parser.add_argument("--handoff-sha256", required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--worktree-receipt", type=Path, required=True)
    parser.add_argument("--worktree-receipt-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def format_text(result: dict[str, Any]) -> str:
    status = "PRODUCED" if result["produced"] else "NOT_PRODUCED"
    lines = [
        f"implementation-session: {status} issue={result['issue'] or 'unknown'}",
        "session_start_authorized=false",
        "implementation_authorized=false",
    ]
    for item in result["failures"]:
        lines.append(f"- {item['rule']}: {item['message']}")
    return "\n".join(lines)


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = build_proposal(
            args.repo,
            args.handoff,
            args.handoff_sha256,
            args.workspace,
            args.worktree_receipt,
            args.worktree_receipt_sha256,
            args.output,
            load_policies(),
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        print(f"implementation-session: ERROR\n- {error}", file=sys.stderr)
        return 1
    if args.format == "json":
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(format_text(result))
    return 0 if result["produced"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
