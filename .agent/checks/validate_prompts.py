#!/usr/bin/env python3
"""Validate portable read-only phase prompts without executing them."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import validate_artifacts


def unique_strings(value: Any, label: str, allow_empty: bool = False) -> list[str]:
    if (
        not isinstance(value, list)
        or (not value and not allow_empty)
        or not all(isinstance(item, str) and item for item in value)
        or len(value) != len(set(value))
    ):
        raise ValueError(f"{label} must be a unique list of non-empty strings")
    return value


def load_prompt_contract(
    path: Path,
    artifact_contract: dict[str, Any],
) -> dict[str, Any]:
    contract = json.loads(path.read_text(encoding="utf-8"))
    required = {
        "version",
        "max_prompt_bytes",
        "common_frontmatter",
        "required_sections",
        "common_required_literals",
        "prompts",
    }
    missing = required.difference(contract)
    if missing:
        raise ValueError(f"Prompt contract is missing fields: {', '.join(sorted(missing))}")
    if (
        not isinstance(contract["version"], int)
        or isinstance(contract["version"], bool)
        or contract["version"] != 1
    ):
        raise ValueError(f"Unsupported prompt contract version: {contract['version']}")
    if (
        not isinstance(contract["max_prompt_bytes"], int)
        or isinstance(contract["max_prompt_bytes"], bool)
        or contract["max_prompt_bytes"] < 1
    ):
        raise ValueError("max_prompt_bytes must be a positive integer")
    unique_strings(contract["common_frontmatter"], "common_frontmatter")
    unique_strings(contract["required_sections"], "required_sections")
    unique_strings(contract["common_required_literals"], "common_required_literals")
    prompts = contract["prompts"]
    if not isinstance(prompts, dict) or not prompts:
        raise ValueError("prompts must be a non-empty object")
    stages: set[str] = set()
    for name, specification in prompts.items():
        if not isinstance(name, str) or not name.endswith(".md") or not isinstance(specification, dict):
            raise ValueError("Each prompt must be a Markdown filename mapped to an object")
        required_spec = {"stage", "mode", "output", "required_references", "output_artifact"}
        missing_spec = required_spec.difference(specification)
        if missing_spec:
            raise ValueError(f"{name} is missing fields: {', '.join(sorted(missing_spec))}")
        stage = specification["stage"]
        if not isinstance(stage, str) or not stage or stage in stages:
            raise ValueError(f"{name} stage must be a unique non-empty string")
        stages.add(stage)
        if specification["mode"] != "read-only":
            raise ValueError(f"{name} mode must be read-only")
        output_artifact = specification["output_artifact"]
        if output_artifact not in artifact_contract["artifacts"]:
            raise ValueError(f"{name} references unknown output artifact: {output_artifact}")
        if specification["output"] != output_artifact:
            raise ValueError(f"{name} output must match output_artifact")
        unique_strings(specification["required_references"], f"{name} required_references")
    return contract


def validate_prompts(
    directory: Path,
    prompt_contract: dict[str, Any],
    artifact_contract: dict[str, Any],
) -> dict[str, Any]:
    errors: list[dict[str, str]] = []
    parsed: list[str] = []

    def add_error(prompt: str, rule: str, message: str) -> None:
        errors.append({"prompt": prompt, "rule": rule, "message": message})

    unexpected = sorted(
        path.name for path in directory.glob("*.md") if path.name not in prompt_contract["prompts"]
    )
    for name in unexpected:
        add_error(name, "unexpected_prompt", "Markdown prompt is outside the contract.")

    for name, specification in prompt_contract["prompts"].items():
        path = directory / name
        if not path.is_file():
            add_error(name, "required_prompt", "Required prompt is missing.")
            continue
        if path.stat().st_size > prompt_contract["max_prompt_bytes"]:
            add_error(name, "max_prompt_bytes", "Prompt exceeds the configured byte limit.")
        try:
            prompt = validate_artifacts.parse_artifact(path)
        except (OSError, UnicodeError, ValueError) as error:
            add_error(name, "parse_prompt", str(error))
            continue
        parsed.append(name)
        for field in prompt_contract["common_frontmatter"]:
            if field not in prompt.frontmatter:
                add_error(name, "required_frontmatter", f"Missing frontmatter: {field}")
        if prompt.frontmatter.get("prompt_version") != str(prompt_contract["version"]):
            add_error(name, "prompt_version", "prompt_version does not match the contract.")
        for field in ("stage", "mode", "output"):
            if prompt.frontmatter.get(field) != specification[field]:
                add_error(name, f"prompt_{field}", f"{field} does not match the contract.")
        for section in prompt_contract["required_sections"]:
            if section not in prompt.sections:
                add_error(name, "required_sections", f"Missing section: {section}")
            elif not prompt.sections[section]:
                add_error(name, "non_empty_sections", f"Section is empty: {section}")
        for reference in specification["required_references"]:
            if reference not in prompt.text:
                add_error(name, "required_reference", f"Missing required reference: {reference}")
        normalized_text = " ".join(prompt.text.split())
        for literal in prompt_contract["common_required_literals"]:
            if " ".join(literal.split()) not in normalized_text:
                add_error(name, "required_guardrail", f"Missing required guardrail: {literal}")
        if validate_artifacts.PLACEHOLDER.search(prompt.text):
            add_error(name, "no_placeholders", "Prompt contains unresolved placeholders.")
        output_sections = artifact_contract["artifacts"][specification["output_artifact"]][
            "required_sections"
        ]
        for section in output_sections:
            if f"`# {section}`" not in prompt.sections.get("Required Output", ""):
                add_error(name, "output_sections", f"Required Output omits artifact section: {section}")
    return {
        "valid": not errors,
        "directory": str(directory.resolve()),
        "prompts": sorted(parsed),
        "errors": errors,
    }


def format_text(result: dict[str, Any]) -> str:
    status = "VALID" if result["valid"] else "INVALID"
    lines = [f"prompt-contract: {status}"]
    for error in result["errors"]:
        lines.append(f"- {error['prompt']} {error['rule']}: {error['message']}")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    repo_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--prompts",
        type=Path,
        default=repo_root / ".agent" / "prompts",
        help="Prompt directory to validate",
    )
    parser.add_argument(
        "--prompt-contract",
        type=Path,
        default=repo_root / ".agent" / "policies" / "prompt-contract.json",
        help="Prompt contract JSON file",
    )
    parser.add_argument(
        "--artifact-contract",
        type=Path,
        default=repo_root / ".agent" / "policies" / "artifact-contract.json",
        help="Artifact contract JSON file",
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        artifact_contract = validate_artifacts.load_contract(args.artifact_contract)
        prompt_contract = load_prompt_contract(args.prompt_contract, artifact_contract)
        result = validate_prompts(args.prompts, prompt_contract, artifact_contract)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        print(f"prompt-contract: ERROR\n- {error}", file=sys.stderr)
        return 1
    if args.format == "json":
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(format_text(result))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
