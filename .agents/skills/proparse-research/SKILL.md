---
name: proparse-research
description: Verify RSSW Proparse APIs and behavior before changing ABL parsing, lexing, keywords, semantic analysis, symbol resolution, schema handling, completion, navigation, or inspections in the IntelliJ plugin.
---

# Proparse Research

Investigate before implementing. The goal is a small evidence artifact, not a
speculative design.

## Workflow

1. State the exact ABL behavior or API question.
2. Search the plugin for existing usage and tests.
3. Inspect the pinned Proparse 3.7.2 source JAR or a user-provided RSSW source
   checkout. Never invent a checkout path.
4. Record evidence with file/class/method names and distinguish:
   - verified in plugin code;
   - verified in RSSW source;
   - inferred;
   - unknown.
5. Identify the smallest plugin boundary that can reuse the verified behavior.
6. List focused tests and failure cases.
7. Stop before implementation when the evidence contradicts the task or when
   the required API cannot be verified.

## Required Output

Produce a compact `research.md` or equivalent response containing:

```text
Question
Evidence
Existing plugin behavior
Recommended boundary
Tests
Unknowns / risks
```

Do not copy large source excerpts. Cite paths and summarize behavior.

## Guardrails

- Do not hardcode ABL keywords or grammar when RSSW exposes the information.
- Do not call a method merely because its name looks plausible.
- Do not modify RSSW source or cached dependency artifacts.
- Do not add a direct parser construction site outside the existing core
  boundary without explicit approval.
- Treat `treeParser01()` as fallible on incomplete or invalid source.
- Treat line positions from Proparse as 1-based unless verified otherwise.

Read [references/known-entry-points.md](references/known-entry-points.md) for
verified APIs. Read [references/recipes.md](references/recipes.md) for repeatable
search commands and evidence rules.
