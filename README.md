# ABL Language Support — Plugin IntelliJ

Plugin IntelliJ IDEA pour **Progress OpenEdge ABL** (Advanced Business Language).

Construit entièrement sur les extension points natifs IntelliJ + la bibliothèque
**proparse** (Riverside Software / RSSW) — pas de LSP server externe.

---

## Fonctionnalités

| Fonctionnalité                  | Description                                               |
|---------------------------------|-----------------------------------------------------------|
| Coloration syntaxique           | Via ABLLexer RSSW (~900 tokens ABL complets)              |
| Folding                         | DO..END, PROCEDURE..END, CLASS..END, /* ... */            |
| Complétion de code              | Mots-clés + symboles du projet + types résolus (sémantique)|
| Diagnostics en temps réel       | Erreurs syntaxiques CABL (squiggles rouges)               |
| Documentation hover             | ~92 fonctions built-in + symboles utilisateur             |
| Go to Declaration               | Ctrl+B sur un symbole ou un `{include.i}`                 |
| Find Usages                     | Alt+F7                                                    |
| Renommage                       | Shift+F6                                                  |
| Structure View                  | Alt+7 — hiérarchie des symboles du fichier                |
| Inspections + Quick Fix         | NO-UNDO manquant, FIND sans lock mode                     |
| Live Templates (snippets)       | Raccourcis de code ABL courants                           |
| Auto-casing des mots-clés       | Mise en majuscules automatique à la frappe                |
| Run Configuration               | Lancer un .p directement via _progres/prowin              |
| openedge-project.json           | Lecture du PROPATH, version OE, connexions DB             |

Extensions supportées : `.p` `.cls` `.i` `.w` `.t`

---

## Architecture

```
src/main/kotlin/com/ablls/plugin/
├── core/            Parsing CABL (AblParserFacade), cache (AblProjectAnalysisService),
│                    index de symboles (AblSymbolIndex), collecteur (AblSymbolCollector)
├── parser/          Pont ABLLexer → IntelliJ PSI (AblLexerAdapter, AblParserDefinition)
├── highlight/       Coloration, folding, bracket matcher, commenter
├── annotator/       Diagnostics syntaxiques en temps réel (ExternalAnnotator)
├── completion/      Autocomplétion 3 niveaux (sémantique, index, mots-clés)
├── documentation/   Hover documentation (built-ins + commentaires source)
├── navigation/      Go to Declaration, Find Usages, navigation includes
├── inspections/     Linting ABL (NO-UNDO, FIND sans lock)
├── refactor/        Renommage de symboles
├── structure/       Vue Structure (Alt+7)
├── project/         Lecture de openedge-project.json
├── startup/         Indexation initiale du projet en background
├── run/             Configuration d'exécution ABL
└── actions/         Re-indexer le projet, ouvrir la config
```

---

## Dépendance clé : RSSW proparse

Le parser ABL officiel, maintenu par Riverside Software pour chaque version OpenEdge.
Remplace entièrement les grammaires `.g4` maison.

```
eu.rssw.openedge.parsers:proparse:3.7.2
```

- Dépôt : `https://dl.cloudsmith.io/public/riverside-software/openedge-dev/maven/`
- Releases : https://github.com/Riverside-Software/sonar-openedge/releases

---

## Prérequis

- IntelliJ IDEA 2023.2+ (Community ou Ultimate)
- Java 17+
- Progress OpenEdge installé localement (optionnel — pour la résolution d'includes)

Aucun plugin tiers requis.

---

## Build

```bash
cd abl-intellij-plugin

# Lancer l'IDE sandbox (développement)
./gradlew runIde

# Construire le .zip distribuable
./gradlew buildPlugin
# → build/distributions/abl-intellij-plugin-1.0.0.zip

# Vérifier la compatibilité multi-versions IntelliJ
./gradlew verifyPlugin
```

---

## Configuration projet : `openedge-project.json`

Créer à la racine du workspace, ou via `Tools → Open openedge-project.json`.

```json
{
  "name": "Mon Projet ABL",
  "version": "12.7",
  "dlcPath": "/usr/dlc",
  "propath": ["src", "src/includes", "${DLC}/tty"],
  "buildPath": ".build",
  "charset": "UTF-8",
  "databases": [
    {
      "logicalName": "sports2020",
      "database": "/data/sports2020",
      "host": "localhost",
      "port": 8500,
      "schemaFile": ".schemas/sports2020.df"
    }
  ]
}
```

Le plugin charge automatiquement ce fichier au démarrage et à chaque modification.
Le `propath` et la `version` alimentent le parser CABL pour la résolution des includes.

---

## Mise à jour de proparse

Pour passer à une nouvelle version RSSW :

```kotlin
// build.gradle.kts
implementation("eu.rssw.openedge.parsers:proparse:NOUVELLE_VERSION") { ... }
```

Si proparse renomme des règles ANTLR4, vérifier les méthodes orphelines dans
`AblSymbolCollector.kt` (les visiteurs manquants sont ignorés silencieusement).

<!-- PR workflow test -->
