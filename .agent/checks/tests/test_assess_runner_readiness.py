from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


CHECKS_DIR = Path(__file__).resolve().parents[1]
MODULE_PATH = CHECKS_DIR / "assess_runner_readiness.py"
REPO_ROOT = CHECKS_DIR.parents[1]
sys.path.insert(0, str(CHECKS_DIR))
SPEC = importlib.util.spec_from_file_location("assess_runner_readiness", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
readiness = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = readiness
SPEC.loader.exec_module(readiness)


def synthetic_sources(satisfied: bool = False) -> dict[str, dict[str, object]]:
    sources: dict[str, dict[str, object]] = {}
    for source_id, contract in readiness.SOURCE_CONTRACTS.items():
        assessments = {item: "not_proven" for item in contract["expected_ids"]}
        sources[source_id] = {
            "purpose": contract["purpose"],
            "mode": contract["mode"],
            contract["completion_field"]: True,
            contract["assessment_fields"][0]: [
                {"id": item, "assessment": assessment}
                for item, assessment in sorted(assessments.items())
            ],
        }
    if satisfied:
        for rules in readiness.EXPECTED_POLICY["satisfaction_rules"].values():
            for rule in rules:
                source = sources[rule["source"]]
                field = readiness.SOURCE_CONTRACTS[rule["source"]]["assessment_fields"][0]
                record = next(item for item in source[field] if item["id"] == rule["id"])
                record["assessment"] = rule["assessment"]
    for source in sources.values():
        source.update({field: False for field in readiness.FALSE_FIELDS})
    return sources


class AssessRunnerReadinessTest(unittest.TestCase):
    def test_repository_policy_is_exact_assessment_only_and_non_authorizing(self) -> None:
        policy = readiness.load_policy()

        self.assertEqual(readiness.EXPECTED_POLICY, policy)
        self.assertEqual("assessment-only", policy["mode"])
        self.assertEqual(set(policy["required_runtime_controls"]), set(policy["satisfaction_rules"]))
        self.assertEqual(set(policy["required_runtime_controls"]), set(policy["related_evidence_rules"]))

    def test_current_environment_is_not_ready_and_preserves_distinctions(self) -> None:
        before = readiness.build_implementation_handoff.repository_status(REPO_ROOT)
        result = readiness.assess(REPO_ROOT, readiness.load_policy())
        after = readiness.build_implementation_handoff.repository_status(REPO_ROOT)
        statuses = {control["id"]: control["status"] for control in result["controls"]}

        self.assertFalse(result["controls_ready"])
        self.assertTrue(result["repo_unchanged"])
        self.assertEqual(before, after)
        self.assertEqual(
            "satisfied",
            statuses["parent_environment_credential_isolation"],
        )
        self.assertEqual(
            "related_evidence_only",
            statuses["provider_credential_descendant_noninheritance"],
        )
        self.assertEqual("related_evidence_only", statuses["filesystem_write_scope"])
        filesystem_scope = next(
            control for control in result["controls"] if control["id"] == "filesystem_write_scope"
        )
        self.assertIn(
            {
                "source": "supervised_implementation_runner_contract",
                "id": "workspace_cwd_and_external_outputs_contract",
                "assessment": "verified_contract",
            },
            filesystem_scope["related_evidence"],
        )
        provider_noninheritance = next(
            control
            for control in result["controls"]
            if control["id"] == "provider_credential_descendant_noninheritance"
        )
        self.assertIn(
            {
                "source": "local_adapter_environment_filter_proof",
                "id": "local_adapter_child_environment_filter",
                "assessment": "verified_enforcement",
            },
            provider_noninheritance["related_evidence"],
        )
        self.assertEqual("satisfied", statuses["bounded_output_capture"])
        self.assertEqual(
            "related_evidence_only",
            statuses["authorization_consumption_to_process_start"],
        )
        lifecycle = next(
            control for control in result["controls"] if control["id"] == "disposable_worktree_lifecycle"
        )
        self.assertIn(
            {
                "source": "supervised_runner_execution_proof",
                "id": "cleanup_after_successful_runner_completion",
                "assessment": "verified_fixture",
            },
            lifecycle["related_evidence"],
        )
        self.assertIn(
            {
                "source": "supervised_implementation_runner_contract",
                "id": "optional_cleanup_after_controlled_blocked_stage",
                "assessment": "verified_contract",
            },
            lifecycle["related_evidence"],
        )
        self.assertIn(
            {
                "source": "supervised_runner_execution_proof",
                "id": "cleanup_after_controlled_blocked_completion",
                "assessment": "verified_fixture",
            },
            lifecycle["related_evidence"],
        )
        self.assertIn(
            {
                "source": "supervised_implementation_runner_contract",
                "id": "cleanup_receipt_validation_after_cleanup",
                "assessment": "verified_contract",
            },
            lifecycle["related_evidence"],
        )
        self.assertIn(
            {
                "source": "supervised_runner_execution_proof",
                "id": "cleanup_receipt_validation_after_runner_cleanup",
                "assessment": "verified_fixture",
            },
            lifecycle["related_evidence"],
        )
        self.assertIn(
            {
                "source": "supervised_runner_execution_proof",
                "id": "cleanup_after_controlled_adapter_timeout",
                "assessment": "verified_fixture",
            },
            lifecycle["related_evidence"],
        )
        authorization_coupling = next(
            control
            for control in result["controls"]
            if control["id"] == "authorization_consumption_to_process_start"
        )
        self.assertIn(
            {
                "source": "supervised_implementation_runner_contract",
                "id": "authorization_consumption_before_adapter_execution",
                "assessment": "verified_contract",
            },
            authorization_coupling["related_evidence"],
        )
        self.assertIn(
            {
                "source": "supervised_runner_execution_proof",
                "id": "supervised_runner_consumption_launch_before_adapter_sequence",
                "assessment": "verified_fixture",
            },
            authorization_coupling["related_evidence"],
        )
        self.assertEqual(
            "satisfied",
            statuses["implementation_result_contract_validation"],
        )
        self.assertEqual(
            "satisfied",
            statuses["runner_enforced_output_post_validation"],
        )
        runner_post_validation = next(
            control
            for control in result["controls"]
            if control["id"] == "runner_enforced_output_post_validation"
        )
        self.assertIn(
            {
                "source": "supervised_runner_execution_proof",
                "id": "runner_enforced_output_post_validation",
                "assessment": "verified_enforcement",
            },
            runner_post_validation["satisfaction_evidence"],
        )
        self.assertIn(
            {
                "source": "runner_output_post_validation_proof",
                "id": "runner_output_post_validation_fixture",
                "assessment": "verified_fixture",
            },
            runner_post_validation["related_evidence"],
        )
        self.assertIn(
            {
                "source": "supervised_implementation_runner_contract",
                "id": "implementation_result_post_validation_before_retention",
                "assessment": "verified_contract",
            },
            runner_post_validation["related_evidence"],
        )
        self.assertIn(
            {
                "source": "supervised_implementation_runner_contract",
                "id": "final_receipt_validation_after_write",
                "assessment": "verified_contract",
            },
            runner_post_validation["related_evidence"],
        )
        self.assertIn(
            {
                "source": "supervised_runner_execution_proof",
                "id": "final_receipt_validation_after_runner_write",
                "assessment": "verified_fixture",
            },
            runner_post_validation["related_evidence"],
        )
        self.assertEqual(
            "satisfied",
            statuses["implementation_patch_post_validation"],
        )
        self.assertEqual(
            "satisfied",
            statuses["implementation_patch_receipt_validation"],
        )
        self.assertEqual(
            "related_evidence_only",
            statuses["implementation_quality_gate_execution"],
        )
        self.assertEqual(
            "satisfied",
            statuses["quality_gate_receipt_validation"],
        )
        self.assertEqual("satisfied", statuses["tool_allowlist"])
        tool_allowlist = next(
            control for control in result["controls"] if control["id"] == "tool_allowlist"
        )
        self.assertIn(
            {
                "source": "runner_tool_allowlist_proof",
                "id": "tool_allowlist",
                "assessment": "verified_enforcement",
            },
            tool_allowlist["satisfaction_evidence"],
        )
        self.assertEqual("related_evidence_only", statuses["model_turn_budget"])
        model_budget = next(
            control for control in result["controls"] if control["id"] == "model_turn_budget"
        )
        self.assertIn(
            {
                "source": "supervised_implementation_runner_contract",
                "id": "model_turn_budget_declared_in_session_contract",
                "assessment": "verified_contract",
            },
            model_budget["related_evidence"],
        )
        self.assertEqual("related_evidence_only", statuses["network_isolation"])
        network_isolation = next(
            control for control in result["controls"] if control["id"] == "network_isolation"
        )
        self.assertIn(
            {
                "source": "supervised_implementation_runner_contract",
                "id": "network_and_publication_requests_disabled",
                "assessment": "verified_contract",
            },
            network_isolation["related_evidence"],
        )
        self.assertEqual(
            "related_evidence_only",
            statuses["implementation_session_wall_clock_timeout"],
        )
        session_timeout = next(
            control
            for control in result["controls"]
            if control["id"] == "implementation_session_wall_clock_timeout"
        )
        self.assertIn(
            {
                "source": "supervised_implementation_runner_contract",
                "id": "adapter_timeout_within_isolated_process_bound",
                "assessment": "verified_contract",
            },
            session_timeout["related_evidence"],
        )
        self.assertIn(
            {
                "source": "supervised_runner_execution_proof",
                "id": "controlled_adapter_timeout_blocks_before_patch",
                "assessment": "verified_fixture",
            },
            session_timeout["related_evidence"],
        )
        self.assertIn(
            "supervised_implementation_runner_contract",
            [source["id"] for source in result["evidence_sources"]],
        )
        self.assertIn(
            "supervised_runner_execution_proof",
            [source["id"] for source in result["evidence_sources"]],
        )
        self.assertIn(
            "runner_tool_allowlist_proof",
            [source["id"] for source in result["evidence_sources"]],
        )
        self.assertIn(
            "local_adapter_environment_filter_proof",
            [source["id"] for source in result["evidence_sources"]],
        )
        for field in readiness.FALSE_FIELDS:
            self.assertFalse(result[field])

    def test_supervised_runner_contract_is_related_evidence_not_readiness(self) -> None:
        sources = synthetic_sources()
        source = sources["supervised_implementation_runner_contract"]
        field = readiness.SOURCE_CONTRACTS["supervised_implementation_runner_contract"][
            "assessment_fields"
        ][0]
        for item in source[field]:
            if item["id"] in {
                "supervised_local_runner_contract",
                "authorization_consumption_before_adapter_execution",
                "bounded_adapter_execution_via_isolated_process",
                "implementation_result_post_validation_before_retention",
                "candidate_patch_validation_before_quality_gate",
                "quality_gate_execution_and_receipt_validation",
                "network_and_publication_requests_disabled",
                "model_turn_budget_declared_in_session_contract",
            }:
                item["assessment"] = "verified_contract"
        result = readiness.assess(REPO_ROOT, readiness.load_policy(), lambda _repo: sources)
        statuses = {control["id"]: control["status"] for control in result["controls"]}

        self.assertFalse(result["controls_ready"])
        self.assertEqual(
            "related_evidence_only",
            statuses["authorization_consumption_to_process_start"],
        )
        self.assertEqual(
            "related_evidence_only",
            statuses["runner_enforced_output_post_validation"],
        )
        self.assertEqual(
            "related_evidence_only",
            statuses["implementation_patch_post_validation"],
        )
        self.assertEqual(
            "related_evidence_only",
            statuses["implementation_quality_gate_execution"],
        )
        self.assertEqual(
            "related_evidence_only",
            statuses["model_turn_budget"],
        )
        self.assertEqual("related_evidence_only", statuses["network_isolation"])
        self.assertEqual(
            "missing_evidence",
            statuses["provider_credential_descendant_noninheritance"],
        )
        for field_name in readiness.FALSE_FIELDS:
            self.assertFalse(result[field_name])

    def test_exact_verified_enforcement_can_satisfy_controls_but_never_authorizes(self) -> None:
        result = readiness.assess(
            REPO_ROOT,
            readiness.load_policy(),
            lambda _repo: synthetic_sources(satisfied=True),
        )

        self.assertTrue(result["controls_ready"])
        self.assertTrue(all(control["status"] == "satisfied" for control in result["controls"]))
        for field in readiness.FALSE_FIELDS:
            self.assertFalse(result[field])

    def test_related_or_wrong_assessment_never_satisfies_control(self) -> None:
        sources = synthetic_sources()
        local = sources["local_runner_audit"]
        field = readiness.SOURCE_CONTRACTS["local_runner_audit"]["assessment_fields"][0]
        record = next(item for item in local[field] if item["id"] == "git_worktree_metadata")
        record["assessment"] = "observed_metadata"
        result = readiness.assess(REPO_ROOT, readiness.load_policy(), lambda _repo: sources)
        control = next(item for item in result["controls"] if item["id"] == "disposable_worktree_lifecycle")

        self.assertEqual("related_evidence_only", control["status"])
        self.assertFalse(result["controls_ready"])

    def test_source_metadata_ids_and_authorization_injection_are_rejected(self) -> None:
        mutations = [
            lambda sources: sources["local_runner_audit"].update(mode="execute"),
            lambda sources: sources["direct_child_timeout_proof"].update(proof_complete=False),
            lambda sources: sources["windows_process_tree_timeout_proof"].update(authorized=True),
            lambda sources: sources["local_runner_audit"]["metadata_assessments"].append(
                {"id": "unexpected", "assessment": "verified_enforcement"}
            ),
        ]
        for mutate in mutations:
            with self.subTest():
                sources = synthetic_sources()
                mutate(sources)
                with self.assertRaisesRegex(ValueError, "Evidence source"):
                    readiness.assess(REPO_ROOT, readiness.load_policy(), lambda _repo: sources)

    def test_repo_drift_forces_not_ready(self) -> None:
        sources = synthetic_sources(satisfied=True)
        with mock.patch.object(
            readiness.build_implementation_handoff,
            "repository_status",
            side_effect=[["before"], ["after"]],
        ):
            result = readiness.assess(REPO_ROOT, readiness.load_policy(), lambda _repo: sources)

        self.assertFalse(result["repo_unchanged"])
        self.assertFalse(result["controls_ready"])
        self.assertFalse(result["session_start_authorized"])

    def test_policy_drift_and_cli_override_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "policy.json"
            policy = json.loads(json.dumps(readiness.EXPECTED_POLICY))
            policy["required_runtime_controls"].remove("network_isolation")
            path.write_text(json.dumps(policy), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "assessment-only contract"):
                readiness.load_policy(path)

        completed = subprocess.run(
            [
                sys.executable,
                str(MODULE_PATH),
                "--repo",
                str(REPO_ROOT),
                "--policy",
                "untrusted.json",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(2, completed.returncode)
        self.assertIn("unrecognized arguments", completed.stderr)


if __name__ == "__main__":
    unittest.main()
