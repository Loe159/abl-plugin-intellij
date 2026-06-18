from __future__ import annotations

import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SKILLS_DIR = REPO_ROOT / ".agents" / "skills"
FRONTMATTER = re.compile(r"\A---\r?\n(?P<body>.*?)\r?\n---\r?\n", re.DOTALL)
NAME = re.compile(r"^name:\s*(?P<value>[a-z0-9-]+)\s*$", re.MULTILINE)
DESCRIPTION = re.compile(r"^description:\s*(?P<value>.+?)\s*$", re.MULTILINE)


class RepositorySkillsTest(unittest.TestCase):
    def test_repo_skills_have_frontmatter_ui_metadata_and_no_todos(self) -> None:
        skill_files = sorted(SKILLS_DIR.glob("*/SKILL.md"))
        self.assertGreaterEqual(len(skill_files), 2)
        for skill_file in skill_files:
            text = skill_file.read_text(encoding="utf-8")
            with self.subTest(skill=skill_file.parent.name):
                match = FRONTMATTER.match(text)
                self.assertIsNotNone(match)
                frontmatter = match.group("body") if match else ""
                name = NAME.search(frontmatter)
                description = DESCRIPTION.search(frontmatter)
                self.assertIsNotNone(name)
                self.assertIsNotNone(description)
                self.assertEqual(skill_file.parent.name, name.group("value") if name else "")
                self.assertNotIn("TODO", text)
                self.assertGreaterEqual(len(description.group("value").strip()), 40)
                metadata = skill_file.parent / "agents" / "openai.yaml"
                self.assertTrue(metadata.is_file())
                metadata_text = metadata.read_text(encoding="utf-8")
                self.assertIn("display_name:", metadata_text)
                self.assertIn("short_description:", metadata_text)
                self.assertIn("default_prompt:", metadata_text)


if __name__ == "__main__":
    unittest.main()
