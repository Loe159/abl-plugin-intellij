from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


CHECKS_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = CHECKS_DIR.parents[1]
MODULE_PATH = CHECKS_DIR / "record_run_metrics.py"
sys.path.insert(0, str(CHECKS_DIR))
SPEC = importlib.util.spec_from_file_location("record_run_metrics", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
metrics = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = metrics
SPEC.loader.exec_module(metrics)


def patch_text() -> str:
    return "\n".join(
        [
            "diff --git a/src/main/example.txt b/src/main/example.txt",
            "index 1111111..2222222 100644",
            "--- a/src/main/example.txt",
            "+++ b/src/main/example.txt",
            "@@ -1 +1,2 @@",
            "-old",
            "+new",
            "+second",
            "",
        ]
    )


def observation(patch_sha256: str | None, stage: str = "implement") -> dict[str, object]:
    return {
        "observation_version": 1,
        "purpose": "agentic_run_metrics_observation",
        "mode": "post-run-observation",
        "run_id": "issue-17-run-1",
        "issue": 17,
        "stage": stage,
        "base_commit": "a" * 40,
        "adapter": {"id": "codex", "version": "manual-pilot"},
        "model": {"provider": "openai", "id": "unknown"},
        "timing": {
            "started_at": "2026-06-17T10:00:00Z",
            "completed_at": "2026-06-17T10:02:03.456Z",
        },
        "tokens": {
            "status": "unavailable",
            "source": "unavailable",
            "input_tokens": None,
            "output_tokens": None,
        },
        "cost": {
            "status": "estimated",
            "source": "manual_estimate",
            "amount_microunits": 12500,
            "currency": "EUR",
        },
        "outcome": {"status": "succeeded"},
        "human_corrections": {"status": "measured", "count": 2},
        "final_disposition": "pending",
        "regression_status": "not_assessed",
        "diff_status": "measured" if patch_sha256 is not None else "not_applicable",
        "patch_sha256": patch_sha256,
    }


def prepare(temp: Path, stage: str = "implement") -> tuple[Path, Path, Path]:
    patch = temp / "candidate.patch"
    patch.write_text(patch_text(), encoding="utf-8")
    digest = hashlib.sha256(patch.read_bytes()).hexdigest()
    source = temp / "observation.json"
    source.write_text(json.dumps(observation(digest, stage)), encoding="utf-8")
    return source, patch, temp / "metrics.json"


class RecordRunMetricsTest(unittest.TestCase):
    def test_policy_is_exact_manual_evidence_only(self) -> None:
        policy = metrics.load_policy()

        self.assertEqual(metrics.EXPECTED_POLICY, policy)
        self.assertEqual("manual-evidence-recording-only", policy["mode"])
        self.assertTrue(policy["require_external_record"])

    def test_builds_duration_patch_and_provenance_without_authorizing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source, patch, output = prepare(Path(temp_dir))
            record, content = metrics.build_record(
                REPO_ROOT,
                source,
                output,
                patch,
                metrics.load_policy(),
            )

        self.assertEqual(123456, record["timing"]["duration_ms"])
        self.assertEqual(1, record["diff"]["file_count"])
        self.assertEqual(3, record["diff"]["changed_lines"])
        self.assertEqual(2, record["diff"]["additions"])
        self.assertEqual(1, record["diff"]["deletions"])
        self.assertEqual("unavailable", record["tokens"]["status"])
        self.assertEqual("estimated", record["cost"]["status"])
        self.assertLess(len(content), metrics.load_policy()["max_record_bytes"])
        for field in metrics.FALSE_FIELDS:
            self.assertFalse(record[field])

    def test_non_implementation_stage_can_record_no_diff_and_unknown_values(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            value = observation(None, "research")
            value["cost"] = {
                "status": "unavailable",
                "source": "unavailable",
                "amount_microunits": None,
                "currency": None,
            }
            value["human_corrections"] = {"status": "not_assessed", "count": None}
            source = temp / "observation.json"
            source.write_text(json.dumps(value), encoding="utf-8")
            record, _content = metrics.build_record(
                REPO_ROOT,
                source,
                temp / "metrics.json",
                None,
                metrics.load_policy(),
            )

        self.assertEqual("not_applicable", record["diff"]["status"])
        self.assertEqual("unavailable", record["cost"]["status"])
        self.assertEqual("not_assessed", record["human_corrections"]["status"])

    def test_blocked_implementation_can_record_no_diff(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            value = observation(None, "implement")
            value["outcome"] = {"status": "blocked"}
            value["cost"] = {
                "status": "unavailable",
                "source": "unavailable",
                "amount_microunits": None,
                "currency": None,
            }
            value["human_corrections"] = {"status": "not_assessed", "count": None}
            source = temp / "observation.json"
            source.write_text(json.dumps(value), encoding="utf-8")
            record, _content = metrics.build_record(
                REPO_ROOT,
                source,
                temp / "metrics.json",
                None,
                metrics.load_policy(),
            )

        self.assertEqual("implement", record["stage"])
        self.assertEqual("blocked", record["outcome"]["status"])
        self.assertEqual("not_applicable", record["diff"]["status"])

    def test_rejects_digest_mismatch_fake_zero_and_implementation_without_patch(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source, patch, output = prepare(Path(temp_dir))
            value = json.loads(source.read_text(encoding="utf-8"))
            value["patch_sha256"] = "b" * 64
            source.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                metrics.build_record(
                    REPO_ROOT,
                    source,
                    output,
                    patch,
                    metrics.load_policy(),
                )

            value = observation(None, "implement")
            source.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Successful implement observations"):
                metrics.build_record(
                    REPO_ROOT,
                    source,
                    output,
                    None,
                    metrics.load_policy(),
                )

            value = observation(hashlib.sha256(patch.read_bytes()).hexdigest())
            value["cost"] = {
                "status": "unavailable",
                "source": "unavailable",
                "amount_microunits": 0,
                "currency": None,
            }
            source.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "must be null"):
                metrics.build_record(
                    REPO_ROOT,
                    source,
                    output,
                    patch,
                    metrics.load_policy(),
                )

    def test_record_validates_exactly_writes_once_and_refuses_policy_override(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source, patch, output = prepare(Path(temp_dir))
            completed = subprocess.run(
                [
                    sys.executable,
                    str(MODULE_PATH),
                    "record",
                    "--repo",
                    str(REPO_ROOT),
                    "--observation",
                    str(source),
                    "--record",
                    str(output),
                    "--patch",
                    str(patch),
                    "--format",
                    "json",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            recorded = json.loads(completed.stdout)
            validated = subprocess.run(
                [
                    sys.executable,
                    str(MODULE_PATH),
                    "validate",
                    "--repo",
                    str(REPO_ROOT),
                    "--observation",
                    str(source),
                    "--record",
                    str(output),
                    "--record-sha256",
                    recorded["record_sha256"],
                    "--patch",
                    str(patch),
                    "--format",
                    "json",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            second = subprocess.run(
                [
                    sys.executable,
                    str(MODULE_PATH),
                    "record",
                    "--repo",
                    str(REPO_ROOT),
                    "--observation",
                    str(source),
                    "--record",
                    str(output),
                    "--patch",
                    str(patch),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            override = subprocess.run(
                [
                    sys.executable,
                    str(MODULE_PATH),
                    "check",
                    "--repo",
                    str(REPO_ROOT),
                    "--observation",
                    str(source),
                    "--record",
                    str(Path(temp_dir) / "other.json"),
                    "--patch",
                    str(patch),
                    "--policy",
                    "untrusted",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertTrue(recorded["recorded"])
        self.assertEqual(0, validated.returncode, validated.stderr)
        self.assertTrue(json.loads(validated.stdout)["valid"])
        self.assertEqual(1, second.returncode)
        self.assertIn("already exists", second.stderr)
        self.assertEqual(2, override.returncode)
        self.assertIn("unrecognized arguments", override.stderr)

    def test_validation_rejects_record_or_source_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            source, patch, output = prepare(temp)
            record, content = metrics.build_record(
                REPO_ROOT,
                source,
                output,
                patch,
                metrics.load_policy(),
            )
            output.write_bytes(content)
            digest = hashlib.sha256(content).hexdigest()
            valid_record, expected = metrics.build_record(
                REPO_ROOT,
                source,
                output,
                patch,
                metrics.load_policy(),
                require_existing_record=True,
            )
            self.assertEqual(record, valid_record)
            self.assertEqual(content, expected)

            output.write_bytes(content + b" ")
            completed = subprocess.run(
                [
                    sys.executable,
                    str(MODULE_PATH),
                    "validate",
                    "--repo",
                    str(REPO_ROOT),
                    "--observation",
                    str(source),
                    "--record",
                    str(output),
                    "--record-sha256",
                    digest,
                    "--patch",
                    str(patch),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(1, completed.returncode)
        self.assertIn("SHA-256 does not match", completed.stderr)


if __name__ == "__main__":
    unittest.main()
