# Dossier de transfert Codex — Workflow agentique autonome et supervisé de développement

> **Note historique 2026-07-04 :** ce transfert est conserve comme contexte
> initial. L'etat courant du workflow vit dans
> `docs/agent-guides/handoff-implementation-audit.md`,
> `docs/agent-guides/workflow-status.md`,
> `docs/agent-guides/runner-readiness.md` et
> `docs/agent-guides/supervised-runner-workflow.md`.

> **Destinataire :** agent Codex chargé de poursuivre concrètement le projet.  
> **Statut :** document autonome de cadrage et d’implémentation.  
> **Date de consolidation :** 2026-06-08.  
> **Langue du projet de workflow :** français pour la documentation utilisateur ; anglais recommandé dans les fichiers techniques destinés aux agents.  
> **Important :** Codex ne dispose pas de la conversation originale ni des documents joints. Les éléments nécessaires sont reproduits ou synthétisés ci-dessous. Toute information non connue est explicitement signalée.

---

# 1. Objectif

## 1.1 Vision générale

Construire un workflow de développement agentique **économique**, **portable**, **progressivement autonome** et **supervisé par un humain**. Il doit pouvoir traiter en continu des bugs et des features avec une qualité compatible avec une base de code réelle : pas de duplication inutile, pas de régression silencieuse, pas de refactor hors périmètre, respect de l’architecture existante et contrôle des risques.

Le workflow doit rester indépendant d’un fournisseur ou d’un agent unique. Il doit pouvoir être expérimenté avec plusieurs harnesses et plusieurs modèles, notamment :

- Codex CLI ;
- Claude Code ;
- OpenCode ;
- Aider ;
- éventuellement mini-swe-agent et d’autres adaptateurs.

La première cible est un **plugin IntelliJ pour OpenEdge ABL écrit en Kotlin**. Le même socle devra ensuite être réutilisable pour d’autres projets, notamment C# et web, en remplaçant principalement les scripts déterministes de build, lint et test.

## 1.2 Problèmes à résoudre

Le workflow doit répondre simultanément aux problèmes suivants :

1. **Agents peu fiables sur les bases de code existantes.** Les agents peuvent générer du code plausible mais incorrect, réinventer des abstractions existantes, introduire de la duplication ou traiter un symptôme au lieu de la cause.
2. **Saturation et pollution du contexte.** Les recherches de fichiers, logs de build, sorties JSON et tentatives successives dégradent progressivement la qualité des réponses.
3. **Risque de prompt injection.** Une issue GitHub, un commentaire, un fichier ou une dépendance peuvent contenir des instructions malveillantes. Le filtrage de texte seul ne suffit pas.
4. **Sur-automatisation dangereuse.** Un LLM ne doit pas décider seul de pousser du code, créer une PR arbitraire, fusionner dans `main`, modifier la CI ou publier un plugin.
5. **Verrouillage fournisseur.** Le workflow ne doit pas dépendre structurellement des commandes internes d’un seul agent.
6. **Coût.** Le workflow doit rester sobre en tokens et exploitable avec un budget réduit, visé autour de quelques euros par mois pour un volume modeste. Les prix et free tiers étant volatils, ils doivent rester configurables.
7. **Spécificités ABL / IntelliJ.** Les modèles risquent d’halluciner des API IntelliJ ou de dupliquer la connaissance du langage ABL au lieu de réutiliser RSSW/Proparse.

## 1.3 Résultat final attendu

Le résultat cible est une petite plateforme versionnée dans le dépôt du plugin, composée de scripts et de conventions portables :

```text
Issue approuvée
  → normalisation déterministe de la tâche
  → recherche read-only compacte
  → plan d’implémentation compact
  → validation humaine aux points à fort levier
  → implémentation isolée dans un worktree ou workspace jetable
  → validations déterministes externes au LLM
  → publication déterministe d’une PR en brouillon
  → CI complète
  → review humaine
  → merge manuel
```

La plateforme devra pouvoir changer d’agent par configuration sans changer la logique métier de l’orchestration.

## 1.4 Critères de réussite

Le workflow sera considéré comme correctement mis en place lorsque :

- les tâches déterministes ne sont jamais déléguées au LLM lorsqu’un script classique suffit ;
- le job qui exécute l’agent n’a aucun jeton GitHub en écriture ;
- l’agent ne peut jamais fusionner dans `main` ni publier une release ;
- toutes les PR générées sont initialement des brouillons et passent par la protection de branche existante ;
- les fichiers sensibles sont bloqués ou nécessitent une validation humaine explicite ;
- une issue approuvée peut produire de manière reproductible `task.md`, `research.md`, `plan.md`, `progress.md`, `verification.md` et `patch.diff` ;
- le contexte est compacté entre les phases et après les phases d’implémentation importantes ;
- toute modification liée au langage ABL inspecte RSSW/Proparse avant implémentation ;
- les checks existants restent obligatoires : `ktlint`, `detekt`, build/tests et `verifyPlugin` ;
- au moins cinq issues historiques servent de golden set comparatif ;
- les exécutions produisent des métriques minimales : agent, modèle, coût, durée, statut, diff, corrections humaines, fusion ou rejet, régression éventuelle ;
- le même contrat d’adaptateur peut être utilisé avec Codex, OpenCode et au moins un autre agent.

---

# 2. Besoins et contraintes

## 2.1 Fonctionnalités attendues

### Obligatoires pour la première version

- Récupérer une issue GitHub approuvée.
- Transformer son contenu en spécification compacte et normalisée.
- Exécuter séparément les phases `research`, `plan`, `implement`, puis `review` consultative.
- Produire un patch Git, pas une modification directe de `main`.
- Vérifier le patch avec des scripts déterministes.
- Refuser automatiquement les modifications interdites.
- Créer une branche et une PR en brouillon via un composant déterministe séparé du LLM.
- Mesurer chaque exécution.
- Tester plusieurs adaptateurs d’agents.
- Fournir un skill portable `proparse-research` pour les tâches ABL.

### Attendues à moyen terme

- Lancer en continu une seule issue approuvée à la fois.
- Classer les tâches selon un niveau de risque.
- Comparer les agents et modèles sur un golden set.
- Autoriser la création automatique de PR en brouillon pour les seuls changements à faible risque, après stabilisation.
- Étendre le même pattern aux projets C# et web.

### Optionnelles ou différées

- Renovate pour les mises à jour de dépendances, dans une voie séparée.
- Gitleaks pour la détection de secrets.
- Qodana, couverture, duplication, Semgrep, Trivy et mutation testing selon les besoins mesurés.
- OpenTelemetry / Langfuse / promptfoo / Inspect AI si les artefacts JSONL deviennent insuffisants.
- Tests UI IntelliJ avancés avec `runIdeForUiTests`, Xvfb, `intellij-ui-test-robot` ou Starter framework.

## 2.2 Contraintes techniques

- Projet initial : plugin IntelliJ Platform en Kotlin pour OpenEdge ABL.
- Build probablement Gradle ; vérifier les commandes réellement présentes dans le dépôt avant toute modification.
- Qualité déjà mise en place par le propriétaire :
  - `verifyPlugin` ;
  - `detekt` ;
  - `ktlint` ;
  - workflow GitHub `quality-gate` ;
  - `CODEOWNERS` ;
  - protection de la branche `main`.
- Le plugin doit réutiliser RSSW / Proparse comme source de vérité pour la connaissance ABL lorsqu’elle existe.
- Les agents précédents ont déjà commis une erreur structurante : coder en dur des mots-clés tels que `SELECT` et `WHERE` au lieu de s’appuyer sur PSI / Proparse. Le nouveau workflow doit empêcher cette dérive.
- Le dépôt du plugin, sa structure exacte, les workflows existants et le chemin réel du checkout RSSW ne sont pas fournis dans ce transfert. Codex doit les inspecter avant d’éditer.
- Le nom exact du dépôt RSSW doit être vérifié. Les échanges mentionnent un checkout adjacent de type `sonar-openedge/` contenant notamment `proparse/`, `openedge-checks/` et `openedge-plugin/`. Ne pas inventer un chemin si le dépôt réel diffère.

## 2.3 Contraintes budgétaires

- Cible utilisateur : workflow économique, idéalement autour de quelques euros par mois pour un faible volume.
- Ne pas coupler l’architecture à un free tier ou à un modèle précis : modèles gratuits, limites et prix changent fréquemment.
- Prévoir des budgets configurables par phase : tours, durée et coût maximal.
- Utiliser les modèles coûteux uniquement lorsque le niveau de risque ou la complexité le justifie.
- Privilégier le cache de prompts lorsque le fournisseur le permet.
- Garder un fallback payant à coût faible plutôt que dépendre entièrement de modèles gratuits instables.

## 2.4 Contraintes humaines

- Le projet est piloté initialement par un développeur solo.
- La review humaine est une ressource rare : elle doit se concentrer sur les artefacts à fort levier, notamment la recherche et le plan.
- L’objectif n’est pas l’autonomie totale immédiate mais une autonomie supervisée qui augmente progressivement.
- Le propriétaire veut pouvoir tester plusieurs agents et LLM avant de choisir les combinaisons les plus efficaces.

## 2.5 Contraintes de sécurité

### Règles strictes

- Ne jamais donner simultanément au LLM : contenu non fiable, secrets privés et capacité de communication externe en écriture.
- Ne jamais exposer au job agent un jeton GitHub en écriture.
- Ne jamais permettre au LLM d’exécuter directement :

```bash
gh pr create
gh issue comment
gh label create
git push
git merge
```

- Ne jamais auto-merger les PR dans la première version.
- Ne jamais autoriser une modification autonome de `.github/**`, `.agent/**`, des scripts de build ou des fichiers Gradle.
- Traiter les artefacts produits par l’agent comme non fiables jusqu’à validation externe.
- Ne pas considérer la suppression de phrases suspectes dans le texte d’une issue comme une frontière de sécurité. Une sanitization peut compléter le système, jamais le sécuriser à elle seule.
- Éviter `pull_request_target` pour exécuter du code non fiable.
- Épingler les actions GitHub tierces sur un SHA complet lorsque le workflow est réellement créé.
- Limiter les permissions GitHub au niveau du workflow et du job.
- Désactiver ou restreindre le réseau autant que possible.

### Nuance critique sur les clés LLM

Un agent CLI exécuté dans un runner CI a généralement besoin d’accéder à une clé LLM ou à un proxy. Cette clé peut être exposée à un agent compromis si elle se trouve simplement dans l’environnement et si l’agent peut lancer des commandes arbitraires. La première implémentation doit donc documenter explicitement le modèle retenu :

- clé éphémère et plafonnée ; ou
- proxy local / distant à quota limité ; ou
- wrapper qui n’hérite pas de la clé dans les sous-processus exécutables par le modèle ; ou
- exécution locale supervisée avant CI autonome.

Ce point n’est pas résolu dans la conversation et nécessite une décision avant l’autonomie CI réelle.

## 2.6 Préférences exprimées

- Portabilité entre agents et modèles avant sophistication.
- Automatiser de manière déterministe tout ce qui peut l’être.
- HITL obligatoire pour les actions à risque.
- Commencer avec le plugin IntelliJ ABL puis étendre à C# et web.
- Ne pas dupliquer la connaissance ABL dans le plugin si RSSW/Proparse la fournit déjà.
- Introduire un skill réutilisable avant de créer un sous-agent Proparse complexe.
- Mesurer avant d’ajouter de l’infrastructure lourde.

## 2.7 Éléments explicitement exclus ou différés

### Exclus de la première version

- auto-merge ;
- publication automatique d’une release du plugin ;
- modification autonome de la CI ;
- modification autonome de Gradle ;
- ingestion automatique et aveugle de toutes les issues publiques ;
- accès direct du LLM aux opérations GitHub en écriture ;
- base de données d’orchestration complexe ;
- architecture multi-agent anthropomorphisée sans bénéfice mesuré ;
- RAG global de toute la documentation IntelliJ ;
- dépendance structurelle à un agent unique.

### Différés

- Langfuse auto-hébergé ;
- n8n ou Activepieces ;
- Qodana si non déjà présent ;
- mutation testing PIT ;
- tests UI exhaustifs ;
- parallélisation de plusieurs issues ;
- MCP externes ;
- GitHub App dédiée ;
- auto-publication des PR à faible risque.

---

# 3. Workflow agentique envisagé

## 3.1 Vue d’ensemble

```text
Issue GitHub
  │
  ├─ label manuel agent:approved
  ▼
[0] Triage et normalisation déterministes
  ▼
[1] Classification du risque
  ▼
[2] Recherche read-only
  ▼
[3] Review humaine éventuelle de la recherche
  ▼
[4] Planification read-only
  ▼
[5] Review humaine du plan selon le risque
  ▼
[6] Implémentation isolée, phase par phase
  ▼
[7] Compaction intentionnelle fréquente
  ▼
[8] Validation déterministe extérieure
  ▼
[9] Review LLM consultative optionnelle
  ▼
[10] Publication déterministe d’une PR en brouillon
  ▼
[11] CI complète, CODEOWNERS et review humaine
  ▼
[12] Merge manuel uniquement
```

## 3.2 Parcours selon la complexité

### Parcours A — changement simple

Exemples : documentation, typo, renommage local, test très localisé, correction faible risque de moins de 50 lignes sans changement d’API.

```text
issue approuvée → mini-spec → implémentation → checks → draft PR → review humaine
```

La recherche détaillée et la validation du plan peuvent être omises.

### Parcours B — bug ou feature standard

Exemples : bug impliquant plusieurs classes, comportement PSI ou parsing localisé, nouvelle autocomplétion, test d’intégration, changement estimé entre environ 50 et 500 lignes.

```text
issue approuvée → recherche → plan → validation humaine du plan
→ implémentation phase par phase → checks → draft PR → review humaine
```

### Parcours C — changement risqué ou complexe

Exemples : threading IntelliJ BGT/EDT, `plugin.xml`, dépendances, Gradle, CI, architecture, API publique, refactor transversal, parsing profond, plus de 500 lignes ou plus de 12 fichiers.

```text
issue approuvée → recherche approfondie → validation humaine de la recherche
→ plan détaillé → validation humaine du plan
→ implémentation par phases → validations humaines intermédiaires
→ checks complets → draft PR → review humaine approfondie
```

Dans la première version automatisée, seuls A et B sont candidats à un flux semi-automatique. C reste manuel.

## 3.3 Étape 0 — file d’attente GitHub

### Objectif

Utiliser GitHub Issues et labels comme file d’attente minimale et état du workflow.

### Entrées

- Issue GitHub.
- Labels ajoutés par un humain.

### Actions

Utiliser progressivement les labels suivants :

```text
agent:candidate
agent:approved
agent:researching
agent:research-review
agent:planning
agent:plan-review
agent:implementing
agent:blocked
agent:patch-ready
agent:pr-opened
agent:failed

risk:low
risk:medium
risk:high

adapter:codex
adapter:opencode
adapter:claude-code
adapter:aider
```

### Sorties

- Une issue clairement éligible ou non éligible.
- Un état visible sans base de données supplémentaire.

### Responsable

- Humain pour l’approbation initiale.
- Script déterministe pour les transitions simples.

### Outils nécessaires

- `gh issue view`, `gh issue edit` ou API GitHub uniquement dans les composants déterministes autorisés.

### Conditions de validation

- Le label `agent:approved` est présent.
- L’issue n’est pas déjà en cours.
- Le niveau de risque est défini ou calculable.

### Erreurs et escalade humaine

- Issue externe ou ambiguë : arrêt et demande de triage humain.
- Plusieurs labels de statut incohérents : arrêt et normalisation manuelle ou scriptée.

## 3.4 Étape 1 — préparation et normalisation de la tâche

### Objectif

Ne jamais injecter aveuglément l’intégralité d’une issue ou de commentaires externes dans l’agent. Produire un artefact compact, traçable et approuvé.

### Entrées

- Numéro d’issue.
- Métadonnées GitHub.
- Corps de l’issue.
- Éventuels commentaires explicitement approuvés.

### Actions

Le script `.agent/scripts/prepare-task.sh` doit :

1. récupérer l’issue en JSON ;
2. vérifier `agent:approved` ;
3. refuser ou isoler les commentaires externes non approuvés ;
4. limiter la taille des champs ;
5. conserver les données utiles ;
6. produire `task.md` ;
7. produire `metadata.json` ;
8. enregistrer le commit de base ;
9. préparer un clone ou worktree jetable.

### Sorties

`docs/agent-work/ISSUE-123/task.md` ou un équivalent temporaire :

```md
---
issue: 123
risk: medium
approved_by: <github-user>
source_author_trusted: true
created_at: <iso8601>
base_commit: <sha>
---

# Goal

...

# Expected behavior

...

# Current behavior

...

# Acceptance criteria

- [ ] ...

# Constraints

- Ne pas modifier plugin.xml
- Ne pas ajouter de dépendance

# Out of scope

- ...
```

### Responsable

- Normalizer déterministe.

### Outils nécessaires

- Bash ou Python ;
- `gh` dans un job distinct et borné ;
- `jq` si Bash.

### Conditions de validation

- Spécification lisible et compacte.
- Source, commit de base et approbateur enregistrés.
- Aucun commentaire non fiable injecté par défaut.

### Erreurs et escalade humaine

- Critères d’acceptation absents ou ambigus : statut `agent:blocked`, demander une clarification humaine.
- Issue externe : demander validation explicite de `task.md`.

## 3.5 Étape 2 — classification du risque

### Objectif

Déterminer le parcours A, B ou C et les gates HITL requis.

### Entrées

- `task.md` ;
- fichiers potentiellement concernés si déjà identifiés ;
- règles dans `.agent/policies/risk-rules.yaml`.

### Actions

Appliquer d’abord des règles déterministes :

- chemins sensibles ;
- nombre de fichiers ;
- volume du diff lorsque disponible ;
- mots-clés liés au threading, Gradle, CI, dépendances, `plugin.xml`, API publique ;
- issue externe ;
- accès réseau requis ;
- modification potentielle de parsing profond.

Une évaluation LLM peut fournir un avis, jamais diminuer automatiquement le risque calculé.

### Sorties

- `risk:low`, `risk:medium` ou `risk:high` ;
- justification.

### Responsable

- Classifier déterministe.
- LLM optionnel consultatif.

### Outils nécessaires

- Script Python ou Bash ;
- YAML de règles.

### Conditions de validation

- Toute règle forte élève le risque ; aucune heuristique LLM ne peut l’abaisser seule.

### Erreurs et escalade humaine

- Incertitude : choisir le risque supérieur et demander validation humaine.

## 3.6 Étape 3 — recherche read-only

### Objectif

Comprendre l’existant avant de proposer une solution. Produire une carte factuelle compacte et limiter la pollution du contexte principal.

### Entrées

- `AGENTS.md` ;
- `task.md` ;
- dépôt du plugin en lecture seule ;
- guides internes pertinents ;
- checkout RSSW en lecture seule pour toute tâche ABL concernée ;
- skill `proparse-research` si déclenché.

### Actions

- Rechercher les fichiers pertinents.
- Décrire le flux actuel.
- Identifier les tests existants.
- Identifier les patterns déjà utilisés.
- Pour ABL : rechercher d’abord dans le plugin, puis dans RSSW/Proparse, puis dans les modules consommateurs RSSW, puis dans les tests.
- Enregistrer les chemins, classes, méthodes et lignes utiles.
- Ne pas écrire de code.
- Ne pas proposer de refactor global.

### Sorties

`research.md` :

```md
---
stage: research
issue: 123
git_commit: <sha>
status: complete
---

# Research question

...

# Summary

...

# Current flow

1. ...

# Relevant components

## Parser
- `path/File.kt:42-87`
- Responsabilité actuelle
- Interactions

## Tests
- `path/FileTest.kt:20-65`
- Scénarios déjà couverts

# Existing patterns to reuse

...

# Open questions

...
```

### Responsable

- Agent `researcher` read-only.
- Pour ABL : skill `proparse-research`, puis éventuellement sous-agent `proparse-researcher` lorsque le processus est stabilisé.

### Outils nécessaires

- recherche fichiers : `rg`, `find`, lecture de fichiers ;
- accès lecture seule au dépôt RSSW ;
- éventuellement historique Git en lecture seule ;
- aucun outil d’écriture.

### Conditions de validation

- Les composants critiques sont identifiés.
- Les tests existants sont recensés.
- Les incertitudes sont déclarées.
- Pour ABL : aucune proposition de liste de mots-clés manuelle, regex de contournement ou duplication de grammaire.

### Erreurs et escalade humaine

- Recherche contradictoire ou trop vague : refaire une passe avec consignes plus précises.
- Dépendance RSSW non accessible : bloquer la tâche ABL et demander le chemin ou le checkout.
- Risque moyen au début du projet : review humaine recommandée.
- Risque élevé : review humaine obligatoire.

## 3.7 Étape 4 — validation humaine de la recherche

### Objectif

Concentrer l’attention humaine au point où elle a le plus de levier.

### Entrées

- `task.md` ;
- `research.md`.

### Actions humaines

Vérifier :

- les bons composants ont-ils été trouvés ?
- le flux correspond-il réellement à l’architecture ?
- les tests existants ont-ils été trouvés ?
- une contrainte IntelliJ manque-t-elle ?
- RSSW/Proparse a-t-il été inspecté lorsqu’il le fallait ?
- la recherche confond-elle symptôme et cause ?

### Sorties

- recherche approuvée ; ou
- commentaires correctifs ; ou
- recherche rejetée et relancée.

### Responsable

- Propriétaire humain.

### Conditions de validation

- Requise pour `risk:high`.
- Recommandée pour `risk:medium` pendant la période pilote.

## 3.8 Étape 5 — planification read-only

### Objectif

Transformer une recherche approuvée en contrat d’implémentation précis, minimal et vérifiable.

### Entrées

- `AGENTS.md` ;
- `task.md` ;
- `research.md` ;
- guides pertinents ;
- recettes Proparse pertinentes.

### Actions

- Décrire l’état actuel et l’état final souhaité.
- Décomposer en phases.
- Lister les fichiers à éditer.
- Prévoir les tests de non-régression.
- Pour un bug, privilégier red/green : écrire un test qui échoue, confirmer l’échec, appliquer le correctif minimal, confirmer le succès.
- Déclarer explicitement ce qui est hors périmètre.
- Déclarer les vérifications automatiques et manuelles.
- Arrêter et demander aide humaine si une hypothèse importante reste non vérifiée.

### Sorties

`plan.md` :

```md
---
stage: plan
issue: 123
based_on_research: research.md
status: awaiting_approval
---

# Overview

...

# Current state

...

# Desired end state

...

# Key discoveries

...

# Out of scope

...

# Phase 1 — Add a regression test

## Files
- `src/test/...`

## Changes
...

## Automated verification
- [ ] Le nouveau test échoue sur le code de base
- [ ] Les tests existants restent verts

# Phase 2 — Apply the fix

## Files
- `src/main/...`

## Changes
...

## Automated verification
- [ ] `./gradlew ktlintCheck detekt test`

# Phase 3 — Full validation

## Automated verification
- [ ] `./gradlew build verifyPlugin`

## Manual verification
- [ ] Vérifier le comportement dans une IDE de test
```

### Responsable

- Agent `planner` read-only.

### Outils nécessaires

- lecture seule du dépôt ;
- lecture des artefacts compacts ;
- aucune écriture de code.

### Conditions de validation

Refuser le plan s’il :

- ajoute un refactor non nécessaire ;
- modifie trop de fichiers ;
- n’ajoute pas de test pertinent ;
- invente une abstraction déjà existante ;
- touche Gradle, `plugin.xml` ou threading sans justification ;
- masque une incertitude ;
- ne prévoit pas de checks.

### Erreurs et escalade humaine

- `risk:medium` : validation humaine obligatoire pendant la phase pilote.
- `risk:high` : validation humaine toujours obligatoire.
- divergences : retour à la recherche.

## 3.9 Étape 6 — implémentation isolée

### Objectif

Appliquer exactement le plan approuvé dans un espace jetable, sans accès GitHub en écriture.

### Entrées

- `AGENTS.md` ;
- `task.md` ;
- `research.md` ;
- `plan.md` approuvé ;
- `progress.md` éventuel ;
- guides pertinents ;
- worktree ou clone jetable.

### Actions

- Modifier uniquement les fichiers prévus.
- Procéder phase par phase.
- Lancer les checks rapides après chaque phase utile.
- Pour les bugs, appliquer red/green.
- Produire des commits locaux atomiques si utile.
- Mettre à jour `progress.md`.
- Stopper si le dépôt réel diverge du plan au lieu d’improviser.
- Ne jamais pousser ni créer de PR.

### Sorties

- modifications locales ;
- `progress.md` ;
- `verification.md` partiel ;
- `patch.diff` à la fin.

### Responsable

- Agent `implementer`.

### Outils nécessaires

- écriture limitée au workspace plugin ;
- commandes de test autorisées ;
- Git local ;
- aucun token GitHub en écriture ;
- RSSW en lecture seule si nécessaire.

### Conditions de validation

- Le diff respecte le plan.
- Les fichiers modifiés sont autorisés.
- Les checks rapides passent.
- Aucun test n’est affaibli.

### Erreurs et escalade humaine

- Divergence plan / dépôt : statut `agent:blocked`.
- Modification d’un chemin protégé : blocage.
- Besoin de dépendance nouvelle : blocage et proposition séparée.
- Boucle ou coût dépassé : arrêt propre et compaction.

## 3.10 Étape 7 — compaction intentionnelle fréquente

### Objectif

Éviter la saturation du contexte et préserver une trajectoire correcte.

### Entrées

- état courant ;
- logs importants ;
- résultats de tests ;
- plan ;
- modifications locales.

### Actions

Après une phase, une tentative importante ou un volume de logs élevé, produire :

```md
# Goal

...

# Completed phases

- [x] Phase 1 ...

# Files changed

- `...`

# Verified commands

- `./gradlew test --tests ...` ✅

# Current blocker

...

# Remaining work

...

# Important discoveries

...

# Do not repeat

- Analyse déjà effectuée sur ...
- Approche rejetée car ...
```

Puis redémarrer une session propre en injectant seulement :

```text
AGENTS.md
+ task.md
+ research.md
+ plan.md
+ progress.md
+ fichiers explicitement utiles
```

### Sorties

- `progress.md` compact.

### Responsable

- Agent `implementer` à la fin de phase, ou script demandant une compaction dédiée.

### Outils nécessaires

- prompt de compaction ;
- limite de tours et durée.

### Conditions de validation

- Résumé exact, factuel, sans transcript complet.
- Approches rejetées et blocages conservés.

### Erreurs et escalade humaine

- Si la compaction perd des éléments critiques, revenir à l’artefact précédent ou demander validation humaine.

## 3.11 Étape 8 — validation déterministe externe

### Objectif

Ne jamais laisser l’agent décider seul que son travail est correct.

### Entrées

- `patch.diff` ;
- checkout propre ;
- règles de sécurité ;
- scripts de qualité.

### Actions

Exécuter :

```bash
.agent/checks/diff-policy.sh
.agent/checks/tests-policy.sh
.agent/checks/secret-scan.sh
.agent/checks/fast.sh
.agent/checks/full.sh
```

Exemples de checks rapides :

```bash
#!/usr/bin/env bash
set -euo pipefail

./gradlew \
  ktlintCheck \
  detekt \
  test
```

Exemple de checks complets à adapter après inspection réelle des tâches Gradle :

```bash
#!/usr/bin/env bash
set -euo pipefail

./gradlew \
  ktlintCheck \
  detekt \
  test \
  build \
  verifyPlugin
```

Suggestion à vérifier selon la version du plugin Gradle IntelliJ : ajouter si disponibles :

```text
verifyPluginStructure
verifyPluginProjectConfiguration
```

### Sorties

- `verification.md` ;
- statut accepté ou rejeté.

### Responsable

- Validator déterministe.

### Outils nécessaires

- Gradle ;
- scripts shell ou Python ;
- éventuellement Gitleaks.

### Conditions de validation

- Tous les scripts passent.
- Aucun chemin interdit modifié.
- Aucun affaiblissement des tests.
- Diff sous les limites.

### Erreurs et escalade humaine

- Échec de lint/test/build : retour à l’implémentation dans la limite du budget.
- Échec de sécurité ou chemin interdit : blocage humain obligatoire.

## 3.12 Étape 9 — review LLM consultative optionnelle

### Objectif

Ajouter une passe critique indépendante sans lui accorder de pouvoir de validation finale.

### Entrées

- `task.md` ;
- `research.md` ;
- `plan.md` ;
- `patch.diff` ;
- `verification.md`.

### Actions

- Chercher les écarts au plan.
- Chercher duplication, régression potentielle, hallucination d’API IntelliJ, tests insuffisants et modifications hors périmètre.
- Ne pas corriger directement le code.

### Sorties

- `review.md` avec observations classées.

### Responsable

- Agent `reviewer` read-only, idéalement avec un modèle ou une session distincte.

### Conditions de validation

- La review ne peut pas approuver seule la PR.

### Erreurs et escalade humaine

- Alerte importante : blocage de publication ou label `needs-human-review`.

## 3.13 Étape 10 — publication déterministe de la PR

### Objectif

Créer la branche et la PR brouillon sans donner de droits GitHub au LLM.

### Entrées

- patch validé ;
- issue ;
- rapport de vérification ;
- checkout propre.

### Actions

Un composant privilégié séparé doit :

1. télécharger le patch ;
2. vérifier son hash ;
3. exécuter `git apply --check` ;
4. appliquer le patch sur un checkout propre ;
5. relancer la politique de diff ;
6. créer une branche `agent/issue-123/run-456` ;
7. pousser la branche ;
8. créer une PR en brouillon ;
9. lier l’issue ;
10. ajouter labels et résumé.

### Sorties

- PR en brouillon.

### Responsable

- Publisher déterministe.

### Outils nécessaires

- `git` ;
- `gh` ;
- `GITHUB_TOKEN` limité aux permissions nécessaires, uniquement dans ce job ;
- plus tard éventuellement GitHub App dédiée.

### Conditions de validation

- Patch préalablement validé.
- Aucune modification additionnelle introduite pendant publication.
- PR en brouillon uniquement.

### Erreurs et escalade humaine

- Conflit ou patch non applicable : blocage et nouvelle exécution depuis un commit de base à jour.
- Chemin sensible : publication refusée jusqu’à validation humaine.

## 3.14 Étape 11 — CI, review humaine et merge manuel

### Objectif

Conserver les garanties habituelles de GitHub.

### Entrées

- PR brouillon.

### Actions

- Exécuter `quality-gate` existant.
- Exiger CODEOWNERS et protection de `main`.
- Relire en priorité plan, tests et fichiers sensibles.
- Tester manuellement l’IDE lorsque nécessaire.
- Passer la PR en prête pour review seulement après vérification.
- Fusionner manuellement.

### Sorties

- PR fusionnée ou rejetée.

### Responsable

- Humain.

### Conditions de validation

- Quality gate vert.
- Approval humaine.
- Aucun doute non traité.

---

# 4. Agents

## 4.1 Orchestrator déterministe

### Nom et rôle

`workflow-orchestrator` — pilote les étapes, états, budgets et artefacts. Ce n’est pas un LLM.

### Responsabilités

- Séquencer les phases.
- Appliquer les règles de risque.
- Appeler les adaptateurs.
- Gérer limites de tours, durée et coût.
- Collecter les sorties.
- Déclencher les validations et HITL.

### Limites

- Ne décide pas de l’architecture métier.
- Ne contourne jamais les gates humaines.

### Outils et accès

- Bash ou Python ;
- filesystem de travail ;
- accès Git local ;
- API GitHub uniquement dans scripts dédiés.

### Informations reçues et produites

- Reçoit configuration, issue et artefacts.
- Produit états, logs JSONL et appels aux phases.

### Prompt système proposé

Aucun : composant déterministe.

### Interactions

- Appelle normalizer, classifier, adapters, validator et publisher.

## 4.2 Normalizer déterministe

### Nom et rôle

`task-normalizer` — transforme l’issue GitHub en spécification approuvable.

### Responsabilités

- Vérifier labels.
- Limiter les entrées non fiables.
- Produire `task.md` et `metadata.json`.

### Limites

- Ne déduit pas des exigences métier manquantes.

### Outils et accès

- `gh issue view`, `jq`, Bash/Python.

### Prompt système proposé

Aucun.

## 4.3 Researcher généraliste

### Nom et rôle

`codebase-researcher` — explorateur read-only.

### Responsabilités

- Cartographier l’existant.
- Identifier flux, composants, tests et patterns.
- Produire une synthèse compacte.

### Limites

- Aucun edit.
- Aucun patch.
- Aucun commit.
- Pas de refactor ou solution détaillée avant la planification.

### Outils et accès

- Lecture seule plugin ;
- `rg`, `find`, `git log` en lecture ;
- skills pertinents.

### Informations reçues et produites

- Reçoit `AGENTS.md`, `task.md`, guides.
- Produit `research.md`.

### Prompt système proposé

```text
You are a read-only codebase researcher.

Your job is to describe how the existing system works before any implementation
is proposed. Search broadly enough to identify the relevant flow, tests and
existing patterns. Record exact file paths, classes, methods and line ranges
when available.

You may search and read files. You may inspect read-only git history when useful.
You may not edit files, create patches, commit, push, propose broad refactors or
skip uncertainties. Return only a compact research.md report using the required
template. If information is missing, state it explicitly.
```

### Interactions

- Fournit sa synthèse au planner.
- Peut appeler le skill `proparse-research` lorsque déclenché.

## 4.4 Skill portable `proparse-research`

### Nom et rôle

`proparse-research` — procédure réutilisable pour investiguer RSSW/Proparse avant toute évolution liée au langage ABL.

### Responsabilités

- Empêcher duplication de grammaire et listes manuelles.
- Forcer l’inspection de RSSW.
- Capitaliser les recettes validées.

### Limites

- Ce n’est pas un agent autonome.
- Il n’édite rien.

### Outils et accès

- Dossier canonique `.agents/skills/proparse-research/`.
- Checkout RSSW read-only via `$RSSW_REPO`.

### Informations reçues et produites

- Reçoit tâche et chemins.
- Produit rapport compact et recettes validées après review humaine.

### Contenu initial proposé de `SKILL.md`

```md
---
name: proparse-research
description: >
  Research Riverside Software Proparse before implementing any OpenEdge ABL
  parsing, PSI, completion, highlighting, inspection, keyword, token, AST,
  grammar or syntax-related behavior. Use this before writing code whenever
  ABL language knowledge may already exist in RSSW.
---

# Proparse research workflow

RSSW Proparse is the source of truth for OpenEdge ABL language knowledge.

## Inputs

- Plugin repository: writable for the implementer, read-only during research
- RSSW repository: read-only, available at `$RSSW_REPO`
- Task description
- Optional existing plugin files

## Rules

1. Do not edit files.
2. Do not propose an implementation before inspecting RSSW.
3. Do not create manual ABL keyword lists.
4. Do not duplicate grammar knowledge.
5. Do not introduce regex-based parsing unless explicitly approved.
6. Prefer existing RSSW APIs and usage patterns.
7. Search consumer modules as well as the Proparse module.

## Search order

1. Search existing plugin code.
2. Search `$RSSW_REPO/proparse`.
3. Search RSSW consumer modules for real usage examples.
4. Inspect tests.
5. Record exact files, classes and methods.

## Required output

Produce a compact Markdown report:

- task
- searches performed
- relevant RSSW files
- relevant plugin files
- existing API or tree data to reuse
- usage examples found
- uncertainties
- minimal recommendation
- whether a small helper is justified
```

### Interactions

- Appelé par researcher ou planner pour les tâches ABL.
- Enrichit progressivement `references/recipes.md` seulement après validation.

## 4.5 Sous-agent optionnel `proparse-researcher`

### Nom et rôle

`proparse-researcher` — worker read-only spécialisé, à introduire seulement après deux ou trois recherches réelles si un explorer générique ne suffit pas.

### Responsabilités

- Charger le skill `proparse-research`.
- Explorer plugin, RSSW/Proparse, consommateurs et tests.
- Renvoyer une synthèse compacte.

### Limites

- Aucun edit, patch, commit ou push.
- Pas de refactor large.

### Outils et accès

- Lecture plugin ;
- lecture RSSW ;
- recherche et historique read-only.

### Prompt système proposé

```text
You are a read-only RSSW Proparse researcher.

Always load and follow the proparse-research skill.

You may:
- search files
- read files
- inspect git history when useful
- run read-only indexing commands

You may not:
- edit files
- create patches
- commit
- push
- propose broad refactors

Return only the compact research report required by the skill.
```

### Interactions

- Répond au researcher principal ou directement au planner.
- Ne transmet que `research.md`, pas l’historique complet de ses recherches.

## 4.6 Planner

### Nom et rôle

`implementation-planner` — produit un plan minimal, précis et vérifiable.

### Responsabilités

- Décomposer en phases.
- Identifier fichiers à éditer et tests.
- Déclarer hors périmètre, incertitudes et checks.
- Respecter le red/green sur bugs.

### Limites

- Lecture seule.
- Aucun edit ni patch.
- Doit revenir à la recherche si l’information manque.

### Outils et accès

- Lecture des artefacts et du dépôt.

### Informations reçues et produites

- Reçoit `AGENTS.md`, `task.md`, `research.md`, guides.
- Produit `plan.md`.

### Prompt système proposé

```text
You are a read-only implementation planner.

Use the approved task and research artifacts as the source of truth. Produce a
minimal, phased implementation plan aligned with existing codebase patterns.
For each phase, name the files to change, the intended behavior, the tests to
add or update, and the exact automated and manual verification steps.

For bug fixes, prefer red/green sequencing: introduce a regression test, verify
that it fails before the fix, apply the minimal fix, then verify that all tests
pass. Explicitly list out-of-scope work. Do not edit files. Do not hide
uncertainties. If the research is insufficient or reality is ambiguous, stop
and request another research pass or human input.
```

### Interactions

- Reçoit `research.md`.
- Produit le contrat lu par implementer.

## 4.7 Implementer

### Nom et rôle

`phase-implementer` — applique un plan approuvé dans un workspace jetable.

### Responsabilités

- Éditer strictement les fichiers nécessaires.
- Implémenter une phase à la fois.
- Exécuter checks rapides.
- Mettre à jour `progress.md`.
- S’arrêter si le plan devient invalide.

### Limites

- Pas de GitHub write.
- Pas de push.
- Pas de merge.
- Pas de nouvelle dépendance sans validation.
- Pas de modification de chemins protégés.
- Pas de contournement des tests.

### Outils et accès

- Workspace plugin read-write ;
- RSSW read-only ;
- Git local ;
- commandes autorisées ;
- clé LLM protégée selon mécanisme à décider.

### Informations reçues et produites

- Reçoit artefacts compacts et fichiers utiles.
- Produit modifications, `progress.md`, `patch.diff`, résultats.

### Prompt système proposé

```text
You are a phase-by-phase implementation agent working in a disposable
workspace.

Follow the approved plan exactly. Implement only the current phase. Keep the
diff minimal and reuse existing patterns. Do not add dependencies, modify
protected paths, weaken tests, push commits, create pull requests or communicate
with GitHub. For bug fixes, verify the regression test fails before applying the
fix whenever the plan requires it.

Run only the allowed verification commands. At the end of the phase, update
progress.md with completed work, changed files, commands run, results,
discoveries, rejected approaches and remaining work. If the repository differs
from the approved plan or a risky change becomes necessary, stop and return a
blocked status instead of improvising.
```

### Interactions

- Consomme le plan.
- Donne patch au validator.

## 4.8 Reviewer LLM consultatif

### Nom et rôle

`patch-reviewer` — critique indépendante read-only.

### Responsabilités

- Vérifier conformité au plan.
- Chercher duplication, régression, manque de tests, hallucination API, dérive de scope.

### Limites

- N’édite rien.
- Ne valide jamais seul la fusion.

### Prompt système proposé

```text
You are an independent read-only reviewer of an agent-generated patch.

Compare the approved task, research, plan, verification report and diff. Look
for scope drift, duplicated logic, weakened tests, missing regression coverage,
unsafe IntelliJ API usage, unsupported assumptions, protected-path changes and
unnecessary abstractions. Report findings with severity and precise locations.
Do not edit files. An empty finding list must be justified briefly.
```

## 4.9 Validator déterministe

### Nom et rôle

`patch-validator` — applique les politiques et quality gates.

### Responsabilités

- Refuser chemins interdits, diff trop grand, binaire, symlink, secret, affaiblissement de tests.
- Lancer Gradle et outils de sécurité.

### Limites

- Aucun jugement métier sophistiqué.

### Outils

- Bash/Python, Git, Gradle, Gitleaks optionnel.

### Prompt système proposé

Aucun.

## 4.10 Publisher déterministe

### Nom et rôle

`draft-pr-publisher` — crée branche et draft PR après validation.

### Responsabilités

- Appliquer patch proprement.
- Pousser branche.
- Créer PR brouillon.
- Ajouter rapport et labels.

### Limites

- Ne merge jamais.
- Ne modifie pas le patch.

### Outils

- Git, `gh`, `GITHUB_TOKEN` minimal.

### Prompt système proposé

Aucun.

## 4.11 Human owner

### Nom et rôle

Propriétaire humain du projet.

### Responsabilités

- Approuver issue/spec.
- Relire recherche et plan aux gates prévues.
- Valider chemins sensibles.
- Review PR et merge manuel.
- Capitaliser recettes validées.

### Limites

- Éviter de relire uniquement des milliers de lignes finales sans intervenir en amont.

---

# 5. Architecture technique

## 5.1 Composants et technologies envisagés

### Confirmé ou fortement recommandé

- GitHub Issues comme file d’attente initiale.
- GitHub Actions comme exécuteur CI et, progressivement, orchestrateur distant.
- Scripts Bash ou Python pour la couche déterministe.
- Gradle pour build et tests Kotlin IntelliJ.
- `ktlint`, `detekt`, `verifyPlugin`, `quality-gate`, `CODEOWNERS`, branch protection existants.
- `AGENTS.md` court.
- `.agents/skills/` pour skills portables.
- `.agent/` distinct pour scripts, policies, prompts et adaptateurs d’orchestration.
- Worktree ou clone jetable pour implémentation.
- Artefacts Markdown compacts.
- Patch Git comme frontière entre exécution non privilégiée et publication privilégiée.

### Adaptateurs à expérimenter

- Codex CLI ;
- OpenCode ;
- Aider ;
- Claude Code ;
- mini-swe-agent en option.

### À ajouter progressivement

- Gitleaks ;
- Renovate ;
- build cache Gradle ;
- éventuellement Qodana, Semgrep, Trivy, couverture, duplication et PIT.

## 5.2 Flux de données

```text
GitHub issue + approval label
  → prepare-task.sh
  → task.md + metadata.json
  → researcher adapter (read-only)
  → research.md
  → human gate if required
  → planner adapter (read-only)
  → plan.md
  → human gate if required
  → implementer adapter in disposable workspace
  → progress.md + patch.diff + partial verification
  → deterministic validator on clean checkout
  → verification.md
  → optional read-only reviewer
  → review.md
  → deterministic publisher with scoped GitHub write token
  → draft PR
  → existing quality-gate + human review
  → manual merge
```

## 5.3 Orchestration

### Contrat portable des adaptateurs

Chaque adaptateur doit accepter :

```text
- stage: research | plan | implement | review
- workspace: path
- task_file: path
- input_artifacts: paths
- output_directory: path
- timeout
- max_turns
- max_cost
```

Chaque adaptateur doit produire :

```text
- result.json
- summary.md
- research.md       # research
- plan.md           # plan
- progress.md       # implement
- verification.md   # implement/validator
- review.md         # review
- patch.diff        # implement uniquement
```

### Configuration centrale proposée

```yaml
version: 1

project:
  type: intellij-plugin-kotlin

default_adapter: codex

stages:
  research:
    mode: read_only
    max_turns: 8
    timeout_minutes: 12
    max_cost_eur: 0.10
    human_review:
      low: false
      medium: true
      high: true

  plan:
    mode: read_only
    max_turns: 6
    timeout_minutes: 10
    max_cost_eur: 0.10
    human_review:
      low: false
      medium: true
      high: true

  implement:
    mode: workspace_write
    max_turns: 16
    timeout_minutes: 30
    max_cost_eur: 0.40
    human_review_after_phase:
      low: false
      medium: false
      high: true

checks:
  fast: .agent/checks/fast.sh
  full: .agent/checks/full.sh
  diff_policy: .agent/checks/diff-policy.sh
  tests_policy: .agent/checks/tests-policy.sh
  secret_scan: .agent/checks/secret-scan.sh

security:
  github_write_access_in_agent: false
  network_default: deny
  allow_binary_files: false
  allow_symlinks: false
  allow_submodules: false

publication:
  draft_pr_only: true
  auto_merge: false
```

`default_adapter: codex` est proposé pour le premier scaffold destiné à Codex, mais doit rester modifiable. Un autre choix raisonnable pour les essais autonomes est OpenCode. Ce choix n’est pas définitivement arrêté.

## 5.4 Gestion du contexte et de la mémoire

### Principe

Le second document joint défend une méthode appelée **frequent intentional compaction** : organiser tout le workflow autour de la gestion du contexte, idéalement en gardant une utilisation modérée et en redémarrant avec un contexte propre. Les grands consommateurs de contexte sont les recherches de fichiers, lectures, logs de build, sorties d’outils, erreurs et tentatives successives.

### Architecture en niveaux

```text
Tier 1 : AGENTS.md
  Règles courtes toujours chargées.

Tier 2 : docs/agent-guides/*.md et skills
  Chargés à la demande.

Tier 3 : task.md, research.md, plan.md, progress.md, verification.md
  Artefacts spécifiques à l’issue.

Logs bruts
  Conservés temporairement comme artefacts, jamais réinjectés intégralement.
```

### Règle de compaction

Créer une session propre :

- après recherche ;
- après planification ;
- après chaque phase importante ;
- après une sortie de build volumineuse ;
- après une tentative échouée ;
- après modification humaine du plan.

## 5.5 Permissions et sécurité

### Tableau des permissions

| Composant | Plugin | RSSW | GitHub lecture | GitHub écriture | Secrets publication | Clé LLM |
|---|---:|---:|---:|---:|---:|---:|
| Normalizer | Lecture | Non | Oui | Limité si label update | Non | Non |
| Researcher | Lecture | Lecture | Non nécessaire | Non | Non | Selon agent |
| Planner | Lecture | Lecture | Non | Non | Non | Selon agent |
| Implementer | Lecture/écriture workspace | Lecture | Non | Non | Non | Selon agent |
| Validator | Lecture/écriture checkout propre | Non | Non | Non | Non | Non |
| Publisher | Lecture/écriture checkout propre | Non | Oui | Oui minimal | Non | Non |
| Human owner | Selon besoin | Selon besoin | Oui | Oui | Selon besoin | Selon usage |

### Politique de chemins proposée

`.agent/policies/protected-paths.yaml` :

```yaml
version: 1

deny_autonomous_write:
  - ".github/**"
  - ".agent/**"
  - "gradle/**"
  - "gradlew"
  - "gradlew.bat"
  - "build.gradle"
  - "build.gradle.kts"
  - "settings.gradle"
  - "settings.gradle.kts"
  - "gradle.properties"

require_explicit_human_approval:
  - "src/main/resources/META-INF/plugin.xml"
  - "**/*.xml"
  - "**/resources/**"
  - "**/*Thread*.kt"
  - "**/*Coroutine*.kt"

limits:
  max_changed_files: 12
  max_added_lines: 500
  max_deleted_lines: 300
  allow_binary_files: false
  allow_symlinks: false
  allow_submodules: false
```

Les patterns threading sont des heuristiques, pas une couverture exhaustive. Le classifier doit aussi examiner le contenu du diff.

### Politique de tests proposée

Refuser automatiquement au minimum l’ajout ou l’usage de contournements suspects :

```text
@Disabled
@Ignore
suppression massive d’assertions
TODO utilisé pour contourner un test
exclusion de répertoires de tests
modification CI destinée à éviter un check
```

## 5.6 GitHub Actions : séparation des privilèges

### Workflow 1 — construction du patch sans privilège

Squelette à adapter et à épingler avec de vrais SHA complets :

```yaml
name: Agent Build

on:
  workflow_dispatch:
    inputs:
      issue_number:
        description: Issue number
        required: true
        type: string
      adapter:
        description: Agent adapter
        required: true
        default: codex
        type: choice
        options:
          - codex
          - opencode
          - claude-code
          - aider

permissions:
  contents: read
  issues: read

concurrency:
  group: agent-build-${{ inputs.issue_number }}
  cancel-in-progress: false

jobs:
  prepare:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@<PINNED_FULL_SHA>
        with:
          persist-credentials: false

      - name: Prepare normalized task
        run: .agent/scripts/prepare-task.sh "${{ inputs.issue_number }}"

      - name: Upload source bundle
        uses: actions/upload-artifact@<PINNED_FULL_SHA>
        with:
          name: agent-input
          path: |
            source.tar.gz
            run/task.md
            run/metadata.json

  run-agent:
    needs: prepare
    runs-on: ubuntu-latest
    permissions: {}
    steps:
      - name: Download source bundle
        uses: actions/download-artifact@<PINNED_FULL_SHA>
        with:
          name: agent-input

      - name: Run isolated agent
        env:
          LLM_API_KEY: ${{ secrets.LLM_API_KEY }}
        run: |
          .agent/scripts/run-stage.sh implement \
            --adapter "${{ inputs.adapter }}" \
            --task run/task.md

      - name: Upload patch
        uses: actions/upload-artifact@<PINNED_FULL_SHA>
        with:
          name: agent-output
          retention-days: 14
          path: run/output/
```

**Attention :** ce squelette ne résout pas encore la protection de `LLM_API_KEY` face à un agent compromis. Ne pas activer tel quel en autonomie sur du contenu externe. Résoudre d’abord le modèle de credential LLM.

### Workflow 2 — publication contrôlée

```yaml
name: Publish Agent PR

on:
  workflow_dispatch:
    inputs:
      source_run_id:
        description: Agent Build run ID
        required: true
        type: string
      issue_number:
        description: Issue number
        required: true
        type: string

permissions:
  contents: write
  pull-requests: write
  issues: write
  actions: read

jobs:
  publish:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout clean repository
        uses: actions/checkout@<PINNED_FULL_SHA>
        with:
          persist-credentials: true

      - name: Download untrusted patch artifact
        uses: actions/download-artifact@<PINNED_FULL_SHA>
        with:
          run-id: ${{ inputs.source_run_id }}
          name: agent-output
          github-token: ${{ secrets.GITHUB_TOKEN }}

      - name: Validate before applying
        run: |
          git apply --check run/output/patch.diff
          .agent/scripts/validate-patch.sh run/output/patch.diff

      - name: Publish deterministic draft PR
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          .agent/scripts/publish-draft-pr.sh \
            "${{ inputs.issue_number }}" \
            run/output/patch.diff
```

Pendant la phase pilote, garder `workflow_dispatch` manuel pour les deux workflows.

## 5.7 Structure de fichiers recommandée

```text
.agent/
├── config.yaml
├── adapters/
│   ├── codex.sh
│   ├── opencode.sh
│   ├── claude-code.sh
│   ├── aider.sh
│   └── mini-swe-agent.sh
├── scripts/
│   ├── prepare-task.sh
│   ├── classify-task.sh
│   ├── run-stage.sh
│   ├── validate-patch.sh
│   ├── publish-draft-pr.sh
│   ├── update-issue-state.sh
│   └── collect-metrics.sh
├── checks/
│   ├── fast.sh
│   ├── full.sh
│   ├── diff-policy.sh
│   ├── tests-policy.sh
│   └── secret-scan.sh
├── prompts/
│   ├── research.md
│   ├── plan.md
│   ├── implement.md
│   ├── compact-progress.md
│   └── review.md
├── policies/
│   ├── protected-paths.yaml
│   ├── commands.yaml
│   └── risk-rules.yaml
└── schemas/
    ├── result.schema.json
    ├── research.schema.json
    └── plan.schema.json

.agents/
└── skills/
    └── proparse-research/
        ├── SKILL.md
        ├── references/
        │   ├── recipes.md
        │   └── known-entry-points.md
        └── scripts/
            └── search-proparse.sh

docs/
├── agent-guides/
│   ├── architecture.md
│   ├── intellij-threading.md
│   ├── psi-and-parsing.md
│   ├── testing.md
│   └── plugin-xml.md
└── agent-work/
    └── ISSUE-123/
        ├── task.md
        ├── research.md
        ├── plan.md
        └── verification.md

AGENTS.md
```

Distinction importante :

- `.agent/` contient l’orchestration du projet ;
- `.agents/skills/` contient les skills portables suivant le standard Agent Skills.

Pour Claude Code, ajouter si nécessaire une redirection ou synchronisation légère depuis `.claude/skills/` vers la source canonique `.agents/skills/`. Éviter deux copies divergentes.

## 5.8 `AGENTS.md` initial proposé

```md
# Project overview

IntelliJ Platform plugin for OpenEdge ABL, written in Kotlin.

# Commands

## Fast verification
./gradlew ktlintCheck detekt test

## Full verification
./gradlew ktlintCheck detekt test build verifyPlugin

# Architecture map

Fill this section after inspecting the repository. Do not invent paths.

# Mandatory rules

- Never modify `.github/`, `.agent/`, Gradle wrapper files or build scripts unless
  the task is explicitly approved for manual high-risk work.
- Never add a dependency without explicit human approval.
- Never weaken, disable or bypass an existing test.
- Every bug fix must include a meaningful regression test whenever feasible.
- Keep diffs minimal and reuse existing patterns.
- If repository reality diverges from the approved plan, stop and report a
  blocked status instead of improvising.

## Mandatory Proparse research

Before editing code related to ABL grammar, parsing, tokens, keywords, syntax
highlighting, PSI, completion or inspections:

1. Use the `proparse-research` skill.
2. Inspect the read-only RSSW checkout at `$RSSW_REPO`.
3. Reuse RSSW data and APIs whenever possible.
4. Do not hardcode ABL keyword lists or duplicate grammar knowledge.
5. Attach the resulting `research.md` to the implementation plan.

# Guides loaded on demand

- `docs/agent-guides/intellij-threading.md`
- `docs/agent-guides/testing.md`
- `docs/agent-guides/psi-and-parsing.md`
- `docs/agent-guides/plugin-xml.md`
```

Codex doit remplacer la section `Architecture map` par des chemins vérifiés après inspection du dépôt.

## 5.9 Observabilité minimale

Commencer par un fichier JSONL ou un artefact par run :

```json
{
  "issue": 123,
  "adapter": "codex",
  "model": "provider/model",
  "risk": "medium",
  "research_reviewed": true,
  "plan_reviewed": true,
  "implementation_status": "patch-ready",
  "human_edits_after_agent": 2,
  "changed_files": 5,
  "added_lines": 143,
  "deleted_lines": 28,
  "cost_eur": 0.18,
  "duration_seconds": 624,
  "merged": true,
  "regression_detected_after_merge": false
}
```

Métriques hebdomadaires :

| Mesure | Objectif initial |
|---|---:|
| Coût moyen par PR mergée | `< 0,50 €` à mesurer et ajuster |
| Régressions post-merge | `0` |
| Modifications hors périmètre | `0` |
| Fichiers protégés modifiés sans accord | `0` |
| PR rejetées | `< 30 %` après pilote, à confirmer empiriquement |
| Temps de review humaine | à réduire progressivement |
| Issues bloquées proprement | à mesurer ; préférable à l’improvisation |

---

# 6. Décisions prises

| Décision | Statut | Justification | Alternatives étudiées | Raisons du rejet ou du report | Niveau de certitude |
|---|---|---|---|---|---|
| Viser une autonomie supervisée, pas une autonomie totale immédiate | Confirmée | Risques qualité et sécurité sur base Kotlin IntelliJ existante | Agent autonome avec auto-merge | Trop risqué ; review humaine indispensable | Élevé |
| Automatiser déterministement tout ce qui peut l’être | Confirmée | Plus fiable, plus rapide, moins coûteux qu’un LLM | Laisser l’agent gérer lint, PR, labels, branche | Inutile et dangereux | Élevé |
| Ne jamais donner de GitHub write token au LLM | Confirmée | Réduit fortement impact d’une prompt injection | Autoriser `gh pr create --draft` à l’agent | Rejeté après analyse sécurité | Élevé |
| Créer branche et draft PR dans un publisher déterministe séparé | Confirmée | Séparation des privilèges | Laisser l’agent pousser | Surface d’attaque trop grande | Élevé |
| Conserver merge manuel et protection `main` | Confirmée | HITL final obligatoire | Auto-merge petites PR | Différé jusqu’à preuve de fiabilité ; probablement non nécessaire au début | Élevé |
| Utiliser `AGENTS.md` court et guides chargés à la demande | Confirmée | Réduit bruit de contexte | Document monolithique | Risque de saturation | Élevé |
| Organiser le workflow en recherche → plan → implémentation | Confirmée | Compaction intentionnelle fréquente ; améliore brownfield et alignment | Session unique de vibe coding | Contexte pollué et trajectoires erronées | Élevé |
| Relire prioritairement recherche et plan | Confirmée | Une erreur amont amplifie les erreurs aval | Review uniquement du code final | Trop tardive et coûteuse | Élevé |
| Utiliser un worktree ou workspace jetable pour implémentation | Confirmée | Isolation et reproductibilité | Travailler directement sur branche locale permanente | Risque de pollution | Élevé |
| Utiliser `.agent/` pour orchestration et `.agents/skills/` pour skills portables | Confirmée comme convention proposée | Évite confusion et favorise portabilité | Un seul dossier ; copies divergentes | Moins clair ; copies difficiles à maintenir | Moyen à élevé |
| Introduire le skill `proparse-research` avant un sous-agent spécialisé | Confirmée | Procédure portable et mémoire progressive avant sophistication | Créer immédiatement `proparse-researcher` complexe | Risque de sur-ingénierie prématurée | Élevé |
| Traiter RSSW/Proparse comme source de vérité ABL | Confirmée | Éviter listes codées en dur et duplication de grammaire | Coder mots-clés et règles dans plugin | Erreur déjà observée avec anciens agents | Élevé |
| Commencer par `workflow_dispatch` manuel | Confirmée pour phase pilote | Contrôle simple et sûr | Trigger automatique sur label dès le début | Trop tôt avant stabilisation | Élevé |
| Utiliser GitHub Issues comme état initial | Confirmée | Suffisant pour solo dev | SQLite, Beads, base externe | Complexité inutile au début | Élevé |
| Tester plusieurs adaptateurs derrière un contrat commun | Confirmée | Évite verrouillage | Choisir immédiatement un seul agent | Contredit l’objectif utilisateur | Élevé |
| OpenCode comme premier adaptateur autonome potentiel | Suggestion | Multi-provider, skills et permissions | Codex CLI, Aider | Le choix final dépend des tests | Moyen |
| Codex comme premier adaptateur à scaffolder dans ce transfert | Suggestion pratique | Le destinataire est Codex ; utile immédiatement | OpenCode d’abord | Ne doit pas devenir un verrouillage | Moyen |
| Ajouter `verifyPluginStructure` et `verifyPluginProjectConfiguration` si disponibles | Suggestion à vérifier | Renforcer validation plugin IntelliJ | Garder uniquement `verifyPlugin` | Disponibilité selon configuration/version à vérifier | Moyen |
| Ajouter Gitleaks rapidement | Suggestion forte | Détection de secrets | Semgrep/Trivy seulement | Gitleaks cible directement les secrets et reste simple | Élevé |
| Utiliser OIDC pour remplacer tout token GitHub | Rejeté / corrigé | OIDC sert surtout à obtenir des tokens temporaires auprès de services externes | PAT longue durée | Pour GitHub, utiliser `GITHUB_TOKEN` scoped ou GitHub App dans publisher | Élevé |
| Sanitizer de prompt comme défense principale | Rejeté / corrigé | Les injections ne sont pas résolues par filtrage lexical | Défense par moindre privilège et isolation | Le filtre reste complémentaire seulement | Élevé |
| Dépendre de free tiers précis | Rejeté | Volatilité prix, limites et disponibilité | Architecture couplée à OpenRouter/Gemini gratuits | Fragile | Élevé |
| Installer Langfuse, n8n, RAG et multi-agent complexe dès le début | Rejeté pour V1 | Ajouterait complexité sans mesurer le besoin | Instrumentation légère JSONL | Différé | Élevé |

---

# 7. Questions ouvertes

## 7.1 Questions non résolues nécessitant inspection technique

1. Quel est le chemin exact du dépôt du plugin ?
2. Quelle est sa structure réelle (`src/main`, tests, package names, workflows GitHub, build scripts) ?
3. Quelles tâches Gradle existent réellement ? Vérifier notamment :
   - `ktlintCheck` ;
   - `detekt` ;
   - `test` ;
   - `build` ;
   - `verifyPlugin` ;
   - disponibilité éventuelle de `verifyPluginStructure` ;
   - disponibilité éventuelle de `verifyPluginProjectConfiguration`.
4. Où se trouve le checkout RSSW réel ? Quel est son URL ou chemin local ?
5. Les modules mentionnés `proparse/`, `openedge-checks/`, `openedge-plugin/` existent-ils exactement sous ces noms ?
6. Le dépôt du plugin est-il public ou privé ?
7. Quelles minutes GitHub Actions et contraintes de secret s’appliquent au compte réel ?
8. Quels tests existent déjà pour parser, PSI, autocomplétion et inspections ?
9. Quelle CI GitHub existe déjà et quels checks sont obligatoires dans la branch protection ?
10. Des dépendances RSSW sont-elles déjà intégrées au plugin, sous quelle forme et quelle version ?

## 7.2 Questions nécessitant décision du propriétaire

1. Quel adaptateur utiliser pour le premier test local : Codex, OpenCode ou les deux ?
2. Souhaite-t-on écrire les scripts d’orchestration en Bash ou en Python ?
   - Bash : simple pour V1 GitHub Actions.
   - Python : meilleure portabilité et tests unitaires à moyen terme.
3. Quel mécanisme protégera la clé LLM dans un runner autonome ?
4. Le repo est-il autorisé à transmettre son code à des modèles ou free tiers utilisant les inputs pour entraînement ?
5. Quel budget réel mensuel maximal accepter ?
6. Quel golden set initial de cinq à vingt issues historiques utiliser ?
7. Quels chemins métier doivent être ajoutés à `protected-paths.yaml` ?
8. Quels changements doivent toujours rester `risk:high` dans le contexte du plugin ?
9. Faut-il versionner `research.md` et `plan.md` pour toutes les issues standard ou uniquement les features complexes ?
10. Faut-il installer Renovate dès le premier sprint ou après le scaffold agentique ?

## 7.3 Risques à surveiller

- Prompt injection depuis issues, commentaires, fichiers, logs et dépendances.
- Exfiltration de la clé LLM si l’agent peut inspecter l’environnement et accéder au réseau.
- Hallucination d’API IntelliJ Platform.
- Duplication de grammaire ou mots-clés ABL au lieu de Proparse.
- Tests générés validant le bug au lieu de le révéler.
- Régression silencieuse non couverte.
- Diff trop large et review humaine coûteuse.
- Sur-ingénierie de l’orchestrateur avant mesure réelle.
- Free tiers indisponibles ou instables.
- Mauvaise compaction perdant une hypothèse critique.
- Mauvaise recherche RSSW conduisant à un plan erroné.
- Injection par artifact lors du passage entre job non privilégié et publisher privilégié.

## 7.4 Contradictions et corrections apparues dans la conversation

1. **Création de PR par l’agent.** Le document initial envisageait une allowlist contenant `gh pr create --draft`. L’analyse ultérieure conclut que la PR doit être créée exclusivement par un publisher déterministe séparé. Retenir la seconde position.
2. **OIDC.** Le document initial suggérait des jetons OIDC courts au lieu de PAT. Correction : OIDC ne remplace pas directement les permissions GitHub nécessaires à la création d’une PR. Utiliser un `GITHUB_TOKEN` scoped dans le publisher ou une GitHub App plus tard.
3. **Sanitization.** Le document initial proposait de filtrer les instructions suspectes dans le corps d’issue. Correction : utile comme signal complémentaire, insuffisant comme frontière de sécurité.
4. **OpenCode et `AGENTS.md`.** Une comparaison initiale indiquait que OpenCode n’avait pas d’équivalent persistant. Correction ultérieure : OpenCode prend en charge `AGENTS.md`. Vérifier la version lors de l’installation.
5. **Agent de départ.** La première recherche recommandait Aider + mini-swe-agent pour le budget ; l’analyse suivante proposait OpenCode comme premier adaptateur autonome ; ce transfert propose de scaffolder Codex en premier parce que Codex reçoit le document. Ce n’est pas une décision définitive : le contrat doit rester neutre et les agents doivent être comparés sur le golden set.
6. **Sous-agent Proparse.** Un sous-agent spécialisé a été envisagé. Décision affinée : commencer par le skill et un explorer read-only générique ; créer un sous-agent dédié seulement après quelques recherches réelles.

---

# 8. Plan d’implémentation

## 8.1 Phase 0 — audit du dépôt réel

### Priorité

Immédiate.

### Objectif

Ne rien inventer avant de connaître le projet.

### Actions

- Inspecter arbre du dépôt.
- Lire `README`, `build.gradle*`, `settings.gradle*`, `gradle.properties` sans exposer secrets.
- Lire `.github/workflows/**`, `CODEOWNERS` et docs existantes.
- Exécuter ou lister les tâches Gradle.
- Identifier packages parser, PSI, completion, highlighting, inspections et tests.
- Identifier intégration RSSW existante.
- Vérifier présence éventuelle de `AGENTS.md`, `.agent/`, `.agents/`, `.claude/` ou autre config d’agent.
- Produire `docs/agent-guides/repository-audit.md` ou rapport séparé avant modifications importantes.

### Livrables

- Rapport d’audit.
- Liste des commandes réellement fonctionnelles.
- Liste des chemins sensibles réels.
- Questions restantes.

### Critères d’acceptation

- Aucun chemin inventé dans les fichiers finaux.
- Commandes Gradle vérifiées.
- Structure RSSW clarifiée ou marquée bloquante.

## 8.2 Phase 1 — fondation contextuelle portable

### Priorité

Très haute.

### Dépendances

- Audit initial.

### Actions

Créer :

```text
AGENTS.md
.agents/skills/proparse-research/SKILL.md
.agents/skills/proparse-research/references/recipes.md
.agents/skills/proparse-research/references/known-entry-points.md
docs/agent-guides/intellij-threading.md
docs/agent-guides/psi-and-parsing.md
docs/agent-guides/testing.md
docs/agent-guides/plugin-xml.md
```

Remplir seulement les informations vérifiées. Les guides peuvent commencer avec des placeholders explicites `TODO: document after repository audit`, mais ne doivent pas inventer des règles propres au projet.

### Livrables

- PR ou commit de scaffold documentaire.

### Critères d’acceptation

- `AGENTS.md` reste court.
- La règle mandatory Proparse research est présente.
- Le skill décrit clairement procédure et sorties.
- Aucun changement fonctionnel.

## 8.3 Phase 2 — scripts déterministes locaux

### Priorité

Très haute.

### Dépendances

- Commandes vérifiées pendant audit.

### Actions

Créer :

```text
.agent/config.yaml
.agent/checks/fast.sh
.agent/checks/full.sh
.agent/checks/diff-policy.sh
.agent/checks/tests-policy.sh
.agent/checks/secret-scan.sh
.agent/policies/protected-paths.yaml
.agent/policies/risk-rules.yaml
.agent/scripts/validate-patch.sh
.agent/scripts/collect-metrics.sh
```

Ajouter des tests unitaires pour scripts si Python est choisi ou des fixtures shell minimales si Bash.

### Livrables

- Scripts exécutables localement.
- Documentation d’usage.

### Critères d’acceptation

- Les checks existants passent sur le dépôt propre.
- Un patch modifiant `.github/**` est refusé.
- Un patch trop grand est refusé.
- Un patch contenant binaire ou symlink est refusé.
- Un patch désactivant un test est refusé.
- Gitleaks ou stub documenté selon décision.

## 8.4 Phase 3 — templates et prompts portables

### Priorité

Haute.

### Actions

Créer :

```text
.agent/prompts/research.md
.agent/prompts/plan.md
.agent/prompts/implement.md
.agent/prompts/compact-progress.md
.agent/prompts/review.md
.agent/templates/task.md
.agent/templates/research.md
.agent/templates/plan.md
.agent/templates/progress.md
.agent/templates/verification.md
.agent/schemas/result.schema.json
```

### Livrables

- Artefacts standardisés.

### Critères d’acceptation

- Chaque phase peut être comprise sans transcript complet.
- Le planner exige hors périmètre et vérifications.
- L’implementer exige stop en cas de divergence.

## 8.5 Phase 4 — premier adaptateur Codex local

### Priorité

Haute.

### Dépendances

- Prompts et config.

### Actions

Créer :

```text
.agent/adapters/codex.sh
.agent/scripts/run-stage.sh
```

Le script doit :

- accepter le contrat portable ;
- appeler Codex dans le mode approprié ;
- limiter sandbox, durée et sorties ;
- produire `result.json` ;
- ne jamais pousser ;
- ne jamais recevoir de GitHub token en écriture.

Vérifier la syntaxe exacte de la version de Codex CLI installée avant de figer le script. Ne pas supposer que les flags restent inchangés.

### Livrables

- Exécution locale `research` sur une tâche exemple.
- Exécution locale `plan` à partir de la recherche.
- Exécution `implement` sur une petite issue historique.

### Critères d’acceptation

- Les sorties suivent les templates.
- Le patch est local uniquement.
- L’adaptateur ne contient pas de logique spécifique impossible à répliquer pour OpenCode.

## 8.6 Phase 5 — golden set

### Priorité

Haute.

### Actions

Sélectionner cinq à vingt issues historiques déjà résolues, avec correction de référence. Inclure :

- typo ou docs ;
- bug simple ;
- test manquant ;
- feature locale ;
- tâche ABL nécessitant recherche RSSW ;
- au moins une tâche à refuser ou escalader.

### Livrables

- `evals/golden-set.yaml` ou format similaire.
- métriques comparatives initiales.

### Critères d’acceptation

- Chaque cas a critères de succès et patch de référence ou vérification déterministe.

## 8.7 Phase 6 — adaptateur OpenCode et baseline Aider

### Priorité

Moyenne à haute.

### Actions

Créer :

```text
.agent/adapters/opencode.sh
.agent/adapters/aider.sh
```

Optionnel : `claude-code.sh`, `mini-swe-agent.sh`.

### Livrables

- Comparaison sur golden set.

### Critères d’acceptation

- Même contrat d’entrées/sorties.
- Mesure coût, durée, qualité, corrections humaines.

## 8.8 Phase 7 — normalisation GitHub et workflow manuel de build

### Priorité

Moyenne.

### Dépendances

- Scripts locaux stables.
- Décision sur credential LLM.

### Actions

Créer :

```text
.agent/scripts/prepare-task.sh
.agent/scripts/classify-task.sh
.github/workflows/agent-build.yml
```

Utiliser uniquement `workflow_dispatch`.

### Livrables

- Run GitHub Actions générant artefacts sans publication.

### Critères d’acceptation

- Aucun GitHub write token dans job agent.
- Artefacts générés.
- Patch validable localement.

## 8.9 Phase 8 — publisher déterministe manuel

### Priorité

Moyenne.

### Actions

Créer :

```text
.agent/scripts/publish-draft-pr.sh
.github/workflows/publish-agent-pr.yml
```

### Livrables

- PR brouillon créée depuis patch validé après lancement manuel.

### Critères d’acceptation

- Publisher ne modifie pas patch.
- PR brouillon seulement.
- Quality gate existant s’exécute comme prévu.
- Merge reste manuel.

## 8.10 Phase 9 — exécution continue prudente

### Priorité

Basse jusqu’à preuve de stabilité.

### Dépendances

- Deux à quatre semaines de métriques satisfaisantes.

### Actions

- Ajouter trigger planifié ou label pour une seule issue `agent:approved`.
- Concurrence à `1`.
- Autoriser publication automatique de brouillon uniquement pour `risk:low` si souhaité.
- Garder merge manuel.

### Critères d’acceptation

- Régressions post-merge : zéro.
- Fichiers protégés modifiés sans accord : zéro.
- Coût et review soutenables.

## 8.11 Première tâche immédiatement réalisable par Codex

### Titre

`chore(agentic): audit repository and add portable context foundation`

### Objectif

Créer la fondation documentaire et le skill Proparse sans modifier le comportement du plugin ni la CI.

### Instructions exactes

1. Inspecter le dépôt actuel et produire un inventaire factuel : structure, commandes Gradle présentes, quality gate, CODEOWNERS, branch protection documentée si visible, zones parser/PSI/completion/tests et intégration RSSW éventuelle.
2. Ne modifier aucun fichier fonctionnel pendant l’audit.
3. Créer ou mettre à jour `AGENTS.md` à partir du template de la section 5.8, en remplaçant la carte d’architecture uniquement par des chemins réellement vérifiés.
4. Créer :

```text
.agents/skills/proparse-research/SKILL.md
.agents/skills/proparse-research/references/recipes.md
.agents/skills/proparse-research/references/known-entry-points.md
docs/agent-guides/repository-audit.md
```

5. Dans `recipes.md`, ne documenter aucune API RSSW non vérifiée. Utiliser des placeholders explicites.
6. Si le checkout RSSW est accessible, effectuer une première recherche read-only et documenter uniquement les entry points vérifiés. Sinon, noter le blocage et demander le chemin `$RSSW_REPO`.
7. Ne pas créer encore de workflow GitHub Actions.
8. Ne pas ajouter de dépendance.
9. Ne pas modifier Gradle.
10. Exécuter uniquement les checks existants dont les commandes ont été vérifiées.
11. Produire un résumé du diff et les questions restantes.

### Critères d’acceptation

- Aucun changement de comportement applicatif.
- Aucun changement `.github/**`.
- Aucun changement Gradle.
- `AGENTS.md` court et exact.
- Skill `proparse-research` présent.
- Audit factuel présent.
- Checks existants passent ou échecs préexistants documentés.

---

# 9. Références et fichiers

## 9.1 Fichiers joints ou générés pendant la conversation

### 1. `compass_artifact_wf-1e0ac698-962f-422f-b8a3-eff1a07a5126_text_markdown.md`

**Rôle :** première recherche approfondie sur un workflow autonome économique pour développeur solo.  
**Contenu pertinent :** état des agents de coding, budget indicatif, couche déterministe, HITL, risques de prompt injection, Kotlin / IntelliJ, architecture hybride GitHub Actions + local, extensibilité multi-projet, comparaison des outils, roadmap et métriques.  
**Modifications envisagées :** aucune ; document de référence historique. Certaines recommandations ont été corrigées dans le présent transfert : création de PR hors agent, nuance OIDC, sanitization non suffisante, OpenCode supporte `AGENTS.md`.  
**À transférer séparément à Codex :** optionnel. Le présent document en synthétise les éléments nécessaires, mais le fichier original peut être utile pour conserver les détails de veille et les sources.

### 2. `ace-fca.md`

**Titre interne :** `Getting AI to Work in Complex Codebases`.  
**Rôle :** article de référence HumanLayer sur le context engineering pour coding agents.  
**Contenu pertinent :** limites du vibe coding, specs comme artefacts sources, recherche/plan/implémentation, compaction intentionnelle fréquente, sous-agents pour isoler la recherche, review humaine à fort levier sur recherche et plan, worktree pour implémentation, exemples BAML et contre-exemple parquet-java.  
**Modifications envisagées :** aucune ; référence méthodologique.  
**À transférer séparément à Codex :** optionnel mais recommandé si Codex doit approfondir la philosophie du workflow.

### 3. `Workflow automatisé développement.txt`

**Rôle :** synthèse produite lors d’un échange antérieur sur la question `skill proparse-research` versus sous-agent `proparse-researcher`.  
**Contenu pertinent :** hiérarchie `AGENTS.md → skill → sous-agent → research.md → agent principal`, structure `.agents/skills/proparse-research/`, contenu initial de `SKILL.md`, règle mandatory Proparse research dans `AGENTS.md`, stratégie multi-repo plugin read-write et RSSW read-only, introduction progressive du sous-agent.  
**Modifications envisagées :** convertir les extraits utiles en fichiers réels dans le dépôt.  
**À transférer séparément à Codex :** non indispensable : son contenu utile est reproduit dans ce transfert.

## 9.2 Fichiers qui devront être transférés séparément à Codex

Les éléments suivants ne sont pas inclus dans ce document et sont nécessaires pour poursuivre concrètement :

1. **Le dépôt complet du plugin IntelliJ OpenEdge ABL** ou un accès Git.
2. **Le checkout RSSW / Proparse** ou son URL exacte, avec chemin prévu dans `$RSSW_REPO`.
3. **Les workflows GitHub actuels** s’ils ne sont pas déjà dans le dépôt.
4. **La configuration de protection de branche** si elle doit être auditée précisément, car elle n’est pas nécessairement versionnée.
5. **La liste des issues historiques** candidates au golden set.
6. **Les secrets ou credentials** ne doivent jamais être transmis dans le document. Fournir séparément seulement le mécanisme d’accès sécurisé décidé.

## 9.3 Liens et ressources mentionnés

### Méthodologie HumanLayer

- Article `Getting AI to Work in Complex Codebases` : contenu joint dans `ace-fca.md`.
- Recherche codebase HumanLayer : `https://github.com/humanlayer/humanlayer/blob/main/.claude/commands/research_codebase.md`
- Création de plan HumanLayer : `https://github.com/humanlayer/humanlayer/blob/main/.claude/commands/create_plan.md`
- Implémentation de plan HumanLayer : `https://github.com/humanlayer/humanlayer/blob/main/.claude/commands/implement_plan.md`
- 12-factor agents : `https://hlyr.dev/12fa`
- Ralph Wiggum loop : `https://ghuntley.com/ralph/`

### Codex

- `AGENTS.md` : `https://developers.openai.com/codex/guides/agents-md`
- Codex CLI : `https://developers.openai.com/codex/cli`
- Codex non-interactive : `https://developers.openai.com/codex/noninteractive`
- Codex skills : `https://developers.openai.com/codex/skills`
- Skills et Agents SDK : `https://developers.openai.com/blog/skills-agents-sdk`

### OpenCode

- Règles / `AGENTS.md` : `https://opencode.ai/docs/rules/`
- CLI : `https://opencode.ai/docs/cli/`
- Modèles : `https://opencode.ai/docs/models/`
- Skills : `https://opencode.ai/docs/skills/`
- Agents : `https://opencode.ai/docs/agents/`

### Claude Code

- Memory : `https://docs.anthropic.com/en/docs/claude-code/memory`
- Common workflows : `https://docs.anthropic.com/en/docs/claude-code/common-workflows`
- Sub-agents : `https://docs.anthropic.com/en/docs/claude-code/sub-agents`
- Skills : `https://docs.anthropic.com/en/docs/claude-code/skills`

### GitHub Actions et sécurité

- Branch protection : `https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/managing-a-branch-protection-rule`
- Sécurisation Actions : `https://docs.github.com/en/actions/reference/security/secure-use`
- Authentification workflow : `https://docs.github.com/actions/reference/authentication-in-a-workflow`
- Événements workflow : `https://docs.github.com/actions/using-workflows/events-that-trigger-workflows`
- Déclenchement manuel : `https://docs.github.com/actions/managing-workflow-runs/manually-running-a-workflow`
- Artefacts : `https://docs.github.com/en/actions/tutorials/store-and-share-data`
- OIDC : `https://docs.github.com/actions/security-for-github-actions/security-hardening-your-deployments/about-security-hardening-with-openid-connect`
- `GITHUB_TOKEN` : `https://docs.github.com/actions/concepts/security/github_token`
- Push protection secrets : `https://docs.github.com/en/code-security/concepts/secret-security/about-push-protection`

### IntelliJ Platform et Kotlin

- Plugin compatibility verification : `https://plugins.jetbrains.com/docs/intellij/verifying-plugin-compatibility.html`
- IntelliJ Platform Plugin Template : à rechercher et vérifier selon version actuelle avant adoption.
- detekt : `https://github.com/detekt/detekt`
- Gradle setup action : `https://github.com/gradle/actions/blob/main/docs/setup-gradle.md`

### Outils complémentaires

- Gitleaks : `https://github.com/gitleaks/gitleaks`
- Renovate : `https://github.com/renovatebot/renovate`
- mini-swe-agent : à rechercher et vérifier selon version actuelle avant intégration.
- Aider : `https://aider.chat/`

## 9.4 Outils mentionnés à ne pas installer aveuglément

Les outils suivants ont été évoqués mais doivent être validés selon besoins mesurés :

- Qodana ;
- Kover / JaCoCo ;
- jscpd ou PMD CPD ;
- Trivy ;
- Semgrep ;
- Dependabot ;
- Snyk ;
- Lefthook ;
- `act` ;
- Langfuse ;
- Helicone ;
- OpenLLMetry ;
- promptfoo ;
- Inspect AI ;
- n8n ;
- Activepieces ;
- PIT mutation testing ;
- intellij-ui-test-robot ;
- Starter framework ;
- Xvfb.

---

# 10. Contexte supplémentaire

## 10.1 Idées abandonnées pouvant redevenir utiles

### Aider architect/editor

Aider peut rester une baseline économique intéressante : un modèle architecte raisonne, un modèle éditeur moins cher applique les changements. À évaluer sur le golden set. Ne pas structurer l’orchestrateur autour de ses flags.

### mini-swe-agent

Harness minimal utile pour mesurer combien de valeur provient du scaffolding. À intégrer plus tard comme adaptateur de benchmark.

### Ralph Wiggum loop

Boucle volontairement simple qui réinjecte prompt et progression dans une session fraîche. Peut servir pour les longues tâches après stabilisation, mais ne doit pas remplacer les gates humaines ni les budgets.

### Memory bank

Un dossier de progression peut devenir utile pour les tâches longues. Dans ce projet, commencer avec `task.md`, `research.md`, `plan.md`, `progress.md` et `verification.md` avant d’ajouter davantage de fichiers.

### Beads ou branche `agent-state`

Une gestion d’état git-backed pourrait devenir utile au-delà de GitHub Issues. Inutile pour la première version solo.

### Langfuse / OpenTelemetry

Pertinent lorsque JSONL ne suffit plus. Ne pas commencer par cela.

### GitHub App dédiée

Peut remplacer le `GITHUB_TOKEN` du publisher lorsque des permissions plus fines ou un comportement avancé deviennent nécessaires.

### RAG IntelliJ

À considérer si les agents hallucinent fréquemment des API malgré les guides et exemples internes. Ne pas lancer un index global avant mesure.

## 10.2 Nuances importantes

- Le document HumanLayer n’affirme pas que la méthode est magique : une recherche peut être fausse et doit être jetée ; certains problèmes restent trop complexes ; un expert du codebase reste nécessaire.
- Les specs et plans améliorent la review, mais ne remplacent pas totalement la lecture du code. Lire attentivement les tests et les fichiers sensibles.
- Les sous-agents ne doivent pas être créés pour simuler une équipe humaine. Leur valeur principale est l’isolation du contexte.
- Le quality gate doit rester déterministe et externe à l’agent.
- Les free tiers ne doivent jamais dicter l’architecture.
- Les liens et capacités outils changent. Vérifier la documentation officielle au moment d’implémenter les adaptateurs.
- Le chemin `$RSSW_REPO` et les API Proparse réelles doivent être inspectés, jamais supposés.
- Le projet IntelliJ ABL est un mauvais terrain pour le vibe coding naïf : API IntelliJ sous-représentées et langage ABL spécialisé. La discipline de recherche est donc prioritaire.

## 10.3 Préférences personnelles influençant le projet

Le propriétaire :

- privilégie les solutions optimisées et compréhensibles ;
- veut éviter la duplication et les régressions ;
- souhaite pouvoir comparer des outils plutôt que s’enfermer dans un écosystème ;
- préfère automatiser les tâches répétables par scripts ;
- accepte un workflow progressif avec review humaine lorsque le risque l’exige ;
- développe actuellement un plugin IntelliJ OpenEdge ABL et souhaite ensuite généraliser à C# et web ;
- utilise déjà Codex dans sa réflexion sur le workflow ;
- souhaite un processus concret et implémentable plutôt qu’une architecture théorique trop lourde.

---

# Instructions de démarrage pour Codex

Lis d’abord intégralement ce document. Ensuite, dans le dépôt réel du plugin, exécute uniquement une phase d’audit read-only : inspecte l’arborescence, les fichiers Gradle, les workflows GitHub existants, `CODEOWNERS`, les tests, les packages liés au parser, au PSI, à l’autocomplétion et aux inspections, ainsi que toute intégration RSSW déjà présente. Vérifie les commandes réellement disponibles, notamment `ktlintCheck`, `detekt`, `test`, `build` et `verifyPlugin`. Ne suppose aucun chemin et ne modifie encore ni Gradle ni `.github/**`.

Après cet audit, réalise la première tâche `chore(agentic): audit repository and add portable context foundation` décrite en section 8.11 : crée un `AGENTS.md` court et factuel, le skill `.agents/skills/proparse-research/SKILL.md`, ses fichiers `references/recipes.md` et `references/known-entry-points.md`, ainsi que `docs/agent-guides/repository-audit.md`. Si le checkout RSSW est disponible, inspecte-le en lecture seule et documente seulement les entry points vérifiés ; sinon, indique clairement que `$RSSW_REPO` manque et demande son chemin. N’ajoute aucune dépendance, ne crée aucun workflow GitHub Actions, ne pousse rien et ne modifie aucun comportement applicatif. Termine par un résumé du diff, les checks exécutés, leurs résultats et les questions bloquantes restantes.
