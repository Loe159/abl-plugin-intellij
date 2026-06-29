#!/usr/bin/env python3
"""Assess implementation-runner controls without selecting or authorizing a runner."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Callable

import audit_local_runner
import build_implementation_handoff
import diff_policy
import prove_disposable_worktree
import prove_parent_environment_isolation
import prove_bounded_output_capture
import prove_implementation_result_validation
import prove_implementation_patch_validation
import prove_implementation_patch_receipt_validation
import prove_implementation_quality_gate
import prove_implementation_quality_gate_validation
import prove_implementation_launch_transaction
import prove_wall_clock_timeout
import prove_runner_output_post_validation
import prove_windows_process_tree_timeout


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / ".agent" / "policies" / "runner-readiness.json"
FALSE_FIELDS = (
    "authorized",
    "agent_invocation_authorized",
    "implementation_authorized",
    "runner_selected",
    "session_start_authorized",
)
SOURCE_IDS = (
    "local_runner_audit",
    "disposable_worktree_proof",
    "direct_child_timeout_proof",
    "windows_process_tree_timeout_proof",
    "parent_environment_isolation_proof",
    "bounded_output_capture_proof",
    "implementation_launch_transaction_proof",
    "implementation_result_validation_proof",
    "runner_output_post_validation_proof",
    "implementation_patch_validation_proof",
    "implementation_patch_receipt_validation_proof",
    "implementation_quality_gate_proof",
    "implementation_quality_gate_validation_proof",
)
SOURCE_CONTRACTS = {
    "local_runner_audit": {
        "purpose": "local_runner_capability_audit",
        "mode": "metadata-only",
        "completion_field": "audit_complete",
        "assessment_fields": ("metadata_assessments", "enforcement_assessments"),
        "expected_ids": {
            *[
                rule["id"]
                for rule in audit_local_runner.EXPECTED_POLICY["metadata_assessments"]
            ],
            *audit_local_runner.EXPECTED_POLICY["unproven_enforcement_controls"],
        },
    },
    "disposable_worktree_proof": {
        "purpose": "disposable_git_worktree_lifecycle_proof",
        "mode": "fixture-only",
        "completion_field": "proof_complete",
        "assessment_fields": ("control_assessments",),
        "expected_ids": {
            prove_disposable_worktree.EXPECTED_POLICY["proven_control"],
            *prove_disposable_worktree.EXPECTED_POLICY["unproven_controls"],
        },
    },
    "direct_child_timeout_proof": {
        "purpose": "post_spawn_direct_child_timeout_proof",
        "mode": "fixture-only",
        "completion_field": "proof_complete",
        "assessment_fields": ("control_assessments",),
        "expected_ids": {
            prove_wall_clock_timeout.EXPECTED_POLICY["proven_control"],
            *prove_wall_clock_timeout.EXPECTED_POLICY["unproven_controls"],
        },
    },
    "windows_process_tree_timeout_proof": {
        "purpose": "windows_taskkill_process_tree_timeout_proof",
        "mode": "fixture-only",
        "completion_field": "proof_complete",
        "assessment_fields": ("control_assessments",),
        "expected_ids": {
            prove_windows_process_tree_timeout.EXPECTED_POLICY["proven_control"],
            *prove_windows_process_tree_timeout.EXPECTED_POLICY["unproven_controls"],
        },
    },
    "parent_environment_isolation_proof": {
        "purpose": "parent_environment_credential_isolation_proof",
        "mode": "enforcement-proof",
        "completion_field": "proof_complete",
        "assessment_fields": ("control_assessments",),
        "expected_ids": {
            prove_parent_environment_isolation.EXPECTED_POLICY["proven_control"],
            *prove_parent_environment_isolation.EXPECTED_POLICY["unproven_controls"],
        },
    },
    "bounded_output_capture_proof": {
        "purpose": "bounded_stream_output_capture_proof",
        "mode": "enforcement-proof",
        "completion_field": "proof_complete",
        "assessment_fields": ("control_assessments",),
        "expected_ids": {
            prove_bounded_output_capture.EXPECTED_POLICY["proven_control"],
            *prove_bounded_output_capture.EXPECTED_POLICY["unproven_controls"],
        },
    },
    "implementation_launch_transaction_proof": {
        "purpose": "implementation_launch_transaction_mechanism_proof",
        "mode": "fixture-only",
        "completion_field": "proof_complete",
        "assessment_fields": ("control_assessments",),
        "expected_ids": {
            prove_implementation_launch_transaction.EXPECTED_POLICY[
                "proven_control"
            ],
            *prove_implementation_launch_transaction.EXPECTED_POLICY[
                "unproven_controls"
            ],
        },
    },
    "implementation_result_validation_proof": {
        "purpose": "implementation_result_contract_validation_proof",
        "mode": "enforcement-proof",
        "completion_field": "proof_complete",
        "assessment_fields": ("control_assessments",),
        "expected_ids": {
            prove_implementation_result_validation.EXPECTED_POLICY["proven_control"],
            *prove_implementation_result_validation.EXPECTED_POLICY["unproven_controls"],
        },
    },
    "runner_output_post_validation_proof": {
        "purpose": "runner_output_post_validation_mechanism_proof",
        "mode": "fixture-only",
        "completion_field": "proof_complete",
        "assessment_fields": ("control_assessments",),
        "expected_ids": {
            prove_runner_output_post_validation.EXPECTED_POLICY["proven_control"],
            *prove_runner_output_post_validation.EXPECTED_POLICY["unproven_controls"],
        },
    },
    "implementation_patch_validation_proof": {
        "purpose": "implementation_patch_post_validation_proof",
        "mode": "enforcement-proof",
        "completion_field": "proof_complete",
        "assessment_fields": ("control_assessments",),
        "expected_ids": {
            prove_implementation_patch_validation.EXPECTED_POLICY["proven_control"],
            *prove_implementation_patch_validation.EXPECTED_POLICY["unproven_controls"],
        },
    },
    "implementation_patch_receipt_validation_proof": {
        "purpose": "implementation_patch_post_validation_receipt_validation_proof",
        "mode": "enforcement-proof",
        "completion_field": "proof_complete",
        "assessment_fields": ("control_assessments",),
        "expected_ids": {
            prove_implementation_patch_receipt_validation.EXPECTED_POLICY[
                "proven_control"
            ],
            *prove_implementation_patch_receipt_validation.EXPECTED_POLICY[
                "unproven_controls"
            ],
        },
    },
    "implementation_quality_gate_proof": {
        "purpose": "implementation_quality_gate_execution_mechanism_proof",
        "mode": "fixture-only",
        "completion_field": "proof_complete",
        "assessment_fields": ("control_assessments",),
        "expected_ids": {
            prove_implementation_quality_gate.EXPECTED_POLICY["proven_control"],
            *prove_implementation_quality_gate.EXPECTED_POLICY["unproven_controls"],
        },
    },
    "implementation_quality_gate_validation_proof": {
        "purpose": "implementation_quality_gate_receipt_validation_proof",
        "mode": "enforcement-proof",
        "completion_field": "proof_complete",
        "assessment_fields": ("control_assessments",),
        "expected_ids": {
            prove_implementation_quality_gate_validation.EXPECTED_POLICY[
                "proven_control"
            ],
            *prove_implementation_quality_gate_validation.EXPECTED_POLICY[
                "unproven_controls"
            ],
        },
    },
}

EXPECTED_POLICY: dict[str, Any] = {
    "version": 1,
    "purpose": "implementation_runner_control_readiness_assessment",
    "mode": "assessment-only",
    "required_runtime_controls": [
        "parent_environment_credential_isolation",
        "provider_credential_descendant_noninheritance",
        "disposable_worktree_lifecycle",
        "filesystem_write_scope",
        "implementation_session_wall_clock_timeout",
        "model_turn_budget",
        "network_isolation",
        "bounded_output_capture",
        "authorization_consumption_to_process_start",
        "implementation_result_contract_validation",
        "runner_enforced_output_post_validation",
        "implementation_patch_post_validation",
        "implementation_patch_receipt_validation",
        "implementation_quality_gate_execution",
        "quality_gate_receipt_validation",
        "tool_allowlist",
    ],
    "satisfaction_rules": {
        "parent_environment_credential_isolation": [
            {
                "source": "parent_environment_isolation_proof",
                "id": "parent_environment_credential_isolation",
                "assessment": "verified_enforcement",
            }
        ],
        "provider_credential_descendant_noninheritance": [
            {
                "source": "parent_environment_isolation_proof",
                "id": "provider_credential_descendant_noninheritance",
                "assessment": "verified_enforcement",
            }
        ],
        "disposable_worktree_lifecycle": [
            {
                "source": "local_runner_audit",
                "id": "disposable_worktree_lifecycle",
                "assessment": "verified_enforcement",
            }
        ],
        "filesystem_write_scope": [
            {
                "source": "local_runner_audit",
                "id": "filesystem_write_scope",
                "assessment": "verified_enforcement",
            }
        ],
        "implementation_session_wall_clock_timeout": [
            {
                "source": "windows_process_tree_timeout_proof",
                "id": "implementation_session_wall_clock_timeout",
                "assessment": "verified_enforcement",
            }
        ],
        "model_turn_budget": [
            {
                "source": "local_runner_audit",
                "id": "model_turn_budget",
                "assessment": "verified_enforcement",
            }
        ],
        "network_isolation": [
            {
                "source": "local_runner_audit",
                "id": "network_isolation",
                "assessment": "verified_enforcement",
            }
        ],
        "bounded_output_capture": [
            {
                "source": "bounded_output_capture_proof",
                "id": "bounded_output_capture",
                "assessment": "verified_enforcement",
            }
        ],
        "authorization_consumption_to_process_start": [
            {
                "source": "local_runner_audit",
                "id": "authorization_consumption_to_process_start",
                "assessment": "verified_enforcement",
            }
        ],
        "implementation_result_contract_validation": [
            {
                "source": "implementation_result_validation_proof",
                "id": "implementation_result_contract_validation",
                "assessment": "verified_enforcement",
            }
        ],
        "runner_enforced_output_post_validation": [
            {
                "source": "implementation_result_validation_proof",
                "id": "runner_enforced_output_post_validation",
                "assessment": "verified_enforcement",
            }
        ],
        "implementation_patch_post_validation": [
            {
                "source": "implementation_patch_validation_proof",
                "id": "implementation_patch_post_validation",
                "assessment": "verified_enforcement",
            }
        ],
        "implementation_patch_receipt_validation": [
            {
                "source": "implementation_patch_receipt_validation_proof",
                "id": "implementation_patch_receipt_validation",
                "assessment": "verified_enforcement",
            }
        ],
        "implementation_quality_gate_execution": [
            {
                "source": "implementation_quality_gate_proof",
                "id": "implementation_quality_gate_execution",
                "assessment": "verified_enforcement",
            }
        ],
        "quality_gate_receipt_validation": [
            {
                "source": "implementation_quality_gate_validation_proof",
                "id": "quality_gate_receipt_validation",
                "assessment": "verified_enforcement",
            }
        ],
        "tool_allowlist": [
            {
                "source": "local_runner_audit",
                "id": "tool_allowlist",
                "assessment": "verified_enforcement",
            }
        ],
    },
    "related_evidence_rules": {
        "parent_environment_credential_isolation": [],
        "provider_credential_descendant_noninheritance": [],
        "disposable_worktree_lifecycle": [
            {
                "source": "local_runner_audit",
                "id": "git_worktree_metadata",
                "assessment": "observed_metadata",
            },
            {
                "source": "disposable_worktree_proof",
                "id": "disposable_git_worktree_lifecycle_fixture",
                "assessment": "verified_fixture",
            },
        ],
        "filesystem_write_scope": [
            {
                "source": "local_runner_audit",
                "id": "codex_sandbox_metadata",
                "assessment": "observed_metadata",
            }
        ],
        "implementation_session_wall_clock_timeout": [
            {
                "source": "direct_child_timeout_proof",
                "id": "post_spawn_direct_child_timeout",
                "assessment": "verified_fixture",
            },
            {
                "source": "windows_process_tree_timeout_proof",
                "id": "windows_taskkill_two_level_process_tree_timeout_fixture",
                "assessment": "verified_fixture",
            },
        ],
        "model_turn_budget": [],
        "network_isolation": [],
        "bounded_output_capture": [
            {
                "source": "local_runner_audit",
                "id": "codex_noninteractive_exec_metadata",
                "assessment": "observed_metadata",
            }
        ],
        "authorization_consumption_to_process_start": [
            {
                "source": "implementation_launch_transaction_proof",
                "id": "local_exclusive_claim_before_direct_child_spawn_fixture",
                "assessment": "verified_fixture",
            }
        ],
        "implementation_result_contract_validation": [],
        "runner_enforced_output_post_validation": [
            {
                "source": "runner_output_post_validation_proof",
                "id": "runner_output_post_validation_fixture",
                "assessment": "verified_fixture",
            }
        ],
        "implementation_patch_post_validation": [],
        "implementation_patch_receipt_validation": [],
        "implementation_quality_gate_execution": [
            {
                "source": "implementation_quality_gate_proof",
                "id": "bounded_quality_gate_execution_fixture",
                "assessment": "verified_fixture",
            }
        ],
        "quality_gate_receipt_validation": [],
        "tool_allowlist": [
            {
                "source": "local_runner_audit",
                "id": "codex_sandbox_metadata",
                "assessment": "observed_metadata",
            }
        ],
    },
    "policy_bindings": [
        ".agent/checks/assess_runner_readiness.py",
        ".agent/checks/audit_local_runner.py",
        ".agent/checks/prove_disposable_worktree.py",
        ".agent/checks/prove_wall_clock_timeout.py",
        ".agent/checks/prove_windows_process_tree_timeout.py",
        ".agent/checks/isolated_process.py",
        ".agent/checks/prove_parent_environment_isolation.py",
        ".agent/checks/prove_bounded_output_capture.py",
        ".agent/checks/prove_implementation_launch_transaction.py",
        ".agent/checks/validate_implementation_result.py",
        ".agent/checks/prove_implementation_result_validation.py",
        ".agent/checks/prove_runner_output_post_validation.py",
        ".agent/checks/validate_implementation_patch.py",
        ".agent/checks/prove_implementation_patch_validation.py",
        ".agent/checks/validate_implementation_patch_receipt.py",
        ".agent/checks/prove_implementation_patch_receipt_validation.py",
        ".agent/checks/run_implementation_quality_gate.py",
        ".agent/checks/prove_implementation_quality_gate.py",
        ".agent/checks/validate_implementation_quality_gate.py",
        ".agent/checks/prove_implementation_quality_gate_validation.py",
        ".agent/policies/local-runner-audit.json",
        ".agent/policies/disposable-worktree-proof.json",
        ".agent/policies/runner-readiness.json",
        ".agent/policies/wall-clock-timeout-proof.json",
        ".agent/policies/windows-process-tree-timeout-proof.json",
        ".agent/policies/parent-environment-isolation.json",
        ".agent/policies/parent-environment-isolation-proof.json",
        ".agent/policies/bounded-output-capture-proof.json",
        ".agent/policies/implementation-launch-transaction-proof.json",
        ".agent/policies/implementation-result-validation.json",
        ".agent/policies/implementation-result-validation-proof.json",
        ".agent/policies/runner-output-post-validation-proof.json",
        ".agent/schemas/implementation-result.schema.json",
        ".agent/policies/implementation-patch-post-validation.json",
        ".agent/policies/implementation-patch-post-validation-proof.json",
        ".agent/policies/implementation-patch-post-validation-validation.json",
        ".agent/policies/implementation-patch-post-validation-validation-proof.json",
        ".agent/policies/implementation-quality-gate.json",
        ".agent/policies/implementation-quality-gate-proof.json",
        ".agent/policies/implementation-quality-gate-validation.json",
        ".agent/policies/implementation-quality-gate-validation-proof.json",
    ],
}


def load_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    policy = json.loads(path.read_text(encoding="utf-8"))
    if policy != EXPECTED_POLICY:
        raise ValueError("Runner-readiness policy does not match the assessment-only contract")
    return policy


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def binding_records(repo: Path, names: list[str]) -> list[dict[str, Any]]:
    records = []
    for name in names:
        path = repo / name
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"Bound readiness policy must be an existing regular file: {name}")
        content = path.read_bytes()
        records.append({"name": name, "sha256": sha256_bytes(content), "size_bytes": len(content)})
    return records


def source_assessments(source_id: str, source: dict[str, Any]) -> dict[str, str]:
    contract = SOURCE_CONTRACTS[source_id]
    if (
        source.get("purpose") != contract["purpose"]
        or source.get("mode") != contract["mode"]
        or source.get(contract["completion_field"]) is not True
    ):
        raise ValueError("Evidence source metadata does not match the contract")
    assessments: dict[str, str] = {}
    for field in contract["assessment_fields"]:
        for item in source.get(field, []):
            if (
                not isinstance(item, dict)
                or not isinstance(item.get("id"), str)
                or not isinstance(item.get("assessment"), str)
                or item["id"] in assessments
            ):
                raise ValueError("Evidence source assessments do not match the contract")
            assessments[item["id"]] = item["assessment"]
    if set(assessments) != contract["expected_ids"]:
        raise ValueError("Evidence source assessment IDs do not match the contract")
    if any(source.get(field) is not False for field in FALSE_FIELDS):
        raise ValueError("Evidence source attempted to authorize or select a runner")
    return assessments


def rule_matches(rule: dict[str, str], evidence: dict[str, dict[str, str]]) -> bool:
    return evidence.get(rule["source"], {}).get(rule["id"]) == rule["assessment"]


def assess_controls(
    policy: dict[str, Any],
    evidence: dict[str, dict[str, str]],
) -> list[dict[str, Any]]:
    controls = []
    for control in policy["required_runtime_controls"]:
        satisfaction_matches = [
            rule for rule in policy["satisfaction_rules"][control] if rule_matches(rule, evidence)
        ]
        related_matches = [
            rule
            for rule in policy["related_evidence_rules"][control]
            if rule_matches(rule, evidence)
        ]
        status = (
            "satisfied"
            if satisfaction_matches
            else "related_evidence_only"
            if related_matches
            else "missing_evidence"
        )
        controls.append(
            {
                "id": control,
                "status": status,
                "satisfaction_evidence": satisfaction_matches,
                "related_evidence": related_matches,
            }
        )
    return controls


def default_sources(repo: Path) -> dict[str, dict[str, Any]]:
    return {
        "local_runner_audit": audit_local_runner.audit(repo, audit_local_runner.load_policy()),
        "disposable_worktree_proof": prove_disposable_worktree.prove(
            repo,
            prove_disposable_worktree.load_policy(),
        ),
        "direct_child_timeout_proof": prove_wall_clock_timeout.prove(
            repo,
            prove_wall_clock_timeout.load_policy(),
        ),
        "windows_process_tree_timeout_proof": prove_windows_process_tree_timeout.prove(
            repo,
            prove_windows_process_tree_timeout.load_policy(),
        ),
        "parent_environment_isolation_proof": prove_parent_environment_isolation.prove(
            repo,
            prove_parent_environment_isolation.load_policy(),
        ),
        "bounded_output_capture_proof": prove_bounded_output_capture.prove(
            repo,
            prove_bounded_output_capture.load_policy(),
        ),
        "implementation_launch_transaction_proof": (
            prove_implementation_launch_transaction.prove(
                repo,
                prove_implementation_launch_transaction.load_policy(),
            )
        ),
        "implementation_result_validation_proof": (
            prove_implementation_result_validation.prove(
                repo,
                prove_implementation_result_validation.load_policy(),
            )
        ),
        "runner_output_post_validation_proof": (
            prove_runner_output_post_validation.prove(
                repo,
                prove_runner_output_post_validation.load_policy(),
            )
        ),
        "implementation_patch_validation_proof": (
            prove_implementation_patch_validation.prove(
                repo,
                prove_implementation_patch_validation.load_policy(),
            )
        ),
        "implementation_patch_receipt_validation_proof": (
            prove_implementation_patch_receipt_validation.prove(
                repo,
                prove_implementation_patch_receipt_validation.load_policy(),
            )
        ),
        "implementation_quality_gate_proof": (
            prove_implementation_quality_gate.prove(
                repo,
                prove_implementation_quality_gate.load_policy(),
            )
        ),
        "implementation_quality_gate_validation_proof": (
            prove_implementation_quality_gate_validation.prove(
                repo,
                prove_implementation_quality_gate_validation.load_policy(),
            )
        ),
    }


def assess(
    repo: Path,
    policy: dict[str, Any],
    source_runner: Callable[[Path], dict[str, dict[str, Any]]] = default_sources,
) -> dict[str, Any]:
    repo_root = Path(
        diff_policy.run_git(repo, "rev-parse", "--show-toplevel").decode("utf-8").strip()
    ).resolve()
    before_status = build_implementation_handoff.repository_status(repo_root)
    sources = source_runner(repo_root)
    if set(sources) != set(SOURCE_IDS):
        raise ValueError("Evidence sources do not match the readiness contract")
    evidence = {
        source_id: source_assessments(source_id, source) for source_id, source in sources.items()
    }
    controls = assess_controls(policy, evidence)
    bindings = binding_records(repo_root, policy["policy_bindings"])
    trusted_bindings = binding_records(REPO_ROOT, policy["policy_bindings"])
    if bindings != trusted_bindings:
        raise ValueError("Workspace readiness policies differ from trusted policies")
    after_status = build_implementation_handoff.repository_status(repo_root)
    repo_unchanged = before_status == after_status
    controls_ready = all(control["status"] == "satisfied" for control in controls)
    if not repo_unchanged:
        controls_ready = False
    return {
        "assessment_version": policy["version"],
        "purpose": policy["purpose"],
        "mode": policy["mode"],
        **{field: False for field in FALSE_FIELDS},
        "assessment_complete": True,
        "controls_ready": controls_ready,
        "repo_unchanged": repo_unchanged,
        "controls": controls,
        "evidence_sources": [
            {
                "id": source_id,
                "purpose": sources[source_id]["purpose"],
                "mode": sources[source_id]["mode"],
            }
            for source_id in SOURCE_IDS
        ],
        "policy_bindings": bindings,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def format_text(result: dict[str, Any]) -> str:
    status = "READY" if result["controls_ready"] else "NOT_READY"
    lines = [
        f"runner-readiness: {status}",
        "runner_selected=false",
        "agent_invocation_authorized=false",
    ]
    lines.extend(f"- {control['id']}: {control['status']}" for control in result["controls"])
    return "\n".join(lines)


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = assess(args.repo, load_policy())
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        print(f"runner-readiness: ERROR\n- {error}", file=sys.stderr)
        return 1
    if args.format == "json":
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(format_text(result))
    return 0 if result["assessment_complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
