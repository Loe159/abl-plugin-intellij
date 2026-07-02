from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
ADAPTERS = REPO_ROOT / "adapters"


WRAPPERS = {
    "codex.sh": "codex",
    "opencode.sh": "opencode",
    "aider.sh": "aider",
    "claude-code.sh": "claude",
    "mini-swe-agent.sh": "mini-swe-agent",
}


class OptionalProviderWrapperTest(unittest.TestCase):
    def test_wrappers_share_the_local_implementation_adapter_contract(self) -> None:
        for wrapper, command in WRAPPERS.items():
            with self.subTest(wrapper=wrapper):
                text = (ADAPTERS / wrapper).read_text(encoding="utf-8")

                self.assertIn("set -euo pipefail", text)
                self.assertIn("--expected-session <expected-session.json>", text)
                self.assertIn("--workspace <worktree>", text)
                self.assertIn('expected_session="$2"', text)
                self.assertIn('workspace="$4"', text)
                self.assertIn("local_implementation_adapter.py", text)
                self.assertIn('--expected-session "$expected_session"', text)
                self.assertIn('--workspace "$workspace"', text)
                self.assertIn(f"command -v {command}", text)
                self.assertIn(f"-- {command} \"$@\"", text)

    def test_wrappers_do_not_claim_authorization_or_publication(self) -> None:
        forbidden = (
            "authorized=true",
            "publication_authorized=true",
            "network_authorized=true",
            "git push",
            "gh pr create",
        )
        for wrapper in WRAPPERS:
            with self.subTest(wrapper=wrapper):
                text = (ADAPTERS / wrapper).read_text(encoding="utf-8")
                for needle in forbidden:
                    self.assertNotIn(needle, text)


if __name__ == "__main__":
    unittest.main()
