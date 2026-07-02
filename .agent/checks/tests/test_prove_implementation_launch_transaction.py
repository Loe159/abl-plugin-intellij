from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


CHECKS_DIR = Path(__file__).resolve().parents[1]
MODULE_PATH = CHECKS_DIR / "prove_implementation_launch_transaction.py"
REPO_ROOT = CHECKS_DIR.parents[1]
sys.path.insert(0, str(CHECKS_DIR))
SPEC = importlib.util.spec_from_file_location(
    "prove_implementation_launch_transaction",
    MODULE_PATH,
)
assert SPEC is not None
assert SPEC.loader is not None
proof = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = proof
SPEC.loader.exec_module(proof)


class ProveImplementationLaunchTransactionTest(unittest.TestCase):
    def test_policy_is_exact_fixture_only_and_non_invoking(self) -> None:
        policy = proof.load_policy()

        self.assertEqual(proof.EXPECTED_POLICY, policy)
        self.assertEqual("fixture-only", policy["mode"])
        self.assertIn(
            "authorization_consumption_to_process_start",
            policy["unproven_controls"],
        )

    def test_fixture_claims_then_spawns_and_blocks_replay(self) -> None:
        result = proof.prove(REPO_ROOT, proof.load_policy())
        assessments = {
            item["id"]: item["assessment"]
            for item in result["control_assessments"]
        }

        self.assertEqual(
            "verified_fixture",
            assessments["local_exclusive_claim_before_direct_child_spawn_fixture"],
        )
        self.assertEqual(
            "not_proven",
            assessments["authorization_consumption_to_process_start"],
        )
        self.assertTrue(result["observations"]["first_claim_and_spawn_matched"])
        self.assertTrue(result["observations"]["ordinary_replay_blocked_before_spawn"])
        for field in proof.FALSE_FIELDS:
            self.assertFalse(result[field])

    def test_wrong_marker_digest_and_existing_claim_do_not_spawn(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            marker = temp / "marker"
            marker.write_text("marker\n", encoding="utf-8")
            calls = 0

            def runner(*_args: object, **_kwargs: object) -> dict[str, object]:
                nonlocal calls
                calls += 1
                return {}

            wrong = proof.claim_then_spawn(
                marker,
                "0" * 64,
                proof.child_command(proof.load_policy()),
                temp,
                proof.load_policy(),
                runner,
            )
            digest = proof.validate_implementation_result.sha256_bytes(
                marker.read_bytes()
            )
            claim = proof.claim_path(marker, proof.load_policy())
            claim.write_text("existing", encoding="utf-8")
            replay = proof.claim_then_spawn(
                marker,
                digest,
                proof.child_command(proof.load_policy()),
                temp,
                proof.load_policy(),
                runner,
            )

        self.assertEqual("marker_sha256", wrong["failure"])
        self.assertEqual("already_claimed", replay["failure"])
        self.assertEqual(0, calls)


if __name__ == "__main__":
    unittest.main()
