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
│   ├── AblDebugConfigurationType.kt
│   ├── AblDebugConnection.kt
│   ├── AblDebugProcess.kt
│   └── AblDebugSupport.kt
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

### Niveau 1 — Parsing syntaxique (`AblParserFacade.parse`)

Produit un AST ANTLR4 + liste d'erreurs. Rapide, pas de résolution de symboles.

```kotlin
val ablLexer = ABLLexer(session, charset, bytes, uri, false)
val lex = Lexer(ablLexer, bytes, uri)
val postLexer = PostLexer(ablLexer, lex)
val tokenList = TokenList(postLexer)
val tokens = CommonTokenStream(tokenList)
val parser = Proparse(tokens)
parser.initialize(session, null)
val tree: Proparse.ProgramContext = parser.program()
```

Produit :
- `Proparse.ProgramContext` — arbre ANTLR4 visitable avec `ProparseBaseVisitor`
- `CommonTokenStream` — accès aux tokens du hidden channel (commentaires, whitespace)

---

### Niveau 2 — Analyse sémantique (`AblParserFacade.analyze`)

Résout les symboles, types et références. Plus lent — toujours en background thread.

```kotlin
val pu = object : ParseUnit(content, uri, session) {}
pu.parse()
pu.treeParser01()   // ← résout symboles, types, références croisées
val scope: TreeParserSymbolScope = pu.getRootScope()
val topNode: JPNode = pu.getTopNode()
```

Produit :
- `TreeParserSymbolScope` — scope racine avec toutes les déclarations
- `JPNode` — arbre sémantique avec `JPNode.getSymbol()` résolu

---

### APIs `TreeParserSymbolScope`

```kotlin
scope.variables          // List<Variable>              — toutes les variables définies
scope.routines           // List<Routine>               — procédures, fonctions, méthodes
scope.childScopes        // List<TreeParserSymbolScope> — sous-scopes (corps de proc...)
scope.getBufferList()    // Collection<TableBuffer>     — buffers table définis
```

---

### APIs `Variable` (`org.prorefactor.treeparser.symbols.Variable`)

```kotlin
variable.name
variable.dataType                   // DataType enum : INTEGER, CHARACTER, LOGICAL...
variable.getDefineNode()            // JPNode → position dans le source
variable.getDefineNode().token.line // ligne (1-based → convertir en 0-based pour IntelliJ)
variable.getDefineNode().token.charPositionInLine
```

---

### APIs `Routine` (`org.prorefactor.treeparser.symbols.Routine`)

```kotlin
routine.name
routine.ideSignature                // "PROCEDURE foo(INPUT x AS INTEGER)" — pour la doc hover
routine.signature                   // Signature courte
routine.parameters                  // List<Parameter> avec nom et type
routine.getDefineNode()             // JPNode → position de définition
```

---

### APIs `JPNode` (`org.prorefactor.core.JPNode`)

```kotlin
node.token                          // Token ANTLR4 : line (1-based), charPositionInLine, text
node.getSymbol()                    // Symbol RSSW résolu — null si non référence
node.firstChild                     // Navigation : firstChild, nextSibling, parent
node.query(ABLNodeType.DEFINE)      // List<JPNode> — tous les nœuds d'un type dans le sous-arbre
node.walk(ICallback)                // Traversée complète avec callback
```

---

### Création de `IProparseEnvironment`

```kotlin
// Minimal (syntaxe seule, pas de résolution d'includes)
val settings = ProparseSettings("")
settings.setCustomProversion("12.2.0")
val env: IProparseEnvironment = object : RefactorSession(settings, Schema()) {}

// Avec PROPATH (résolution d'includes {file.i})
val settings = ProparseSettings(propath.joinToString(",") { it.toString() })
val env: IProparseEnvironment = object : RefactorSession(settings, Schema()) {
    override fun findFile3(fileName: String?): File? =
        super.findFile3(fileName) ?: dummyFile
}
```

---

### Chargement du schéma DB (`.df`) — TODO

```kotlin
// À implémenter dans OpenEdgeProjectService
val schema = Schema()
// Lire le .df depuis databases[].schemaFile dans openedge-project.json
schema.createTable("sports2020", "Customer", listOf("CustNum", "Name", "CreditLimit"))
val env = RefactorSession(ProparseSettings(propath), schema)
// Débloque : complétion tables/champs, validation FIND/FOR EACH
```

---

## Architecture des services

### `AblProjectAnalysisService` (project-level, cache central)

```
Document change
    → AblProjectAnalysisService.invalidate(file)
    → on next access : AblParserFacade.parse(file)   [Niveau 1, synchrone ou background]
    →                  AblParserFacade.analyze(file)  [Niveau 2, toujours background]
    → résultats cachés par VirtualFile + modificationStamp
```

### `OpenEdgeProjectService` (project-level)

Lit `openedge-project.json`. Expose :
- `version` → `ProparseSettings.setCustomProversion()`
- `dlcPath` + `propath` → `IProparseEnvironment` pour la résolution d'includes
- `databases[].schemaFile` → **TODO** alimenter `Schema`

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

### 🟢 Migration core/ — TERMINÉE

| Fichier | Action | État |
|---|---|---|
| `AblParserFacade.kt` | Seul point d'instanciation `ParseUnit`/`ABLLexer`/`Proparse` | ✅ |
| `AblParseResult.kt` | Wrapper `ParseUnit` — expose `.topNode`, `.syntaxErrors`, `.queryNodes()` | ✅ |
| `AblSemanticResult.kt` | Référence directe aux objets RSSW (`JPNode`, `TreeParserSymbolScope`) | ✅ rien à faire |
| `AblSymbolCollector.kt` | `collectFromScope()` via `TreeParserSymbolScope` ; `AblSymbolVisitor` via `ProparseBaseVisitor` | ✅ |
| `AblSymbolIndex.kt` | Alimenté depuis `Variable`, `TableBuffer` via `collectFromScope` | ✅ (`ITypeInfo` = TODO OO) |
| `AblProparseKeywords.kt` | `ABLNodeType.values().filter { it.isKeyword }` | ✅ |

**Décision sur `AblSymbolVisitor` :** il étend `ProparseBaseVisitor` — le visiteur ANTLR4
**auto-généré par RSSW**. Les contextes typés (`ctx.newIdentifier()`, `ctx.datatype()`) sont
l'API proparse publique. Ce n'est pas un walk manuel — c'est le chemin synchrone rapide (avant
`treeParser01`). `collectFromScope()` enrichit les symboles après `treeParser01()`.
Les deux chemins sont intentionnels et complémentaires.

**Règle absolue :** `AblParserFacade` est le **seul** endroit du codebase qui instancie
`ParseUnit`, `ABLLexer` ou `Proparse`. Tous les autres fichiers reçoivent `AblParseResult`
ou `AblSemanticResult`. Ne jamais appeler ces classes directement ailleurs.

---

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
| 🟠 | Complétion des paramètres de procédure/fonction | 📋 | `AblCompletionContributor.kt` |
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
| 🟡 | Navigate to Overriding Methods | 📋 | nouveau |

### Hints et annotations inline

| Priorité | Feature | État | Fichier clé |
|---|---|---|---|
| 🟠 | Inlay hints de type sur les variables (`DEFINE VARIABLE x` → hint `: INTEGER`) | ✅ | `AblTypeInlayHintsProvider.kt` |
| 🟠 | Inlay hints sur les paramètres d'appel (`foo(/* INPUT */ 42, /* OUTPUT */ result)`) | ✅ | `AblParameterInlayHintsProvider.kt` |
| 🟠 | Inlay hints de valeur de retour | 📋 | nouveau |
| 🟡 | Code Vision (nombre d'usages au-dessus de chaque déclaration) | 📋 | nouveau |

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
| 🟠 | Code formatter complet (indentation, espaces, casse des mots-clés) | 📋 | nouveau |
| 🟡 | Import optimizer (trier/nettoyer les `USING` dans les classes OO) | ✅ | `AblOptimizeUsingsIntention.kt` |

### Debugger

> Package `debug/` existant : `AblDebugProcess`, `AblDebugConnection`, `AblDebugConfigurationType`.

| Priorité | Feature | État | Fichier clé |
|---|---|---|---|
| 🟠 | Breakpoints : ligne, conditionnel (`WHEN myVar > 0`), exception (`CATCH`) | 📋 | `AblDebugProcess.kt` |
| 🟠 | Variables watch : affichage des variables locales dans la fenêtre Debugger | 📋 | `AblDebugProcess.kt` |
| 🟠 | Step Over / Step Into / Step Out complets | 📋 | `AblDebugProcess.kt` |
| 🟠 | Call Stack avec navigation vers le source | 📋 | `AblDebugProcess.kt` |
| 🟠 | Attach to process (`-debugReady`) | 📋 | `AblDebugConnection.kt` |
| 🟠 | Remote debug via socket (AppServer distant) | 📋 | `AblDebugConnection.kt` |
| 🟡 | Evaluate Expression (expression ABL à la volée pendant le debug) | 📋 | `AblDebugProcess.kt` |
| 🟡 | Conditional Breakpoints sur les champs de tables (`WHEN Customer.Balance > 1000`) | 📋 | `AblDebugProcess.kt` |
| 🟢 | Hot Swap (rechargement de code à chaud pendant une session debug) | 📋 | `AblDebugProcess.kt` |
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
| 🟠 | Vue Profiler : temps CPU, nombre d'appels, par procédure/méthode | 📋 | `AblProfilerParser.kt` |
| 🟠 | Coverage : lignes couvertes/non couvertes dans la gouttière | 📋 | `AblCoverageService.kt` |
| 🟠 | Hot Spots : mise en évidence des lignes coûteuses dans l'éditeur | 📋 | nouveau |
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
| 🟡 | Sticky lines : signature de la procédure courante en haut de l'éditeur | 📋 | nouveau |
| 🟡 | Rainbow brackets : coloration des blocs `DO/END` imbriqués | 📋 | nouveau |
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

### 1. Tests lexer

```kotlin
class AblLexerTest : LexerTestCase() {
    override fun getDirPath() = "src/test/testData/lexer"
    override fun createLexer() = AblLexerAdapter()

    fun testSimpleProcedure() = doFileTest("simple_procedure.p")
    fun testPreprocessorDefine() = doTest("&IF DEFINED(DEBUG) &THEN MESSAGE 'x'. &ENDIF", "")
}
```

### 2. Tests parser

```kotlin
// Premier run avec -Dupdate=true pour générer les .txt attendus, puis committer.
class AblParserTest : ParsingTestCase("parser/parsing", "p", AblParserDefinition()) {
    override fun getTestDataPath() = "src/test/testData"
    override fun includeRanges() = true

    fun testProcedureDefinition() = doTest(true)
    fun testClassWithInheritance() = doTest(true)
    fun testSyntaxError() = doTest(false)
}
```

### 3. Tests highlighting

```kotlin
class AblHighlightingTest : BasePlatformTestCase() {
    override fun getTestDataPath() = "src/test/testData/highlighting"

    // Le fichier contient : <info descr="KEYWORD">DEFINE</info> VARIABLE x ...
    fun testKeywordHighlighting() = myFixture.testHighlighting(true, false, false, "keywords.p")

    fun testNoKeywordInsideComment() {
        myFixture.configureByText(AblFileType, "/* DEFINE VARIABLE */")
        myFixture.checkHighlighting()
    }
}
```

### 4. Tests completion

```kotlin
class AblCompletionContributorTest : BasePlatformTestCase() {

    fun testKeywordCompletion() {
        myFixture.configureByText(AblFileType, "DEF<caret>")
        val lookups = myFixture.completeBasic()
        assertTrue(lookups?.any { it.lookupString.uppercase() == "DEFINE" } == true)
    }

    fun testVariableCompletion() {
        myFixture.configureByText(AblFileType, """
            DEFINE VARIABLE myVar AS INTEGER NO-UNDO.
            myV<caret>
        """.trimIndent())
        assertTrue(myFixture.completeBasic()?.any { it.lookupString == "myVar" } == true)
    }

    fun testNoCompletionInComment() {
        myFixture.configureByText(AblFileType, "/* DEF<caret> */")
        assertTrue(myFixture.completeBasic().isNullOrEmpty())
    }
}
```

### 5. Tests inspections

Pattern à répliquer pour chacune des 9 inspections :

```kotlin
class AblNoUndoInspectionTest : BasePlatformTestCase() {
    override fun setUp() { super.setUp(); myFixture.enableInspections(AblNoUndoInspection()) }

    // NoUndo.p : DEFINE VARIABLE <warning descr="Missing NO-UNDO">x</warning> AS INTEGER.
    fun testWarningOnMissingNoUndo() = myFixture.testHighlighting("NoUndo.p")

    fun testNoWarningWhenPresent() {
        myFixture.configureByText(AblFileType, "DEFINE VARIABLE x AS INTEGER NO-UNDO.")
        myFixture.checkHighlighting()
    }

    fun testQuickFix() {
        myFixture.configureByText(AblFileType, "DEFINE VARIABLE <caret>x AS INTEGER.")
        myFixture.launchAction(myFixture.findSingleIntention("Add NO-UNDO"))
        myFixture.checkResult("DEFINE VARIABLE x AS INTEGER NO-UNDO.")
    }
}
```

| Test class | Inspection |
|---|---|
| `AblNoUndoInspectionTest` | `AblNoUndoInspection` |
| `AblEmptyCatchInspectionTest` | `AblEmptyCatchInspection` |
| `AblUnusedVariableInspectionTest` | `AblUnusedVariableInspection` |
| `AblFindNoLockInspectionTest` | `AblFindNoLockInspection` |
| `AblNoErrorWithoutCheckInspectionTest` | `AblNoErrorWithoutCheckInspection` |
| `AblMissingSchemaPrefixInspectionTest` | `AblMissingSchemaPrefixInspection` |
| `AblFortranOperatorsInspectionTest` | `AblFortranOperatorsInspection` |
| `AblStringConcatInWhereInspectionTest` | `AblStringConcatInWhereInspection` |

### 6. Tests navigation

```kotlin
class AblNavigationTest : BasePlatformTestCase() {

    fun testGotoDeclaration() {
        myFixture.configureByText(AblFileType, """
            DEFINE VARIABLE myVar AS INTEGER NO-UNDO.
            MESSAGE myV<caret>ar.
        """.trimIndent())
        val targets = GotoDeclarationAction.findAllTargetElements(
            project, myFixture.editor, myFixture.caretOffset)
        assertEquals(1, targets.size)
    }

    fun testFindUsages() {
        myFixture.configureByText(AblFileType, """
            DEFINE VARIABLE myVar AS INTEGER NO-UNDO.
            myVar = 1.
            MESSAGE myVar.
        """.trimIndent())
        val usages = myFixture.findUsages(myFixture.elementAtCaret)
        assertEquals(2, usages.size)
    }
}
```

### 7. Tests rename

```kotlin
class AblRenameTest : BasePlatformTestCase() {

    fun testRenameVariable() {
        myFixture.configureByText(AblFileType, """
            DEFINE VARIABLE my<caret>Var AS INTEGER NO-UNDO.
            myVar = 42.
        """.trimIndent())
        myFixture.renameElementAtCaret("renamedVar")
        myFixture.checkResult("""
            DEFINE VARIABLE renamedVar AS INTEGER NO-UNDO.
            renamedVar = 42.
        """.trimIndent())
    }
}
```

### 8. Tests folding

```kotlin
// Étendre AblFoldingBuilderTest.kt existant
class AblFoldingBuilderTest : BasePlatformTestCase() {
    fun testProcedureFolding() = myFixture.testFolding("src/test/testData/folding/procedures.p")
    fun testClassFolding()     = myFixture.testFolding("src/test/testData/folding/class.cls")
}
```

### 9. Tests structure view

```kotlin
class AblStructureViewTest : BasePlatformTestCase() {

    fun testProceduresAppearInStructure() {
        myFixture.configureByText(AblFileType, """
            PROCEDURE foo: END PROCEDURE.
            PROCEDURE bar: END PROCEDURE.
        """.trimIndent())
        myFixture.testStructureView { model ->
            val names = model.root.children.map { it.presentation.presentableText }
            assertContainsElements(names, "foo", "bar")
        }
    }
}
```

### 10. Tests core (JUnit pur, sans plateforme)

```kotlin
class AblParserFacadeTest {
    private val facade = AblParserFacade(OpenEdgeProjectSettings.default())

    @Test fun `parse procedure returns top node`() {
        val result = facade.parseText("PROCEDURE foo: END PROCEDURE.")
        assertNotNull(result.topNode)
    }

    @Test fun `syntax error captured without throw`() {
        val result = facade.parseText("DEFINE VARIABLE x AS .")
        assertTrue(result.syntaxErrors.isNotEmpty())
    }

    @Test fun `keyword list covers core ABL keywords`() {
        val kws = ABLNodeType.values().filter { it.isKeyword() }.map { it.name }
        assertContainsElements(kws, "DEFINE", "PROCEDURE", "FUNCTION", "CLASS", "IF", "FOR")
        assertTrue(kws.size > 100)
    }

    @Test fun `symbol collector finds variables`() {
        val result = facade.parseText("""
            DEFINE VARIABLE myVar AS INTEGER NO-UNDO.
            DEFINE VARIABLE otherVar AS CHARACTER NO-UNDO.
        """.trimIndent())
        val names = AblSymbolCollector.collect(result).map { it.name }
        assertContainsElements(names, "myVar", "otherVar")
    }
}
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
