from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any


CHECKS_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = CHECKS_DIR.parents[1]
MODULE_PATH = CHECKS_DIR / "validate_multi_adapter_comparison.py"
sys.path.insert(0, str(CHECKS_DIR))
SPEC = importlib.util.spec_from_file_location("validate_multi_adapter_comparison", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
comparison = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = comparison
SPEC.loader.exec_module(comparison)


BASE_COMMIT = "a" * 40
CONTEXT_SHA = "b" * 64


def sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def write_json(path: Path, value: dict[str, Any]) -> str:
    content = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
    path.write_bytes(content)
    return sha256(content)


def metrics_record(
    *,
    adapter_id: str,
    run_id: str,
    patch_sha: str,
    duration_ms: int,
    changed_lines: int,
) -> dict[str, Any]:
    return {
        "metrics_version": 1,
        "purpose": "agentic_run_metrics_record",
        "mode": "manual-evidence-recording-only",
        "authorized": False,
        "agent_invocation_authorized": False,
        "implementation_authorized": False,
        "repository_mutation_authorized": False,
        "network_authorized": False,
        "publication_authorized": False,
        "runner_selected": False,
        "session_start_authorized": False,
        "run_id": run_id,
        "issue": 17,
        "stage": "implement",
        "base_commit": BASE_COMMIT,
        "adapter": {"id": adapter_id, "version": "manual-pilot"},
        "model": {"provider": "local", "id": "unknown"},
        "timing": {
            "started_at": "2026-06-17T10:00:00Z",
            "completed_at": "2026-06-17T10:01:00Z",
            "duration_ms": duration_ms,
        },
        "tokens": {
            "status": "unavailable",
            "source": "unavailable",
            "input_tokens": None,
            "output_tokens": None,
        },
        "cost": {
            "status": "unavailable",
            "source": "unavailable",
            "amount_microunits": None,
            "currency": None,
        },
        "outcome": {"status": "succeeded"},
        "human_corrections": {"status": "not_assessed", "count": None},
        "final_disposition": "pending",
        "regression_status": "not_assessed",
        "diff": {
            "status": "measured",
            "sha256": patch_sha,
            "size_bytes": 12,
            "file_count": 1,
            "changed_lines": changed_lines,
            "additions": changed_lines,
            "deletions": 0,
            "paths": ["src/example.txt"],
            "binary_paths": [],
            "symlink_paths": [],
        },
        "source_evidence": {
            "observation_sha256": "c" * 64,
            "observation_size_bytes": 200,
            "patch_sha256": patch_sha,
            "patch_size_bytes": 12,
        },
        "policy_bindings": [],
    }


def build_manifest(temp: Path, same_adapter: bool = False) -> Path:
    codex_patch = temp / "codex.patch"
    aider_patch = temp / "aider.patch"
    codex_patch.write_bytes(b"codex patch\n")
    aider_patch.write_bytes(b"aider patch\n")
    codex_patch_sha = sha256(codex_patch.read_bytes())
    aider_patch_sha = sha256(aider_patch.read_bytes())
    codex_metrics_sha = write_json(
        temp / "codex-metrics.json",
        metrics_record(
            adapter_id="codex",
            run_id="issue-17-codex",
            patch_sha=codex_patch_sha,
            duration_ms=60000,
            changed_lines=3,
        ),
    )
    second_adapter = "codex" if same_adapter else "aider"
    aider_metrics_sha = write_json(
        temp / "aider-metrics.json",
        metrics_record(
            adapter_id=second_adapter,
            run_id="issue-17-aider",
            patch_sha=aider_patch_sha,
            duration_ms=45000,
            changed_lines=5,
        ),
    )
    manifest = {
        "manifest_version": 1,
        "purpose": "multi_adapter_comparison_manifest",
        "mode": "local-artifact-and-metrics-comparison-only",
        "comparison_id": "issue-17-implement",
        "task": {
            "id": "issue-17",
            "issue": 17,
            "stage": "implement",
            "base_commit": BASE_COMMIT,
            "context_sha256": CONTEXT_SHA,
        },
        "candidates": [
            {
                "candidate_id": "codex",
                "adapter": {"id": "codex", "version": "manual-pilot"},
                "model": {"provider": "local", "id": "unknown"},
                "artifact": {
                    "role": "complete_patch",
                    "path": "codex.patch",
                    "sha256": codex_patch_sha,
                },
                "metrics_record": {"path": "codex-metrics.json", "sha256": codex_metrics_sha},
            },
            {
                "candidate_id": "aider",
                "adapter": {"id": second_adapter, "version": "manual-pilot"},
                "model": {"provider": "local", "id": "unknown"},
                "artifact": {
                    "role": "complete_patch",
                    "path": "aider.patch",
                    "sha256": aider_patch_sha,
                },
                "metrics_record": {"path": "aider-metrics.json", "sha256": aider_metrics_sha},
            },
        ],
        "manual_interpretation": {"required": True, "winner_selected": False},
    }
    write_json(temp / "manifest.json", manifest)
    return temp / "manifest.json"


class ValidateMultiAdapterComparisonTest(unittest.TestCase):
    def test_policy_is_exact_local_artifact_contract(self) -> None:
        policy = comparison.load_policy()

        self.assertEqual(comparison.EXPECTED_POLICY, policy)
        self.assertEqual("local-artifact-and-metrics-comparison-only", policy["mode"])
        self.assertTrue(policy["no_winner_selection"])
        self.assertIn("timing.duration_ms", policy["metric_table"])

    def test_valid_manifest_produces_deterministic_non_authorizing_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manifest = build_manifest(Path(temp_dir))

            result = comparison.build_comparison(REPO_ROOT, manifest, comparison.load_policy())

        self.assertTrue(result["valid"])
        self.assertTrue(result["local_comparison_calculated"])
        self.assertTrue(result["local_artifacts_compared"])
        self.assertTrue(result["manual_interpretation_required"])
        self.assertFalse(result["shared_context_provenance_validated"])
        self.assertEqual(2, result["candidate_count"])
        self.assertEqual(["aider", "codex"], [row["candidate_id"] for row in result["candidates"]])
        for field in comparison.FALSE_FIELDS:
            self.assertFalse(result[field])
        duration = next(row for row in result["metric_table"] if row["metric"] == "timing.duration_ms")
        self.assertEqual(
            [
                {"candidate_id": "aider", "value": 45000},
                {"candidate_id": "codex", "value": 60000},
            ],
            duration["values"],
        )

    def test_rejects_non_distinct_adapters_and_metric_digest_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manifest = build_manifest(Path(temp_dir), same_adapter=True)

            with self.assertRaisesRegex(ValueError, "distinct adapters"):
                comparison.build_comparison(REPO_ROOT, manifest, comparison.load_policy())

        with tempfile.TemporaryDirectory() as temp_dir:
            manifest = build_manifest(Path(temp_dir))
            value = json.loads(manifest.read_text(encoding="utf-8"))
            value["candidates"][0]["metrics_record"]["sha256"] = "d" * 64
            manifest.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "Metrics record SHA-256 does not match"):
                comparison.build_comparison(REPO_ROOT, manifest, comparison.load_policy())

    def test_complete_patch_artifact_must_match_metrics_diff_sha(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            manifest = build_manifest(temp)
            value = json.loads(manifest.read_text(encoding="utf-8"))
            metrics_path = temp / value["candidates"][0]["metrics_record"]["path"]
            metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
            metrics["diff"]["sha256"] = "e" * 64
            metrics["source_evidence"]["patch_sha256"] = "e" * 64
            value["candidates"][0]["metrics_record"]["sha256"] = write_json(
                metrics_path,
                metrics,
            )
            manifest.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "metrics diff.sha256"):
                comparison.build_comparison(REPO_ROOT, manifest, comparison.load_policy())

    def test_cli_rejects_adapter_override(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(MODULE_PATH),
                "--repo",
                str(REPO_ROOT),
                "--manifest",
                "manifest.json",
                "--adapter",
                "codex",
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(2, completed.returncode)
        self.assertIn("unrecognized arguments", completed.stderr)


if __name__ == "__main__":
    unittest.main()
