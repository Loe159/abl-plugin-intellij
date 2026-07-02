from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


class HandoffLocalGapArtifactsTest(unittest.TestCase):
    def test_handoff_named_check_wrappers_exist(self) -> None:
        for relative in (
            ".agent/checks/fast.sh",
            ".agent/checks/full.sh",
            ".agent/checks/tests-policy.sh",
            ".agent/checks/secret-scan.sh",
            ".agent/scripts/fetch-issue-snapshot.sh",
            ".agent/scripts/prepare-task.sh",
            ".agent/scripts/classify-task.sh",
            ".agent/scripts/run-stage.sh",
            ".agent/scripts/validate-patch.sh",
            ".agent/scripts/collect-metrics.sh",
            ".agent/scripts/publish-draft-pr.sh",
        ):
            path = REPO_ROOT / relative
            self.assertTrue(path.is_file(), relative)
            text = path.read_text(encoding="utf-8")
            self.assertTrue(text.startswith("#!/usr/bin/env bash\n"), relative)
            self.assertIn("set -euo pipefail", text)

    def test_optional_adapter_wrappers_exist_without_claiming_provider_presence(self) -> None:
        for relative, executable in (
            (".agent/adapters/codex.sh", "codex"),
            (".agent/adapters/opencode.sh", "opencode"),
            (".agent/adapters/aider.sh", "aider"),
            (".agent/adapters/claude-code.sh", "claude"),
            (".agent/adapters/mini-swe-agent.sh", "mini-swe-agent"),
        ):
            path = REPO_ROOT / relative
            self.assertTrue(path.is_file(), relative)
            text = path.read_text(encoding="utf-8")
            self.assertIn("local_implementation_adapter.py", text)
            self.assertIn(f"command -v {executable}", text)

    def test_handoff_compatibility_schemas_exist(self) -> None:
        for relative in (
            ".agent/schemas/result.schema.json",
            ".agent/schemas/research.schema.json",
            ".agent/schemas/plan.schema.json",
        ):
            path = REPO_ROOT / relative
            self.assertTrue(path.is_file(), relative)
            self.assertIn('"$schema"', path.read_text(encoding="utf-8"))

    def test_optional_proparse_researcher_agent_exists(self) -> None:
        path = REPO_ROOT / ".agents/skills/proparse-research/agents/proparse-researcher.yaml"
        self.assertTrue(path.is_file())
        text = path.read_text(encoding="utf-8")
        self.assertIn("Proparse Researcher", text)
        self.assertIn("read-only", text)

    def test_runner_tool_allowlist_proof_exists(self) -> None:
        for relative in (
            ".agent/checks/prove_runner_tool_allowlist.py",
            ".agent/policies/runner-tool-allowlist-proof.json",
        ):
            self.assertTrue((REPO_ROOT / relative).is_file(), relative)
        text = (REPO_ROOT / ".agent/checks/prove_runner_tool_allowlist.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("non_allowlisted_adapter_blocked_before_consumption", text)
        self.assertIn("agent_invocation_authorized=false", text)

    def test_local_adapter_environment_filter_proof_exists(self) -> None:
        for relative in (
            ".agent/checks/prove_local_adapter_environment_filter.py",
            ".agent/policies/local-adapter-environment-filter-proof.json",
        ):
            self.assertTrue((REPO_ROOT / relative).is_file(), relative)
        text = (
            REPO_ROOT / ".agent/checks/prove_local_adapter_environment_filter.py"
        ).read_text(encoding="utf-8")
        self.assertIn("local_adapter_child_environment_filter", text)
        self.assertIn("provider_credential_descendant_noninheritance", text)

    def test_handoff_central_config_is_non_authorizing(self) -> None:
        config = REPO_ROOT / ".agent/config.yaml"
        self.assertTrue(config.is_file())
        text = config.read_text(encoding="utf-8")
        self.assertIn("mode: non-authorizing-reference", text)
        self.assertIn("github_write_access_in_agent: false", text)
        self.assertIn("authorized_by_status: false", text)
        self.assertIn("python_resolver: .agent/scripts/resolve-python.sh", text)
        self.assertIn("prepare_github_task: .agent/checks/prepare_github_task.py", text)
        self.assertIn("list_approved_issue_queue: .agent/checks/list_github_approved_issues.py", text)

    def test_review_and_compaction_prompts_are_present(self) -> None:
        for relative in (
            ".agent/prompts/review.md",
            ".agent/prompts/compact-progress.md",
            ".agent/templates/review.md",
        ):
            self.assertTrue((REPO_ROOT / relative).is_file(), relative)

    def test_prepare_github_task_chain_is_present_without_task_approval(self) -> None:
        for relative in (
            ".agent/checks/list_github_approved_issues.py",
            ".agent/policies/github-approved-issue-queue.json",
            ".agent/checks/prepare_github_task.py",
            ".agent/policies/prepare-github-task.json",
        ):
            self.assertTrue((REPO_ROOT / relative).is_file(), relative)
        policy = (REPO_ROOT / ".agent/policies/prepare-github-task.json").read_text(
            encoding="utf-8"
        )
        self.assertIn('"task_approval_performed": false', policy)
        script = (REPO_ROOT / ".agent/scripts/prepare-task.sh").read_text(encoding="utf-8")
        self.assertIn("queue-list", script)
        self.assertIn("fetch-check|approve-init", script)
        self.assertIn("task-check", script)
        self.assertIn("task-approve", script)
        self.assertIn("approve_task.py check", script)
        self.assertIn("approve_task.py approve", script)

    def test_golden_set_status_marker_exists_without_adopting_corpus(self) -> None:
        path = REPO_ROOT / "evals/golden-set.yaml"
        self.assertTrue(path.is_file())
        text = path.read_text(encoding="utf-8")
        self.assertIn("adoption_status: not_adopted", text)
        self.assertIn("golden_set_ready: false", text)
        self.assertIn("case_count: 0", text)
        self.assertIn("cases: []", text)
        self.assertIn("external_candidate_manifest_required: true", text)

    def test_handoff_audit_uses_current_gap_language(self) -> None:
        path = REPO_ROOT / "docs/agent-guides/handoff-implementation-audit.md"
        self.assertTrue(path.is_file())
        text = path.read_text(encoding="utf-8")

        for stale_phrase in (
            "wrappers incomplets",
            "records de metriques manuels seulement",
            "review n'est pas un stage adaptateur live",
            "Meme contrat adaptateur pour Codex/OpenCode/autre | Non implemente",
            "Mesurer chaque run | Non implemente",
            "seul le wrapper de commande locale est implemente comme nouvel adaptateur",
            "rien n'a ete implemente dans `.github/**`",
            "aucun workflow `.github/**` n'a ete ajoute",
            "approbation locale exacte et une validation de receipt. Elle n'est pas",
            "chaque checker lie les bytes exacts de policy attendus",
            "pipeline CI/publication ne sont pas",
            "references et manifests `agents/openai.yaml`",
            "et `agents/openai.yaml`",
            "| Implementer | `run_supervised_implementation.py` + adaptateur local | Implemente localement |",
            "les fichiers de reference externes nommes dans le",
            "ne sont pas necessaires pour le checkout actuel",
            "Le depot contient maintenant un vrai runner local d'implementation supervisee",
            "`isolated_process.py`",
            "`assess_runner_readiness.py`",
            "`diff_policy.py`",
            "`generate_complete_patch.py`",
            "`artifact-contract.json`",
        ):
            self.assertNotIn(stale_phrase, text)

        for current_phrase in (
            "Date d'audit initial : 2026-06-30",
            "Derniere mise a jour : 2026-07-02",
            ".github/CODEOWNERS",
            ".github/workflows/quality-gate.yml",
            "Aucun workflow agentique de build/publication n'a ete ajoute",
            "CI quality-gate non agentique",
            ".agents/skills/proparse-research/agents/openai.yaml",
            ".agents/skills/agentic-workflow-pilot/agents/openai.yaml",
            "Partiel ; runner local fonctionnel, controles runner encore incomplets",
            "aucun fichier de reference externe n'est necessaire pour",
            "L'execution du workflow, elle, depend encore d'artefacts externes",
            "outils locaux `gh` non authentifiants et non",
            "docs/agent-guides/repository-audit.md",
            "Contrats, prompts, schemas et templates",
            ".agent/checks/validate_artifacts.py",
            ".agent/checks/validate_prompts.py",
            ".agent/policies/artifact-contract.json",
            ".agent/policies/prompt-contract.json",
            "Evidence runner readiness",
            ".agent/checks/prove_parent_environment_isolation.py",
            ".agent/checks/prove_bounded_output_capture.py",
            ".agent/checks/prove_wall_clock_timeout.py",
            ".agent/checks/prove_windows_process_tree_timeout.py",
            ".agent/checks/prove_implementation_launch_transaction.py",
            ".agent/checks/prove_implementation_result_validation.py",
            ".agent/checks/prove_runner_output_post_validation.py",
            ".agent/checks/prove_implementation_patch_validation.py",
            ".agent/checks/prove_implementation_patch_receipt_validation.py",
            ".agent/checks/prove_implementation_quality_gate.py",
            ".agent/checks/prove_implementation_quality_gate_validation.py",
            "file live `agent:approved` devient bloquante",
            "`runner_controls_ready=false`",
            "Script implemente, controle runner encore partiel",
            "`implementation_quality_gate_execution` reste une evidence liee",
            "validateur independant dedie du receipt d'adoption",
            "human_golden_set_adoption_decision",
            "github_label_independently_verified=false",
            "source_state_authenticated=false",
            "approbation de recherche",
            "`validate_stage_application.py` conservent `authorized=false`",
            ".agent/checks/consume_implementation_session_start_authorization.py",
            ".agent/checks/validate_implementation_session_start_consumption.py",
            ".agent/checks/check_implementation_launch_readiness.py",
            "garantie uniforme",
            "wrappers optionnels structurellement testes",
            "observation derivable d'un receipt runner valide",
            "prompt et artefact `review.md`, contexte `review`, validation de sortie",
            "test statique `.agent/checks/tests/test_optional_provider_wrappers.py`",
            ".agent/checks/build_runner_metrics_observation.py",
            "evals/golden-set.yaml` existe maintenant comme marqueur",
            "pas de runner de comparaison live et pas de preuve d'execution reelle",
            ".agent/checks/prepare_github_task.py",
            ".agent/policies/prepare-github-task.json",
            "Il est en dry-run par defaut",
            ".agent/scripts/publish-draft-pr.sh",
            ".agent/policies/draft-pr-publication-readiness.json",
            ".agent/adapters/codex.sh",
            ".agent/adapters/claude-code.sh",
            ".agent/adapters/mini-swe-agent.sh",
            ".agent/policies/golden-set-readiness.json",
            ".agent/policies/historical-golden-set-readiness.json",
            ".agent/policies/golden-set-adoption.json",
            "`evals/golden-set.yaml` existe maintenant comme marqueur",
            "normalise maintenant l'entrypoint d'adaptateur vers le chemin absolu",
            ".agent/checks/prove_disposable_worktree.py",
            ".agent/policies/disposable-worktree-proof.json",
            "preuve fixture d'un cycle de",
            ".agent/policies/local-read-only-adapter.json",
            ".agent/checks/tests/test_local_read_only_adapter.py",
            "docs/agent-guides/local-read-only-adapter.md",
            "y compris quand la commande echoue ou depasse son",
            ".agent/checks/validate_plan_approval.py",
            ".agent/checks/check_draft_pr_publication_readiness.py",
            ".agent/policies/draft-pr-publisher.json",
            ".agent/policies/draft-pr-publication-readiness.json",
            ".agent/policies/run-metrics.json",
            ".agent/policies/runner-metrics-observation.json",
            ".agent/checks/check_multi_adapter_comparison_readiness.py",
            ".agent/policies/multi-adapter-comparison-readiness.json",
            ".agent/checks/check_historical_golden_set_readiness.py",
            "demande humaine explicite, pas une autorisation issue du statut global",
            ".agent/checks/isolated_process.py",
            ".agent/checks/validate_supervised_runner_receipt.py",
            ".agent/checks/prove_supervised_runner_execution.py",
            ".agent/checks/prove_local_adapter_environment_filter.py",
            "valide son receipt final",
            "cleanup du worktree est tente sur les",
            ".agent/checks/validate_task_approval.py",
            ".agent/checks/validate_implementation_session_approval.py",
            ".agent/checks/validate_implementation_session_start_authorization.py",
            ".agent/checks/assess_runner_readiness.py",
            ".agent/policies/local-adapter-environment-filter-proof.json",
            ".agent/policies/runner-readiness.json",
            ".agent/prompts/compact-progress.md",
            ".agent/prompts/review.md",
            ".agent/templates/review.md",
            ".agent/scripts/resolve-python.sh",
            ".agent/scripts/fetch-issue-snapshot.sh",
            "inventaire non autorisant",
            "dispatchers locaux non autorisants",
            "adaptateurs read-only manuel et local pour repeter recherche, plan et review",
            "validation de resultat, patch, receipt de patch, quality gate",
            ".agent/checks/validate_supervised_runner_receipt.py",
            ".agent/checks/validate_portable_run_initialization.py",
            ".agent/checks/validate_stage_application.py",
            ".agent/checks/validate_implementation_invocation_preflight.py",
            ".agents/skills/agentic-workflow-pilot/SKILL.md",
            ".agent/checks/run_implementation_quality_gate.py",
            ".agent/checks/validate_implementation_quality_gate.py",
            "docs/agent-guides/implementation-quality-gate.md",
            "lifecycle complet du worktree jetable",
            "timeout complet de session",
            "budget de",
            "couplage consommation-autorisation -> process",
            "filesystem pour les vrais runs",
        ):
            self.assertIn(current_phrase, text)

    def test_handoff_local_references_exist_or_are_explicitly_external(self) -> None:
        text = (REPO_ROOT / "docs/agent-guides/handoff-implementation-audit.md").read_text(
            encoding="utf-8"
        )
        references: list[str] = []
        in_code = False
        buffer: list[str] = []
        for char in text:
            if char == "`":
                if in_code:
                    value = "".join(buffer)
                    if value.startswith((".agent/", ".agents/", "docs/", "evals/", ".github/")) or value == "AGENTS.md":
                        references.append(value)
                    buffer = []
                    in_code = False
                else:
                    buffer = []
                    in_code = True
            elif in_code:
                buffer.append(char)

        self.assertTrue(references)
        allowed_missing = {
            ".github/workflows/agent-build.yml",
            ".github/workflows/publish-agent-pr.yml",
        }
        for reference in references:
            if any(marker in reference for marker in ("*", "<", ">")):
                continue
            if reference in allowed_missing:
                continue
            path = REPO_ROOT / reference
            with self.subTest(reference=reference):
                if reference.endswith("/"):
                    self.assertTrue(path.is_dir(), reference)
                else:
                    self.assertTrue(path.exists(), reference)

    def test_numbered_handoff_sections_state_current_reality_or_gap(self) -> None:
        text = (REPO_ROOT / "docs/agent-guides/handoff-implementation-audit.md").read_text(
            encoding="utf-8"
        )
        lines = text.splitlines()
        headings: list[tuple[int, str]] = []
        for index, line in enumerate(lines, 1):
            if line.startswith("### ") and (
                "Section " in line
                or line.startswith("### 1.")
                or line.startswith("### 2.")
                or line.startswith("### 3.")
                or line.startswith("### 5.")
                or line.startswith("### 8.")
            ):
                headings.append((index, line))
        self.assertTrue(headings)
        headings.append((len(lines) + 1, "END"))
        markers = (
            "Realite implementee",
            "Etat :",
            "Implemente",
            "Present :",
            "Manquant",
            "Ecart",
            "Correction",
            "Note :",
            "Notes :",
        )
        for (start, heading), (end, _next_heading) in zip(headings, headings[1:]):
            body = "\n".join(lines[start:end - 1])
            with self.subTest(heading=heading, line=start):
                self.assertTrue(any(marker in body for marker in markers), heading)


if __name__ == "__main__":
    unittest.main()
