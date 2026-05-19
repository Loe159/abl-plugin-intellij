# CLAUDE.md — Plugin IntelliJ ABL (natif proparse)

Fichier de contexte pour Claude Code. Décrit l'architecture réelle, les commandes de build,
les APIs RSSW disponibles, l'état des fonctionnalités et les conventions du projet.

---

## Vue d'ensemble

Plugin IntelliJ IDEA **100 % natif** pour **Progress OpenEdge ABL**.
Pas de LSP server externe. Pas de LSP4IJ. Tout passe par les extension points IntelliJ
+ la bibliothèque **proparse** (Riverside Software / RSSW) embarquée directement.

- **Plugin layer :** Kotlin
- **Parsing :** `eu.rssw.openedge.parsers:proparse` (RSSW)
- **Target :** IntelliJ Platform 2023.2+
- **Package root :** `com.ablls.plugin`

---

## Commandes essentielles

```bash
cd abl-intellij-plugin

./gradlew runIde          # Lancer l'IDE sandbox (développement)
./gradlew buildPlugin     # → build/distributions/abl-intellij-plugin-1.0.0.zip
./gradlew verifyPlugin    # Vérifier la compatibilité multi-versions IntelliJ
./gradlew test            # Tests unitaires
```

---

## Structure du projet (ne pas réorganiser)

```
src/main/kotlin/com/ablls/plugin/
├── language/
│   ├── AblLanguage.kt               Singleton Language("ABL"). Référencé partout.
│   ├── AblFileType.kt               .p .cls .i .w .t → langue ABL.
│   └── AblIcons.kt                  Icônes SVG (resources/icons/).
│
├── parser/
│   ├── AblTokenTypes.kt             IElementType pour ~10 catégories de tokens.
│   ├── AblLexerAdapter.kt           PONT CENTRAL : ABLLexer (RSSW) → IntelliJ Lexer API.
│   │                                mapTokenType() : ABLNodeType → AblTokenType.
│   ├── AblParserDefinition.kt       Point d'entrée PSI : createLexer, createParser.
│   └── AblPsiParser.kt              AblFile (PsiFileBase), arbre plat.
│
├── highlight/
│   ├── AblSyntaxHighlighter.kt      AblTokenType → TextAttributesKey (couleurs).
│   ├── AblHighlighterFactory.kt     Factory pour IntelliJ.
│   ├── AblColorSettingsPage.kt      Settings → Editor → Color Scheme → ABL.
│   ├── AblFoldingBuilder.kt         Folding DO..END, PROCEDURE..END, CLASS..END.
│   ├── AblBracketMatcher.kt         Correspondance parenthèses/crochets.
│   └── AblCommenter.kt              // et /* */ (Ctrl+/).
│
├── core/
│   ├── AblParserFacade.kt           POINT D'ENTRÉE PARSING RSSW.
│   │                                Niveau 1 : parse() → AST + erreurs syntaxiques.
│   │                                Niveau 2 : analyze() → treeParser01() (types résolus).
│   ├── AblProjectAnalysisService.kt Service projet : cache parse + sémantique,
│   │                                index de symboles, gestion PROPATH.
│   ├── AblSymbolCollector.kt        Deux sources :
│   │                                1. ProparseBaseVisitor (AST ANTLR4)
│   │                                2. TreeParserSymbolScope (après treeParser01)
│   ├── AblSymbolIndex.kt            Index global par fichier + par nom.
│   │                                findByName(), findByPrefix(), getSymbolsForFile().
│   ├── AblSymbol.kt                 DTO symbole : nom, Kind, URI, Range, dataType, doc.
│   ├── AblSemanticResult.kt         DTO résultat sémantique : JPNode + TreeParserSymbolScope.
│   ├── AblParseResult.kt            DTO résultat syntaxique : ProgramContext + tokens + erreurs.
│   │                                topNode (JPNode lazy), queryNodes(ABLNodeType) → List<JPNode>.
│   ├── SyntaxError.kt               DTO erreur (ligne, colonne, message, URI).
│   ├── AblProparseKeywords.kt       Mots-clés ABL via ABLNodeType.values().filter { it.isKeyword }.
│   └── AblBuiltinDocs.kt            Documentation Markdown de ~92 fonctions built-in ABL.
│
├── annotator/
│   └── AblAnnotator.kt              ExternalAnnotator : diagnostics syntaxiques CABL
│                                    en temps réel (squiggles rouges).
│
├── completion/
│   ├── AblCompletionContributor.kt  3 sources de complétion :
│   │                                1. TreeParserSymbolScope (types exacts)
│   │                                2. AblSymbolIndex (projet entier)
│   │                                3. AblProparseKeywords filtrés par AblContextualCompletion
│   ├── AblContextualCompletion.kt   Tokens valides au curseur via l'ATN ANTLR4 de Proparse.
│   │                                Parse le source tronqué → IntervalSet attendus → keywords.
│   ├── AblAutoCaseTypedHandler.kt   Auto-casing des mots-clés à la frappe.
│   └── AblTemplateContextType.kt    Contexte pour les live templates.
│
├── documentation/
│   └── AblDocumentationProvider.kt  Hover : built-ins + symboles utilisateur
│                                    (commentaires /* */ précédant la définition).
│
├── navigation/
│   ├── AblGotoDeclarationHandler.kt Go to Declaration (Ctrl+B / Ctrl+Click) :
│   │                                - Symboles via AblSymbolIndex
│   │                                - Includes {file.i} → fichier source
│   └── AblFindUsagesProvider.kt     Find Usages (Alt+F7).
│
├── inspections/
│   ├── AblNoUndoInspection.kt       Avertissement NO-UNDO manquant. Quick Fix inclus.
│   ├── AblFindNoLockInspection.kt   Avertissement FIND sans SHARE/NO/EXCLUSIVE-LOCK.
│   ├── AblEmptyCatchInspection.kt
│   ├── AblFortranOperatorsInspection.kt
│   ├── AblMissingSchemaPrefixInspection.kt
│   ├── AblNoErrorWithoutCheckInspection.kt
│   ├── AblStringConcatInWhereInspection.kt
│   ├── AblUnusedVariableInspection.kt
│   └── AblInspectionHelper.kt
│
├── refactor/
│   └── AblRenameHandler.kt          Renommage de symboles (Shift+F6) via index.
│
├── structure/
│   └── AblStructureViewFactory.kt   Panneau Structure (Alt+7) : hiérarchie des symboles.
│
├── project/
│   ├── OpenEdgeProjectService.kt    Service IntelliJ : lit openedge-project.json.
│   └── AblProjectListener.kt        Recharge config quand le fichier change.
│
├── startup/
│   └── AblStartupActivity.kt        Post-startup : indexation du projet en background.
│
├── run/
│   └── AblRunConfigurationType.kt   Configuration d'exécution (.p via _progres/prowin).
│
├── actions/
│   └── AblActions.kt                ReindexProjectAction, OpenProjectConfigAction.
│
├── coverage/
│   ├── AblCoverageService.kt
│   ├── AblProfilerParser.kt
│   └── LoadCoverageAction.kt
│
├── debug/
│   ├── AblDebugConnection.kt        Protocole TCP vers OE (closed source, reverse-engineerd)
│   ├── AblDebugProcess.kt           Pont XDebugProcess ↔ AblDebugConnection
│   └── AblDebugSupport.kt           Breakpoint type, stack frame, value handling
│
├── duplication/
│   ├── AblDuplicationDetector.kt
│   ├── AblDuplicatesPanel.kt
│   ├── AblTokenNormalizer.kt
│   └── FindAblDuplicatesAction.kt
│
└── xref/
    ├── XrefParser.kt
    ├── XrefModel.kt
    ├── XrefPanel.kt
    ├── ShowXrefAction.kt
    └── XrefToolWindowFactory.kt

src/test/kotlin/com/ablls/plugin/
├── completion/
│   ├── AblCompletionContributorTest.kt
│   └── AblContextualCompletionTest.kt
├── core/
│   └── PrintMethodsTest.kt
└── highlight/
    └── AblFoldingBuilderTest.kt
```

---

## Dépendance critique : proparse (RSSW)

**C'est la seule dépendance de parsing — elle remplace entièrement toute grammaire maison.**

- Contient `ABLLexer`, `ABLParser`, `ABLNodeType` (~900 tokens), `ProparseBaseVisitor`.
- Maintenu par Riverside Software pour chaque version OpenEdge.
- Dépôt Maven : `https://dl.cloudsmith.io/public/riverside-software/openedge-dev/maven/`
- Releases : https://github.com/Riverside-Software/sonar-openedge/releases

```kotlin
// build.gradle.kts
repositories {
    maven("https://dl.cloudsmith.io/public/riverside-software/openedge-dev/maven/")
}

dependencies {
    implementation("eu.rssw.openedge.parsers:proparse:3.7.2") {
        exclude(group = "org.sonarsource.sonarqube")
        exclude(group = "org.sonarsource.analyzer-commons")
    }
}
```

> ⚠️ **LGPL compliance :** proparse est LGPL-3.0. Ne pas la shader dans le plugin jar.
> Toujours rester en dépendance dynamique.

---

## APIs RSSW — référence complète

### Règle absolue

`AblParserFacade` est le **seul endroit** du codebase qui instancie les classes RSSW de parsing.
Tous les autres fichiers reçoivent `AblParseResult` ou `AblSemanticResult`.
Ne jamais appeler `ParseUnit`, `ABLLexer` ou `Proparse` en dehors de `AblParserFacade`.

---

## Fichier de configuration : `openedge-project.json`

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

---

## Guide de migration : garder la structure, remplacer les internals

La structure de packages existante est **correcte et ne doit pas être réorganisée**.
La migration est interne : remplacer la logique ABL écrite à la main par les APIs RSSW,
fichier par fichier.

## État des fonctionnalités

> Consulter ce tableau avant tout développement pour ne pas redévelopper l'existant.

| Fonctionnalité | État | Fichier clé |
|---|---|---|
| Coloration syntaxique | ✅ Opérationnel | `AblLexerAdapter.kt` |
| Folding (DO/END, PROC/END...) | ✅ Opérationnel | `AblFoldingBuilder.kt` |
| Commenter (// et /* */) | ✅ Opérationnel | `AblCommenter.kt` |
| Live Templates (snippets) | ✅ Opérationnel | `liveTemplates/abl.xml` |
| Auto-casing des mots-clés | ✅ Opérationnel | `AblAutoCaseTypedHandler.kt` |
| Diagnostics syntaxiques | ✅ Opérationnel | `AblAnnotator.kt` |
| Complétion mots-clés (ABLNodeType) | ✅ Opérationnel | `AblProparseKeywords.kt` |
| Complétion contextuelle (ATN ANTLR4) | ✅ Opérationnel | `AblContextualCompletion.kt` |
| Complétion symboles projet | ✅ Opérationnel | `AblCompletionContributor.kt` |
| Complétion sémantique (typée) | ✅ Opérationnel | `AblCompletionContributor.kt` |
| Documentation hover built-ins | ✅ Opérationnel (~92) | `AblBuiltinDocs.kt` |
| Documentation hover symboles | ✅ Opérationnel | `AblDocumentationProvider.kt` |
| Go to Declaration | ✅ Opérationnel | `AblGotoDeclarationHandler.kt` |
| Go to Include (Ctrl+B sur {f.i}) | ✅ Opérationnel | `AblGotoDeclarationHandler.kt` |
| Structure View (Alt+7) | ✅ Opérationnel | `AblStructureViewFactory.kt` |
| Inspection NO-UNDO + Quick Fix | ✅ Opérationnel | `AblNoUndoInspection.kt` |
| Inspection FIND sans lock | ✅ Opérationnel | `AblFindNoLockInspection.kt` |
| Run Configuration (.p) | ✅ Opérationnel | `AblRunConfigurationType.kt` |
| SDK OpenEdge ABL (File → Project Structure → SDKs) | ✅ Opérationnel | `OpenEdgeSdkType.kt` |
| openedge-project.json | ✅ Opérationnel | `OpenEdgeProjectService.kt` |
| Find Usages (Alt+F7) | ✅ Scope-aware (TreeParserSymbolScope) | `AblFindUsagesProvider.kt` |
| Rename (Shift+F6) | ✅ Scope-aware (TreeParserSymbolScope) | `AblRenameHandler.kt` |
| Complétion tables/champs DB | ✅ Opérationnel (dot-notation + index) | `AblCompletionContributor.kt` |
| Chargement schéma .df | ✅ Opérationnel (DfSchemaParser + Schema RSSW) | `AblProjectAnalysisService.kt` |
| Inspection complexité cognitive | ✅ Opérationnel (CognitiveComplexityListener) | `AblCognitiveComplexityInspection.kt` |
| Inspection FIND FIRST sans NO-ERROR | ✅ Opérationnel | `AblFindFirstNoErrorInspection.kt` |
| Dead code (procédures non référencées) | ✅ Opérationnel (file-local, WEAK_WARNING) | `AblDeadCodeInspection.kt` |
| Inlay hints paramètres d'appel | ✅ Opérationnel | `AblParameterInlayHintsProvider.kt` |
| Find References sémantique | 🔧 Partiel (index textuel + scope kind) | `AblFindUsagesProvider.kt` |
| Complétion membres OO (TYPE:method) | ✅ Opérationnel (index-based, scope-aware) | `AblCompletionContributor.kt` |

---

## Prochaines étapes (priorités)

### 1. Chargement des fichiers `.df` (schéma DB)

Lire `databases[].schemaFile` depuis `openedge-project.json` et alimenter `Schema` :

```kotlin
// OpenEdgeProjectService.kt
val schema = Schema()
// Parser le .df et appeler schema.createTable(...)
val env = RefactorSession(ProparseSettings(propath), schema)
```

Débloque : complétion tables/champs, validation sémantique des `FIND` / `FOR EACH`.

### 2. Find References sémantique via `JPNode`

Après `treeParser01()`, parcourir `topNode` et collecter tous les nœuds où
`jpNode.getSymbol() === targetSymbol`. Remplace la recherche textuelle naïve actuelle.

```kotlin
// AblFindUsagesProvider.kt
val refs = mutableListOf<JPNode>()
topNode.walk { node ->
    if (node.getSymbol() === targetSymbol) refs.add(node)
    true
}
```

### 3. Rename sémantique

Utiliser les références JPNode (étape 2) pour ne renommer que les vraies références
au même symbole — pas les homonymes dans d'autres scopes.

### 4. Complétion membres OO (`TYPE:method`)

Résoudre le type de l'expression avant `:` depuis le scope, puis lister les membres
de la classe depuis `TreeParserSymbolScope`.

```kotlin
// AblCompletionContributor.kt
val typeInfo: ITypeInfo? = scope.resolveType(expressionBeforeColon)
typeInfo?.methods?.forEach { method ->
    result.addElement(LookupElementBuilder.create(method.name)
        .withTailText("(${method.signature})")
        .withTypeText(method.returnType.toString()))
}
```

---

## Roadmap complète

> Légende : ✅ Opérationnel · 🔧 Partiel / en cours · 📋 À implémenter · 🔴 Priorité haute · 🟠 Priorité moyenne · 🟡 Priorité basse · 🟢 Priorité faible

### Complétion avancée

| Priorité | Feature | État | Fichier clé |
|---|---|---|---|
| 🔴 | Complétion membres OO (`myObject:<caret>` → méthodes/propriétés) | ✅ | `AblCompletionContributor.kt` |
| 🔴 | Complétion tables et champs DB (après chargement `.df`) | ✅ | `AblCompletionContributor.kt` |
| 🟠 | Complétion des paramètres de procédure/fonction | ✅ | `AblCompletionContributor.kt` |
| 🟠 | Complétion des includes `{<caret>` → fichiers `.i` dans le PROPATH | ✅ | `AblCompletionContributor.kt` |
| 🟠 | Complétion des préprocesseurs (`&` → `&IF`, `&DEFINE`, `&SCOPED-DEFINE`…) | ✅ | `AblCompletionContributor.kt` |
| 🟡 | Postfix completion (`x.message` → `MESSAGE x.`) | ✅ | `AblPostfixTemplateProvider.kt` |

### Navigation

| Priorité | Feature | État | Fichier clé |
|---|---|---|---|
| 🔴 | Find Usages sémantique (`JPNode.getSymbol()`) | ✅ | `AblFindUsagesProvider.kt` |
| 🔴 | Rename sémantique (scope-aware) | ✅ | `AblRenameHandler.kt` |
| 🟠 | Go to Symbol (`Ctrl+Alt+Shift+N`) — procédures, classes, méthodes dans tout le projet | ✅ | `AblGotoSymbolContributor.kt` |
| 🟠 | Go to Class (`Ctrl+N`) — classes ABL OO | ✅ | `AblGotoClassContributor.kt` |
| 🟡 | Go to Related Symbol — naviguer entre `.cls` et son `.i` d'interface | ✅ | `AblGotoRelatedProvider.kt` |
| 🟡 | Breadcrumb navigation (classe → méthode → bloc courant) | ✅ | `AblBreadcrumbProvider.kt` |
| 🟡 | Navigate to Super Class / implementation (`Ctrl+U`) | ✅ | `AblSuperClassNavigator.kt` |
| 🟡 | Navigate to Overriding Methods | ✅ | `AblOverridingMethodsProvider.kt` |

### Hints et annotations inline

| Priorité | Feature | État | Fichier clé |
|---|---|---|---|
| 🟠 | Inlay hints de type sur les variables (`DEFINE VARIABLE x` → hint `: INTEGER`) | ✅ | `AblTypeInlayHintsProvider.kt` |
| 🟠 | Inlay hints sur les paramètres d'appel (`foo(/* INPUT */ 42, /* OUTPUT */ result)`) | ✅ | `AblParameterInlayHintsProvider.kt` |
| 🟠 | Inlay hints de valeur de retour | ✅ | `AblReturnValueInlayHintsProvider.kt` |
| 🟡 | Code Vision (nombre d'usages au-dessus de chaque déclaration) | ❌ Non disponible IC | API absente de Community SDK |

### Analyse et inspections supplémentaires

| Priorité | Feature | État | Fichier clé |
|---|---|---|---|
| 🟠 | Dead code detection (procédures jamais appelées) | ✅ | `AblDeadCodeInspection.kt` |
| 🟠 | Variables déclarées mais jamais utilisées (extension `AblUnusedVariableInspection`) | 📋 | `AblUnusedVariableInspection.kt` |
| 🟠 | `FIND FIRST` sans `NO-ERROR` dans un bloc `IF AVAIL` | ✅ | `AblFindFirstNoErrorInspection.kt` |
| 🟡 | Complexité cyclomatique (warning au-delà d'un seuil) | ✅ | `AblCyclomaticComplexityInspection.kt` (CC > 10) |
| 🟡 | Longueur de procédure excessive | ✅ | `AblProcedureLengthInspection.kt` |
| 🟡 | Nommage non conforme à la convention (préfixes `l`, `i`, `c`…) | ✅ | `AblNamingConventionInspection.kt` (disabled by default) |
| 🟡 | Utilisation de `INTEGER` au lieu de `INT64` pour les grands nombres | ✅ | `AblIntegerOverflowInspection.kt` |
| 🟡 | Détection des `LEAVE`/`NEXT` sans étiquette dans des boucles imbriquées | ✅ | `AblUnlabeledLoopControlInspection.kt` |
| 🟢 | Spell checking dans les strings et commentaires | ✅ | `AblSpellcheckingStrategy.kt` |

### Refactoring

| Priorité | Feature | État | Fichier clé |
|---|---|---|---|
| 🟡 | Extract Procedure (sélection → nouvelle `PROCEDURE`) | ✅ | `AblExtractProcedureIntention.kt` |
| 🟡 | Extract Method (dans une classe ABL) | 📋 | nouveau |
| 🟡 | Inline Variable | ✅ | `AblInlineVariableIntention.kt` |
| 🟡 | Introduce Variable (`DEFINE VARIABLE` à partir d'une expression) | ✅ | `AblIntroduceVariableIntention.kt` |
| 🟡 | Change Signature (renommer/réordonner les paramètres) | ✅ | `AblChangeSignatureIntention.kt` |
| 🟡 | Safe Delete (vérifie qu'aucun usage avant de supprimer) | ✅ | `AblSafeDeleteHandler.kt` + `AblRefactoringSupportProvider` |

### Formatter

| Priorité | Feature | État | Fichier clé |
|---|---|---|---|
| 🟠 | Code formatter complet (indentation, espaces, casse des mots-clés) | ✅ | `AblFormattingModelBuilder.kt` (indentation de base) |
| 🟡 | Import optimizer (trier/nettoyer les `USING` dans les classes OO) | ✅ | `AblOptimizeUsingsIntention.kt` |

### Debugger

> Package `debug/` : `AblDebugConnection`, `AblDebugProcess`, `AblDebugSupport` (+ ressource `resources/abl/oe-debug-bootstrap.p`).
> Détails du protocole et du flux dans la section "Debugger ABL — architecture et protocole" plus bas.

| Priorité | Feature | État | Fichier clé |
|---|---|---|---|
| 🔴 | Debug du fichier courant (bouton Debug, sans config manuelle) | ✅ | `AblProgramRunner.kt` |
| 🔴 | Breakpoints ligne | ✅ | `AblDebugSupport.kt` (AblLineBreakpointType) |
| 🔴 | Step Over / Step Into / Step Out / Resume / Pause | ✅ | `AblDebugProcess.kt` |
| 🔴 | Call Stack (multi-frames) avec navigation source | ✅ | `AblDebugConnection.parseStack`, `AblStackFrame` |
| 🔴 | Variables locales + paramètres (mode IO via flèches ←/→/↔) | ✅ | `AblDebugConnection.listVariables/listParameters` |
| 🟡 | Breakpoints conditionnels (`WHEN myVar > 0`) | 📋 | `AblDebugSupport.kt` |
| 🟡 | Evaluate Expression (`Alt+F8`) — passe l'expression brute à OE | ✅ (basique) | `AblDebugEvaluator` |
| 🟡 | Watchpoints (`watch <expr>` + `show watch`) | 📋 | nouveau |
| 🟡 | Temp-tables / DataSets (récupération + browse) | 📋 | nouveau |
| 🟡 | Inspection des classes OO (`GET-CLASS-INFO`) | 📋 | nouveau |
| 🟡 | Inspection des arrays (`GET-ARRAY`) | 📋 | nouveau |
| 🟠 | Remote Attach (AppServer / process OE existant) | 📋 | nouveau (utiliser `AblDebugConnection.connect()` direct) |
| 🟢 | Hot Swap | 📋 | impossible côté OE |
| 🟢 | Memory view : inspection des handles ABL (`WIDGET-HANDLE`, `QUERY-HANDLE`) | 📋 | nouveau |

### Database / DataSource

| Priorité | Feature | État | Fichier clé |
|---|---|---|---|
| 🔴 | Chargement automatique du `.df` comme schéma | ✅ | `AblProjectAnalysisService.kt` |
| 🔴 | Complétion DB dans le code (noms de tables et champs) | ✅ | `AblCompletionContributor.kt` |
| 🔴 | Validation des requêtes (champs référencés existent dans le schéma) | ✅ | `AblSchemaValidationInspection.kt` |
| 🟠 | Enregistrement d'une DataSource ABL dans la fenêtre "Database" d'IntelliJ | 📋 | nouveau |
| 🟠 | Exploration du schéma : tables, champs, index, séquences | ✅ | `AblSchemaExplorerPanel.kt` (ToolWindow "ABL Schema") |
| 🟡 | SQL Console ABL : requêtes `FOR EACH` avec complétion depuis le schéma | 📋 | nouveau |
| 🟢 | ER Diagram généré depuis le `.df` | 📋 | nouveau |
| 🟢 | DB Connection live pour inspecter les données réelles | 📋 | nouveau |

### Profiler

> Package `coverage/` existant : `AblCoverageService`, `AblProfilerParser`, `LoadCoverageAction`.

| Priorité | Feature | État | Fichier clé |
|---|---|---|---|
| 🟠 | Vue Profiler : temps CPU, nombre d'appels, par procédure/méthode | ✅ | `AblProfilerViewPanel.kt` (ToolWindow "ABL Profiler") |
| 🟠 | Coverage : lignes couvertes/non couvertes dans la gouttière | ✅ | `AblCoverageLineMarkerProvider.kt` + `AblCoverageService.isLineCovered()` |
| 🟠 | Hot Spots : mise en évidence des lignes coûteuses dans l'éditeur | ✅ | `AblHotSpotAnnotator.kt` |
| 🟠 | Intégration avec les Run Configurations (lancer avec profiling en un clic) | 📋 | `AblRunConfigurationType.kt` |
| 🟡 | Flame Graph : visualisation de la pile d'appels avec les temps | 📋 | nouveau |
| 🟡 | Coverage diff : comparaison de deux runs | 📋 | nouveau |

### Build

| Priorité | Feature | État | Fichier clé |
|---|---|---|---|
| 🟠 | Compilation ABL via PCT (Apache Ant tasks de Riverside Software) | 📋 | nouveau |
| 🟠 | Compilation incrémentale (recompiler uniquement les fichiers modifiés) | 📋 | nouveau |
| 🟠 | Rapport d'erreurs de compilation dans le panneau "Problems" | 📋 | nouveau |
| 🟠 | Intégration du fichier XREF (`.xref` / `.xref-xml`) | 📋 | `xref/XrefParser.kt` |
| 🟡 | Build Configuration (équivalent `build.xml` / PCT) | 📋 | nouveau |
| 🟡 | Gutter icon "compile this file" sur les `.p` | ✅ | `AblCompileGutterIconProvider.kt` |
| 🟡 | Pre-compile checks (lancer les inspections avant la compilation) | 📋 | nouveau |

### Tests ABLUnit

| Priorité | Feature | État | Fichier clé |
|---|---|---|---|
| 🔴 | Test Runner ABL (ABLUnit framework de Progress) | 📋 | nouveau |
| 🔴 | Reconnaissance des classes de test (`@Test`, `@Before`…) | 📋 | nouveau |
| 🟠 | Gutter icon "Run test" sur chaque méthode de test | ✅ | `AblTestRunLineMarkerProvider.kt` |
| 🟠 | Fenêtre Test Results (pass/fail/error avec détail) | 📋 | nouveau |
| 🟠 | Re-run failed tests | 📋 | nouveau |
| 🟡 | Coverage depuis les tests (couverture mesurée par ABLUnit) | 📋 | `AblCoverageService.kt` |

### Gestion de projet

| Priorité | Feature | État | Fichier clé |
|---|---|---|---|
| 🟡 | Project Wizard : template "New OpenEdge ABL Project" | ✅ | `AblNewProjectWizard.kt` |
| 🟡 | Project Settings UI : panneau Settings → OpenEdge | ✅ | `AblProjectSettingsConfigurable.kt` |
| 🟡 | PROPATH explorer : visualiser et éditer le PROPATH depuis l'IDE | ✅ | `AblPropathExplorerPanel.kt` (ToolWindow "ABL PROPATH") |
| 🟢 | Module system : support des projets multi-modules ABL | 📋 | nouveau |
| 🟢 | Dependency management (OE Package Manager ?) | 📋 | nouveau |

### Intégrations externes

| Priorité | Feature | État | Fichier clé |
|---|---|---|---|
| 🟡 | SonarLint integration (règles CABL de sonar-openedge dans IntelliJ) | 📋 | nouveau |
| 🟡 | PCT Ant tasks (exécution de tâches PCT depuis l'IDE) | 📋 | nouveau |
| 🟢 | OpenEdge AppServer : déploiement et invocation de procédures | 📋 | nouveau |
| 🟢 | PASOE : déploiement avec logs en temps réel | 📋 | nouveau |
| 🟢 | Docker : container OpenEdge pour tests et compilation | 📋 | nouveau |

### UX / Ergonomie

| Priorité | Feature | État | Fichier clé |
|---|---|---|---|
| 🟠 | Intention Actions (ampoule jaune) : suggestions contextuelles | ✅ | `AblAddNoUndoToAllIntention.kt`, `AblSurroundDescriptor.kt` |
| 🟡 | Sticky lines : signature de la procédure courante en haut de l'éditeur | ❌ Non disponible IC | API absente de Community SDK |
| 🟡 | Rainbow brackets : coloration des blocs `DO/END` imbriqués | ❌ Non disponible IC | API absente de Community SDK |
| 🟡 | Color Settings avancés : thème sombre/clair bien différencié | 📋 | `AblColorSettingsPage.kt` |
| 🟢 | Editor tabs : icône distincte par type (`.cls` vs `.p` vs `.i`) | 📋 | `AblIcons.kt` |
| 🟢 | Scratch files : support ABL dans les fichiers temporaires | 📋 | nouveau |

---

## Points chauds (pièges connus)

### 1. `treeParser01()` peut lever des exceptions sur du code invalide

Toujours entourer d'un `try/catch` et fallback sur le résultat syntaxique simple :

```kotlin
// Dans AblParserFacade.analyze(parseResult: AblParseResult)
try {
    parseResult.parseUnit!!.treeParser01()
    AblSemanticResult(parseResult.topNode, getRootScopeSafely(pu), emptyList(), parseResult.uri)
} catch (e: Exception) {
    LOG.warn("treeParser01 failed for ${parseResult.uri}: ${e.message}")
    AblSemanticResult(null, null, parseResult.syntaxErrors, parseResult.uri)
}
```

### 2. `getRootScope()` est parfois réfléchi (pas toujours public)

```kotlin
fun getRootScopeSafely(pu: ParseUnit): TreeParserSymbolScope? =
    runCatching {
        pu.javaClass.getMethod("getRootScope").invoke(pu) as? TreeParserSymbolScope
    }.getOrNull()
```

### 3. Le `.` ABL est ambigu

`.` est à la fois terminateur d'instruction, séparateur de package et séparateur de champ.
CABL/proparse gère ça nativement — ne jamais essayer de le tokeniser côté plugin.

### 4. PROPATH nécessaire pour résoudre les `{include.i}`

Sans PROPATH, les includes non résolus génèrent des centaines d'erreurs en cascade.
Le service limite l'affichage à 20 erreurs + message d'avertissement utilisateur.

### 5. Vérifier les noms de classes après un update proparse

```bash
jar tf ~/.m2/repository/eu/rssw/openedge/parsers/proparse/*/proparse-*.jar \
    | grep "ABLParserBaseVisitor\|TreeParserSymbolScope"
```

Certains noms de classes internes changent entre versions mineures.

### 6. Positions : proparse est 1-based, IntelliJ est 0-based

```kotlin
// Toujours convertir avant d'utiliser dans l'API IntelliJ
val intellijLine = node.token.line - 1
val intellijCol  = node.token.charPositionInLine  // déjà 0-based
```

---

## Conventions de code

- `AblLexerAdapter.mapTokenType()` : `when` exhaustif sur `ABLNodeType`, `else → KEYWORD` générique.
- Services IntelliJ (`@Service`) : injectés via `project.service<X>()`, jamais instanciés directement.
- Les analyses sémantiques (`treeParser01`) sont lancées en background via `executeOnPooledThread`.
- Jamais de blocage sur l'EDT — toujours `invokeLater` pour les updates UI.
- Pas de `!!` (non-null assertion) — utiliser `?: return` ou `?: return@visitor`.
- Logger avec `thisLogger()`, jamais `println` ou `System.out`.

---

## Testing

> Chaque feature doit avoir un test correspondant. Toujours vérifier la table d'état
> avant d'implémenter pour ne pas écrire des tests sur du code déjà existant.

### Classes de base JetBrains — choisir la bonne

```
LexerTestCase              ← tests de tokenisation pure (pas de projet, rapide)
ParsingTestCase            ← tests de forme de l'arbre PSI (pas de projet)
BasePlatformTestCase       ← tests avec projet + module + VFS en mémoire
  └── myFixture            ← CodeInsightTestFixture pour les tests éditeur
```

### Organisation des données de test

```
src/test/testData/
├── lexer/           ← fichiers .p/.cls pour LexerTestCase
├── parser/
│   └── parsing/     ← arbres PSI attendus (.txt, générés avec -Dupdate=true)
├── completion/      ← fichiers avec <caret>
├── highlighting/    ← fichiers avec marqueurs <info>/<warning>/<error>
├── inspections/     ← fichiers avec marqueurs <warning descr="...">
└── folding/         ← fichiers avec marqueurs <fold text="...">...</fold>
```
### Conventions de test

| Convention | Règle |
|---|---|
| Nommage | `<TestedClass>Test.kt` dans le package miroir sous `test/` |
| Données | snake_case, extension `.p` ou `.cls` selon le type ABL |
| Inline vs fichier | `configureByText` pour < 10 lignes, fichier `testData/` au-delà |
| Assertions | Toujours sur `ABLNodeType` ou types PSI — jamais sur des strings brutes |
| Cas négatifs | Toujours tester le cas "pas d'erreur quand le code est correct" |
| CI | `./gradlew test` doit passer à 100% avant tout merge |

---

## Références

- [IntelliJ Custom Language Support](https://plugins.jetbrains.com/docs/intellij/custom-language-support.html)
- [IntelliJ Testing Guide](https://plugins.jetbrains.com/docs/intellij/testing-plugins.html)
- [IntelliJ Light & Heavy Tests](https://plugins.jetbrains.com/docs/intellij/light-and-heavy-tests.html)
- [sonar-openedge GitHub](https://github.com/Riverside-Software/sonar-openedge)
- [vscode-abl (utilise le même LSP)](https://github.com/vscode-abl/vscode-abl)
- [JetBrains Plugin Template](https://github.com/JetBrains/intellij-platform-plugin-template)

---

## Audit technique (2026-05-13)

> Audit complet de l'intégration IntelliJ (extension points, RSSW, architecture).
> Légende verdicts : ✅ OK · 🟡 Mineur · 🔴 Refaire · ❌ Absent

### Dette architecturale : PSI plat

`AblPsiParser` produit un arbre PSI **plat** — tous les tokens sont enfants directs de `AblFile`.
Cause racine de plusieurs limitations qui ne peuvent pas être corrigées sans restructurer le PSI :

- **Breadcrumbs** : `getParent()` retourne null → aucune hiérarchie réelle
- **Formatter** : impossible de distinguer "token dans un bloc DO" de "token hors bloc"
- **Find Usages** : pas de `PsiReference` possible → fallback textuel permanent
- **Surround With** : `getElementsToSurround()` ne peut pas sélectionner des blocs complets

Si le PSI plat est conservé, documenter ces limitations comme "by design" plutôt que les contourner
individuellement. Sinon, migrer vers un PSI structuré en adaptant `AblPsiParser` pour construire
des nœuds composites (via `PsiBuilder` + markers pour PROCEDURE/CLASS/DO blocks).

### Bloc 1 — Bases du langage

| Feature | Fichier | EP correct | RSSW | Verdict |
|---|---|---|---|---|
| FileType | `AblFileType.kt` | ✅ `fileType` | n/a | ✅ OK |
| Lexer | `AblLexerAdapter.kt` | ✅ `lang.parserDefinition` | ⚠️ `ABLNodeType.getLiteral()` seulement — scanner maison complet | 🟡 Risque divergence RSSW |
| Parser/PSI | `AblParserDefinition.kt` | ✅ `lang.parserDefinition` | ❌ PSI plat | 🟡 Limite nav/formatter/breadcrumbs |
| Syntax Highlighting | `AblSyntaxHighlighter.kt` | ✅ `lang.syntaxHighlighterFactory` | n/a | ✅ OK |
| Color Settings | `AblColorSettingsPage.kt` | ✅ `colorSettingsPage` | n/a | ✅ OK |
| Bracket Matching | `AblBracketMatcher` | ✅ `lang.bracketMatcher` | n/a | 🟡 `()` seulement |
| Commenter | `AblCommenter` | ✅ `lang.commenter` | n/a | ✅ OK |
| Folding | `AblFoldingBuilder.kt` | ✅ `lang.foldingBuilder` | ⚠️ `ABLNodeType` pour classification, scan linéaire | ✅ OK |

### Bloc 2 — Éditeur enrichi

| Feature | Fichier | EP correct | RSSW | Verdict |
|---|---|---|---|---|
| Formatter | `AblFormattingModelBuilder.kt` | ✅ `lang.formatter` | ❌ | 🟡 Indentation basique uniquement |
| Code Style Settings | ❌ absent | `langCodeStyleSettingsProvider` | — | ❌ Absent → ajouté en tâche 9 |
| Surround With | `AblSurroundDescriptor.kt` | ✅ `lang.surroundDescriptor` | n/a | ✅ OK |
| Postfix Templates | `AblPostfixTemplateProvider.kt` | ✅ `postfixTemplateProvider` | n/a | ✅ OK |
| Live Templates | `abl.xml` + `AblTemplateContextType.kt` | ✅ | n/a | ✅ OK |
| Spell Checking | `AblSpellcheckingStrategy.kt` | ✅ `spellchecker.support` | n/a | ✅ OK |
| Sticky Lines | ❌ absent | `com.intellij.ui.stickyLines` | — | ❌ Absent (optionnel) |

### Bloc 3 — Complétion

| Feature | Fichier | EP correct | RSSW | Verdict |
|---|---|---|---|---|
| Keyword + symboles | `AblCompletionContributor.kt` | ✅ `completion.contributor` | ✅ `TreeParserSymbolScope` | ✅ OK |
| OO member (myObj:) | `AblCompletionContributor.kt` | ✅ | ✅ scope + index | ✅ OK |
| Parameter completion | `AblCompletionContributor.kt` | ⚠️ dans contributor, pas `ParameterInfoHandler` (Ctrl+P absent) | ✅ `Routine.parameters` | 🟡 → tâche 5 |
| Inlay hints | `AblParameterInlayHintsProvider.kt` | ✅ `codeInsight.inlayProvider` | ✅ | ✅ OK |

### Bloc 4 — Navigation

| Feature | Fichier | EP correct | RSSW | Verdict |
|---|---|---|---|---|
| Go to Declaration | `AblGotoDeclarationHandler.kt` | ✅ `gotoDeclarationHandler` | ✅ `TreeParserSymbolScope` | ✅ OK |
| Go to Symbol | `AblGotoSymbolContributor.kt` | ✅ `gotoSymbolContributor` | ✅ | ✅ OK |
| Go to Class | `AblGotoClassContributor` | ✅ `gotoClassContributor` | ✅ | ✅ OK |
| Go to Related | `AblGotoRelatedProvider.kt` | ✅ `gotoRelatedProvider` | — | ✅ OK |
| Super class (Ctrl+U) | `AblSuperClassNavigator.kt` | ✅ `codeInsight.gotoSuper` | ⚠️ scan textuel INHERITS | 🟡 |
| Overriding Methods | `AblOverridingMethodsProvider.kt` | ✅ `codeInsight.lineMarkerProvider` | ❌ index textuel | 🟡 Faux positifs possibles |
| Breadcrumbs | `AblBreadcrumbProvider.kt` | ✅ `breadcrumbsInfoProvider` | ❌ | ✅ `getParent()` text-based (scan siblings, stack blocs) |
| Find Usages | `AblFindUsagesProvider.kt` + `AblReferenceContributor.kt` | ✅ `lang.findUsagesProvider` + `psi.referenceContributor` | ✅ `AblSymbolReference.isReferenceTo()` via RSSW scope | ✅ Sémantique |

### Bloc 5 — Inspections

| Feature | EP correct | RSSW | Verdict |
|---|---|---|---|
| 17 inspections | ✅ `localInspection` + `LocalInspectionTool` | ✅ `topNode.query*()` | ✅ OK |
| groupPath | `groupPath="ABL"` ⚠️ doit être `"OpenEdge ABL"` | — | 🟡 → tâche 2 |

### Bloc 6 — Refactoring

| Feature | Fichier | EP correct | RSSW | Verdict |
|---|---|---|---|---|
| Rename | `AblRenameHandler.kt` | ✅ `renameHandler` | ✅ scope-aware | 🟡 Dialogue custom (pas `RenameDialog`) |
| Safe Delete | `AblSafeDeleteHandler.kt` | ❌ `AblSafeDeleteAction` non enregistrée dans plugin.xml | ⚠️ | 🔴 Inaccessible → tâche 3 |
| Extract/Inline/Introduce/ChangeSignature | `intentions/*.kt` | ⚠️ `intentionAction` (Alt+Enter), pas Ctrl+Alt+Shift+T | ❌ | 🟡 UX non native |

### Bloc 7 — Structure

| Feature | EP correct | RSSW | Verdict |
|---|---|---|---|
| Structure View | ✅ `lang.psiStructureViewFactory` | ✅ | ✅ OK |
| Class/Call Hierarchy | ❌ absent | — | ❌ Absent |

### Bloc 8 — Documentation

| Feature | EP correct | RSSW | Verdict |
|---|---|---|---|
| Quick doc (Ctrl+Q) | ✅ `lang.documentationProvider` | ✅ `Routine.getIDESignature()`, `Variable.*` | ✅ OK |
| External doc link | `getUrlFor()` non implémenté | — | ❌ Absent (optionnel) |

### Bloc 9 — Run / Build

| Feature | EP correct | RSSW | Verdict |
|---|---|---|---|
| Run Configuration | ✅ `configurationType` + `runConfigurationProducer` | n/a | ✅ OK |
| Build / PCT | ❌ absent | — | ❌ Absent |
| Gutter Compile | ✅ `codeInsight.lineMarkerProvider` | n/a | ✅ OK |

### Bloc 10 — Tests ABLUnit

| Feature | EP correct | RSSW | Verdict |
|---|---|---|---|
| Gutter @Test | ✅ `codeInsight.lineMarkerProvider` | ❌ | 🔴 Action null (clic ne fait rien) → supprimé tâche 7 |
| Test Runner | ❌ absent | — | 🔴 Absent — nécessite `SMTRunnerConsoleProperties` + protocole ABLUnit |
| Coverage | ❌ `RangeHighlighter` custom | ❌ | 🔴 Doit utiliser `com.intellij.coverage.CoverageEngine` |

### Bloc 11 — Profiler

| Feature | EP correct | RSSW | Verdict |
|---|---|---|---|
| Vue Profiler | ❌ ToolWindow Swing custom | ❌ | 🔴 Doit utiliser `com.intellij.profiler.ProfilerExecutorGroup` |
| Hot Spots | ✅ `codeInsight.inlayProvider` | ⚠️ Proxy incorrect (numéros de ligne ≠ counts) | 🟡 → tâche 6 (fix counts réels) |

### Bloc 12 — Base de données

| Feature | EP correct | RSSW | Verdict |
|---|---|---|---|
| Schema Explorer | ❌ ToolWindow JTree custom | ⚠️ Via `AblSymbolIndex` | 🔴 Doit utiliser `com.intellij.database` (Ultimate seulement) |

### Bloc 13 — Project Wizard

| Feature | EP correct | RSSW | Verdict |
|---|---|---|---|
| New Project | ❌ Non enregistré dans plugin.xml | — | 🔴 Inaccessible → tâche 4 |

### Bloc 14 — Settings

| Feature | EP correct | Verdict |
|---|---|---|
| Settings panel | ✅ `projectConfigurable` + `parentId="language"` | 🟡 UI read-only (`isModified()` always false) — délibéré |

---

### Plan de correction par priorité

> Tâches réalisées en session (commit+push après chaque) :

| Tâche | Bloc | Changement | Fichiers |
|---|---|---|---|
| 1 | CLAUDE.md | Rapport d'audit | `CLAUDE.md` |
| 2 | Bloc 5 | `groupPath` → `"OpenEdge ABL"` dans plugin.xml | `plugin.xml` |
| 3 | Bloc 6 | Enregistrer `AblSafeDeleteAction` dans `<actions>` | `plugin.xml` |
| 4 | Bloc 13 | `AblModuleBuilder` + registration | nouveau + `plugin.xml` |
| 5 | Bloc 3 | `AblParameterInfoHandler` (Ctrl+P) | nouveau + `plugin.xml` |
| 6 | Bloc 11 | Fix hot spots — vrais counts depuis `AblProfilerParser` | `AblProfilerParser.kt`, `AblCoverageService.kt`, `AblHotSpotAnnotator.kt` |
| 7 | Bloc 10 | Supprimer gutter @Test (action null = UX trompeuse) | `AblTestRunLineMarkerProvider.kt`, `plugin.xml` |
| 8 | Bloc 2 | `AblCodeStyleSettingsProvider` | nouveau + `plugin.xml` |
| 9 | Bloc 8 | `getUrlFor()` — external doc link vers docs.progress.com | `AblDocumentationProvider.kt` |
| 10 | Bloc 1 | `AblSymbolCollector` capture INHERITS/IMPLEMENTS dans `dataType` | `AblSymbolCollector.kt` |
| 11 | Bloc 7 | `AblTypeHierarchyProvider` (Ctrl+H) — sous/supertypes via INHERITS | nouveau + `plugin.xml` |
| 12 | Bloc 7 | `AblCallHierarchyProvider` (Ctrl+Alt+H) — callers/callees via RUN | nouveau + `plugin.xml` |
| 13 | Bloc 6 | 4 AnActions refactoring dans le menu Refactor (Ctrl+Alt+Shift+T) | nouveau + `plugin.xml` |
| 14 | Bloc 4 | `AblOverridingMethodsProvider` scope-aware (INHERITS, deux directions) | `AblOverridingMethodsProvider.kt` |
| 15 | Bloc 4 | `AblSuperClassNavigator` utilise l'index au lieu du scan textuel | `AblSuperClassNavigator.kt` |
| 16 | Bloc 4 | `AblReferenceContributor` — PsiReference sémantique sur les identifiants | nouveau + `plugin.xml` |
| 17 | Bloc 2 | `AblFormattingModelBuilder` — indentation structurelle en O(n) via depth tracking | `AblFormattingModelBuilder.kt` |
| 18 | Bloc 1 | BracketMatcher — ajout de `[` `]` + `LBRACKET`/`RBRACKET` dans lexer | `AblFoldingBuilder.kt`, `AblLexerAdapter.kt`, `AblTokenTypes.kt` |
| 19 | PSI | `AblAstFactory` + `AblNamedLeafElement` — `PsiNamedElement` sur les IDENTIFIER tokens | nouveau + `plugin.xml` |
| 20 | Bloc 6 | Migration vers `RenameDialog` natif via `PsiNamedElement` + `handleElementRename()` | `AblIdentifierElement.kt`, `plugin.xml` |
| 21 | Bloc 4 | `AblBreadcrumbProvider.getParent()` — scan text-based de siblings, stack blocs DO/END | `AblBreadcrumbProvider.kt` |
| 22 | Docs | `AblBuiltinDocs` — correctif typo "LENGTHs", +130 built-ins (OO, I/O, DB, préprocesseur) | `AblBuiltinDocs.kt` |
| 23 | UX | Dictionnaire spellchecker ABL embarqué (PROPATH, RECID, LONGCHAR, ROWID…) | `AblBundledDictionaryProvider.kt`, `spellchecker/abl.dic` |
| 24 | Hints | `AblReturnValueInlayHintsProvider` — type de retour après parenthèse fermante des appels | `AblReturnValueInlayHintsProvider.kt`, `plugin.xml` |
| 25 | Tests | Tests `AblBreadcrumbProviderTest` (8 cas) + `AblBuiltinDocsTest` (11 cas) | tests |
| 26 | Templates | +13 live templates (dowhile, fori, output, input, interface, deleteobj, readjson…) | `liveTemplates/abl.xml` |
| 27 | SDK | `OpenEdgeSdkType` — SDK natif IntelliJ (File → Project Structure → SDKs), `resolveDlc()` priorité SDK | `OpenEdgeSdkType.kt`, `AblRunConfigurationType.kt`, `AblModuleBuilder.kt`, `plugin.xml` |

> Chantiers multi-jours (documentés, non implémentés en session) :

| Chantier | Effort estimé | Blocker |
|---|---|---|
| Coverage via `CoverageEngine` | 3-5 jours | API complexe : `CoverageEngine`, `CoverageSuite`, `CoverageAnnotator`, `CoverageRunner` |
| Profiler via `ProfilerExecutorGroup` | 3-5 jours | API expérimentale IntelliJ, dépend du format .prof RSSW |
| Database via `com.intellij.database` | 5+ jours | Dépend d'IntelliJ **Ultimate** — nécessite dépendance optionnelle (`<depends optional="true">com.intellij.database</depends>`) |
| Test Runner ABLUnit (SMTestProxy) | 5+ jours | Nécessite protocole de communication avec ABLUnit + `SMTRunnerConsoleProperties` |
| PSI structuré (non-plat) | 3-5 jours | Débloquerait Find Usages sémantique, Formatter complet, Breadcrumbs réels |
| Protocole debugger OE réel | ✅ Implémenté | Voir section dédiée ci-dessous. |

---

## Debugger ABL — architecture et protocole

### Vue d'ensemble

Le debugger est **natif** et **transparent** : cliquer sur le bouton Debug d'un fichier
`.p`/`.w` ouvert dans l'éditeur démarre une session debug — sans configuration manuelle.

Flux complet (4 fichiers) :

```
AblProgramRunner.kt          orchestre le lancement
AblDebugConnection.kt        protocole binaire vers OE (closed source, reverse-engineerd)
AblDebugProcess.kt           pont XDebugProcess ↔ AblDebugConnection
AblDebugSupport.kt           breakpoint type, stack frame, value handling
+ resources/abl/oe-debug-bootstrap.p   sas READKEY entre OE et IntelliJ
```

### Lancement (`AblProgramRunner.launch`)

1. Allouer un port libre (≥ 1024 — ports privilégiés rejetés par `-debugReady` sur Windows).
2. Extraire `oe-debug-bootstrap.p` du JAR vers `$TEMP/abl-debug/`.
3. Spawn :
   ```
   _progres.exe -b -p <bootstrap.p> -debugReady <PORT>
     ENABLE_OPENEDGE_DEBUGGER=1
     ABL_DEBUG_PROGRAM=<fichier utilisateur>
     ABL_DEBUG_PROPATH=<propath depuis openedge-project.json>
     DLC=<SDK ou config>
   ```
4. `AblDebugConnection.connectWithRetry()` — IntelliJ ouvre **deux** sockets vers PORT (retry 15 s).
5. Session XDebug démarre. IntelliJ propage les breakpoints existants au handler.
6. `AblDebugProcess.sessionInitialized()` envoie `SETPROP IDE 1` + liste BPs, puis écrit `\r`
   sur stdin du process → libère le `READKEY` du bootstrap → le programme utilisateur démarre.

### Résolution du DLC

Priorité dans `AblRunState.resolveDlc()` :
1. Champ "DLC path" de la config Run (si renseigné)
2. **SDK OpenEdge ABL** configuré dans File → Project Structure → SDKs
3. `dlcPath` dans `openedge-project.json`
4. Variable d'environnement `$DLC`

### Protocole OE — closed source, reverse-engineerd

Le protocole binaire d'OE n'est pas documenté par Progress. La référence est
[vscode-abl](https://github.com/chriscamicas/vscode-abl) (`src/debugAdapter/`),
qui l'a reverse-engineerd via Wireshark. Confirmé localement avec `tools/oe-debug-proxy.py`.

**Architecture** : OE = serveur (écoute sur `-debugReady PORT`), IntelliJ = client.
IntelliJ ouvre deux sockets vers le même port :
- `recvSocket` — premier connect, IntelliJ y lit les événements OE
- `sendSocket` — second connect,  IntelliJ y écrit les commandes IDE

**Encodage** : messages texte ASCII/UTF-8 terminés par un octet nul `\0`.
Plusieurs messages peuvent arriver dans un seul paquet TCP.

**Commandes IDE → OE** :

| Commande                            | Effet |
|---|---|
| `SETPROP IDE 1`                     | Handshake initial — active le mode debug |
| `break B;id;E;path;line; ;…`        | Liste complète des breakpoints (renvoyée à chaque modification) |
| `break;`                            | Efface tous les breakpoints |
| `cont`                              | Reprend l'exécution |
| `next`                              | Step Over |
| `step`                              | Step Into |
| `step-out`                          | Step Out |
| `interrupt`                         | Pause |
| `show stack-ide`                    | Demande la pile (réponse `STACK-IDE`) |
| `list variables`                    | Demande les variables locales (réponse `MSG_VARIABLES`) |
| `list parameters`                   | Demande les paramètres (réponse `MSG_PARAMETERS`) |
| `SETPROP IDE 0`                     | Termine la session debug |

**Événements OE → IDE** :

| Code           | Sens |
|---|---|
| `MSG_ENTER`    | OE vient de se suspendre (breakpoint, step, pause). Les BPs sont effacés à chaque entrée dans un nouveau scope — il faut les renvoyer. |
| `MSG_EXIT`     | OE quitte (programme terminé ou interrompu) |
| `STACK-IDE`    | Pile d'appels — une frame par ligne, champs sépares par `;`. Indexation : `[4]`=file, `[6]`=function, `[8]`=line. |
| `MSG_VARIABLES`| Variables locales — `name;type;classType?;?;extent;R|RW;value;` par ligne |
| `MSG_PARAMETERS`| Paramètres — `INPUT|OUTPUT|INPUT-OUTPUT;name;type;?;?;value;` par ligne |
| `MSG_LISTING`  | Info BPs / position — ignoré (on récupère la position via `STACK-IDE`) |
| `MSG_STATUS`, `MSG_INFO` | Informationnels — ignorés |

**Encodage CHARACTER/LONGCHAR** : `\x12<digits>"value"` (DC2 + longueur + value entre quotes).
Voir `AblDebugConnection.decodeValue()`.

### Points d'attention

- OE clear ses breakpoints à chaque `MSG_ENTER`. `AblDebugConnection.dispatch()` les renvoie
  automatiquement.
- `_progres.exe` est le seul binaire à interpréter `-debugReady` correctement. `prowin.exe`
  le parse caractère par caractère.
- Le bootstrap `READKEY` est obligatoire : sans ce sas, OE exécuterait le programme avant
  qu'IntelliJ ait fini son handshake → breakpoints jamais atteints.
- `tools/oe-debug-proxy.py` permet de capturer le trafic d'une vraie session PDSOE ↔ OE
  pour valider/étendre le protocole.
