# CLAUDE.md — ABL IntelliJ Plugin

Fichier de contexte pour Claude Code. Décrit l'architecture réelle, les commandes,
les APIs RSSW, les conventions, les bugs connus et le pipeline agent Paperclip.

---

## Vue d'ensemble

Plugin IntelliJ IDEA **100 % natif** pour **Progress OpenEdge ABL**.
Pas de LSP. Tout passe par les extension points IntelliJ + la bibliothèque
**proparse** (Riverside Software / RSSW) embarquée directement.

- **Plugin version :** 1.0.0
- **Cible :** IntelliJ 2023.2+ (`sinceBuild=232`)
- **Testé sur :** 2023.2, 2023.3, 2024.1
- **JVM :** 17, Kotlin 2.0.0
- **proparse :** 3.7.2
- **Repo :** `https://github.com/Loe159/abl-plugin-intellij`
- **Local :** `/home/aiagent/workspace/abl-plugin-intellij`
- **Worktrees :** `/home/aiagent/workspace/abl-worktrees/`

---

## Commandes essentielles

```bash
./gradlew compileKotlin --no-daemon   # vérification rapide (~30s)
./gradlew test --no-daemon            # tests (~60s)
./gradlew buildPlugin --no-daemon     # → build/distributions/ABL-Language-Support-1.0.0.zip
./gradlew verifyPlugin --no-daemon    # compatibilité multi-versions
./gradlew runIde --no-daemon          # IDE sandbox
```

---

## Architecture

```
src/main/kotlin/com/ablls/plugin/
├── core/
│   ├── AblParserFacade.kt           POINT D'ENTRÉE PARSING
│   │                                parse()   → AblParseResult  (syntaxique, rapide)
│   │                                analyze() → AblSemanticResult (sémantique, background)
│   ├── AblProjectAnalysisService.kt Service @Service(PROJECT) : cache + index + PROPATH
│   │                                analyzeFile()        → parse rapide + update index
│   │                                analyzeFileSemantic() → treeParser01 complet
│   │                                analyzeSemanticAsync() → lancement background
│   │                                buildIndexInBackground() → indexation initiale
│   ├── AblSymbolCollector.kt        Deux sources : ProparseBaseVisitor (AST) + TreeParserSymbolScope
│   ├── AblSymbolIndex.kt            findByName(), findByPrefix(), getSymbolsForFile()
│   ├── AblSymbol.kt                 DTO : nom, Kind, URI, Range, dataType, doc
│   ├── AblSemanticResult.kt         DTO : JPNode + TreeParserSymbolScope
│   ├── AblParseResult.kt            DTO : ProgramContext + tokens + erreurs
│   ├── SyntaxError.kt               DTO erreur (ligne 0-based, colonne, message, URI)
│   ├── AblKeywordList.kt            ~200 mots-clés ABL statiques
│   └── AblBuiltinDocs.kt            ~92 fonctions built-in documentées
│
├── parser/
│   ├── AblLexerAdapter.kt           PONT CENTRAL : scanner de caractères → IntelliJ Lexer
│   │                                NE PAS utiliser ABLLexer ici (trop lourd pour streaming)
│   ├── AblParserDefinition.kt       PSI entry point : createLexer, createParser
│   ├── AblPsiParser.kt              AblFile (PsiFileBase), arbre plat
│   └── AblTokenTypes.kt             IElementType pour ~10 catégories de tokens
│
├── highlight/
│   ├── AblSyntaxHighlighter.kt      AblTokenType → TextAttributesKey
│   ├── AblHighlighterFactory.kt
│   ├── AblColorSettingsPage.kt      Settings → Editor → Color Scheme → ABL
│   ├── AblFoldingBuilder.kt         DO..END, PROCEDURE..END, CLASS..END
│   ├── AblBracketMatcher.kt
│   └── AblCommenter.kt              // et /* */
│
├── annotator/
│   ├── AblAnnotator.kt              ExternalAnnotator : squiggles en temps réel
│   │                                collectInformation (EDT) → doAnnotate (background) → apply (EDT)
│   ├── AblCompilerWarningAnnotator.kt  Warnings issus du fichier .warnings RSSW
│   └── AblWarningFileListener.kt    Détecte les changements de .warnings
│
├── completion/
│   ├── AblCompletionContributor.kt  3 sources : scope sémantique > index projet > mots-clés
│   ├── AblAutoCaseTypedHandler.kt   Auto-casing mots-clés à la frappe
│   └── AblTemplateContextType.kt    Contexte live templates
│
├── documentation/
│   └── AblDocumentationProvider.kt  Hover : built-ins + symboles utilisateur (/* */ précédant)
│
├── navigation/
│   ├── AblGotoDeclarationHandler.kt Go to Declaration (Ctrl+B) : symboles + {include.i}
│   └── AblFindUsagesProvider.kt     Find Usages (textuel — TODO : sémantique via JPNode)
│
├── inspections/
│   ├── AblInspectionHelper.kt       toRange(doc, line1based, col, len) → TextRange
│   ├── AblNoUndoInspection.kt       DEFINE VARIABLE/TEMP-TABLE sans NO-UNDO + Quick Fix
│   ├── AblFindNoLockInspection.kt   FIND sans SHARE-LOCK/NO-LOCK/EXCLUSIVE-LOCK
│   ├── AblEmptyCatchInspection.kt   Bloc CATCH vide (scan du TokenStream)
│   ├── AblUnusedVariableInspection.kt  Variable définie mais jamais lue (sémantique + fallback)
│   ├── AblFortranOperatorsInspection.kt  Opérateurs Fortran (EQ, NE, GT...) au lieu de =,<>,>
│   ├── AblMissingSchemaPrefixInspection.kt  Champ sans préfixe table
│   ├── AblNoErrorWithoutCheckInspection.kt  NO-ERROR sans vérification d'ERROR-STATUS
│   └── AblStringConcatInWhereInspection.kt  Concat de chaîne dans clause WHERE
│
├── refactor/
│   └── AblRenameHandler.kt          Rename (textuel — TODO : sémantique via JPNode)
│
├── structure/
│   └── AblStructureViewFactory.kt   Alt+7 : hiérarchie depuis AblSymbolIndex
│
├── project/
│   ├── OpenEdgeProjectService.kt    Lit openedge-project.json (@Service PROJECT)
│   └── AblProjectListener.kt        Recharge config quand le fichier change
│
├── run/
│   ├── AblRunConfigurationType.kt   Run .p via _progres/prowin
│   ├── AblRunConfigurationProducer.kt
│   ├── AblProgramRunner.kt          Lance + attache le debug
│   └── AblConsoleFilterProvider.kt  Filtre les erreurs OE dans la console
│
├── debug/
│   ├── AblDebugConnection.kt        Client TCP vers OE (-debugReady PORT)
│   │                                Protocole textuel non documenté (inspiré vscode-abl)
│   │                                → À valider via Wireshark contre PDSOE
│   ├── AblDebugProcess.kt           XDebugProcess : breakpoints, step, eval
│   ├── AblDebugSupport.kt           Enregistrement du type de debug
│   └── AblDebugConfigurationType.kt
│
├── coverage/
│   ├── AblProfilerParser.kt         Parse les fichiers .prof RSSW
│   ├── AblCoverageService.kt        Coloration des lignes couvertes
│   └── LoadCoverageAction.kt
│
├── duplication/
│   ├── AblDuplicationDetector.kt    Détection de blocs dupliqués (hash de tokens normalisés)
│   ├── AblTokenNormalizer.kt        Normalisation des tokens pour la comparaison
│   ├── AblDuplicatesPanel.kt        UI tool window
│   └── AblDuplicatesToolWindowFactory.kt
│
├── xref/
│   ├── XrefParser.kt                Parse les fichiers .xref RSSW
│   ├── XrefModel.kt                 Modèle de données XREF
│   ├── XrefPanel.kt / XrefToolWindowFactory.kt / ShowXrefAction.kt
│
├── startup/
│   └── AblStartupActivity.kt        Post-startup : updateEnvironment + buildIndexInBackground
│
├── language/
│   ├── AblLanguage.kt               Singleton Language("ABL")
│   ├── AblFileType.kt               .p .cls .i .w .t → ABL
│   └── AblIcons.kt                  SVG : losange vert (OpenEdge branding)
│
└── actions/
    └── AblActions.kt                ReindexProjectAction, OpenProjectConfigAction
```

---

## Dépendances critiques

### Modules RSSW disponibles (sonar-openedge)

Source : `https://github.com/Riverside-Software/sonar-openedge` — cloné localement en `/home/aiagent/workspace/sonar-openedge`.

| Module | Artefact | État dans le plugin | Utilité |
|--------|----------|---------------------|---------|
| `proparse` | `eu.rssw.openedge.parsers:proparse:3.7.2` | ✅ Utilisé | Parser ABL, AST, symboles, ABLNodeType |
| `profiler-parser` | `eu.rssw.openedge.parsers:profiler-parser:3.7.2` | ✅ Utilisé | Fichiers `.prof` (couverture) |
| `database-parser` | `eu.rssw.openedge.parsers:database-parser:3.7.2` | ❌ Non ajouté | **Parse les `.df`** → `DumpFileUtils.getDatabaseDescription(path)` → tables+champs pour complétion DB |
| `rcode-reader` | `eu.rssw.openedge.parsers:rcode-reader:3.7.2` | ❌ Non ajouté | Lit les `.r` compilés → symboles sans source |
| `listing-parser` | `eu.rssw.openedge.parsers:listing-parser:3.7.2` | ❌ Non ajouté | Parse les listings de compilation OE |

### Dépendances actuelles build.gradle.kts

```kotlin
// NE PAS changer version sans vérifier sonar-openedge releases
implementation("eu.rssw.openedge.parsers:proparse:3.7.2") {
    exclude(group = "org.sonarsource.sonarqube")
    exclude(group = "org.sonarsource.analyzer-commons")
}
implementation("eu.rssw.openedge.parsers:profiler-parser:3.7.2") {
    exclude(group = "org.sonarsource.sonarqube")
    exclude(group = "org.sonarsource.analyzer-commons")
}
// Pour activer .df schema loading, ajouter :
// implementation("eu.rssw.openedge.parsers:database-parser:3.7.2") { ... }
// Maven : https://dl.cloudsmith.io/public/riverside-software/openedge-dev/maven/
// Releases : https://github.com/Riverside-Software/sonar-openedge/releases
```

---

## APIs RSSW disponibles

### ABLNodeType — source de vérité pour les mots-clés

`org.prorefactor.core.ABLNodeType` est l'enum complet (~900 tokens) de tous les tokens ABL.
**Ne jamais coder en dur une liste de mots-clés — utiliser ABLNodeType.**

```kotlin
// Énumérer tous les mots-clés (formes complètes + abrégées)
val allKeywords: Set<String> = buildSet {
    for (type in ABLNodeType.values()) {
        if (!type.isKeyword()) continue
        val text = type.getText() ?: continue
        if (text.isNotBlank()) add(text.uppercase())
        type.alternate?.let  { alt -> if (alt.isNotBlank()) add(alt.uppercase()) }
        type.alternate2?.let { alt -> if (alt.isNotBlank()) add(alt.uppercase()) }
    }
}

// Lookup par texte (case-insensitive, gère les abréviations)
val nodeType: ABLNodeType? = ABLNodeType.getLiteral("excl")  // → EXCLUSIVELOCK
val isKw: Boolean = nodeType?.isKeyword() ?: false
val isReserved: Boolean = nodeType?.isReservedKeyword() ?: false

// Classification dans le lexer
val type = ABLNodeType.getLiteral(word.lowercase())
return if (type != null && type.isKeyword()) AblTokenTypes.KEYWORD else AblTokenTypes.IDENTIFIER
```

Méthodes utiles : `getText()`, `getAlternate()`, `getAlternate2()`, `isKeyword()`, `isReservedKeyword()`,
`isNoArgFunc()`, `isOptionalArgFunction()`, `isValidDatatype()`, `isSystemHandle()`.

### database-parser — chargement des schémas .df

```kotlin
// Dépendance : eu.rssw.openedge.parsers:database-parser:3.7.2
import eu.rssw.antlr.database.DumpFileUtils
import eu.rssw.antlr.database.objects.DatabaseDescription

val desc: DatabaseDescription = DumpFileUtils.getDatabaseDescription(Path.of("sports2020.df"))
for (table in desc.tables) {
    val tableName = table.name
    for (field in table.fields) {
        val fieldName = field.name
        val dataType = field.dataType
    }
}
```

### Niveau 1 — Parsing syntaxique (AblParserFacade.parse)

```kotlin
val ablLexer  = ABLLexer(session, charset, bytes, uri, false)
val lex       = Lexer(ablLexer, bytes, uri)
val postLexer = PostLexer(ablLexer, lex)
val tokenList = TokenList(postLexer)
val tokens    = CommonTokenStream(tokenList)
val parser    = Proparse(tokens)
parser.initialize(session, null)
val tree: Proparse.ProgramContext = parser.program()
// → visitable via ProparseBaseVisitor
// → tokens.get(i) pour le hidden channel (commentaires)
```

### Niveau 2 — Analyse sémantique (AblParserFacade.analyze)

```kotlin
val pu = object : ParseUnit(content, uri, session) {}
pu.parse()
pu.treeParser01()   // ← résout symboles, types, références
// getRootScope() peut ne pas être public → reflection :
val scope = runCatching {
    pu.javaClass.getMethod("getRootScope").invoke(pu) as? TreeParserSymbolScope
}.getOrNull()
val topNode = runCatching {
    pu.javaClass.getMethod("getTopNode").invoke(pu) as? JPNode
}.getOrNull()
```

### APIs TreeParserSymbolScope

```kotlin
scope.variables      // List<Variable>
scope.routines       // List<Routine>
scope.childScopes    // List<TreeParserSymbolScope>
// getBufferList() ou getBuffers() selon version → reflection
```

### APIs Variable / Routine / JPNode

```kotlin
variable.name
variable.dataType               // DataType enum
variable.javaClass.getMethod("getDefineNode").invoke(variable) as? JPNode

routine.name
routine.ideSignature            // "PROCEDURE foo(INPUT x AS INTEGER)"
routine.parameters

node.token.line                 // 1-based → IntelliJ : line - 1
node.token.charPositionInLine   // 0-based (pas de conversion)
node.getSymbol()                // Symbol résolu (null si pas une référence)
```

### IProparseEnvironment

```kotlin
// Minimal (syntaxe seule)
val settings = ProparseSettings("")
settings.setCustomProversion("12.2.0")
val env = object : RefactorSession(settings, Schema()) {
    override fun findFile3(fileName: String?) = super.findFile3(fileName) ?: dummyIncludeFile
}

// Avec PROPATH
val settings = ProparseSettings(propath.joinToString(",") { it.toString() })
settings.setCustomProversion(oeVersion.ifBlank { "12.2.0" })
```

---

## Conventions de code

### Thread safety

- Analyses sémantiques (`treeParser01`) → `executeOnPooledThread`
- Updates UI → `invokeLater` depuis background thread
- **Jamais bloquer l'EDT** — `doAnnotate()` est déjà sur background thread (ExternalAnnotator)
- `analyzeFileSemantic()` est bloquant par conception — ne l'appeler que depuis background

### Positions

```kotlin
// proparse : line 1-based, col 0-based
// IntelliJ : tout 0-based
val intellijLine = proparseLine - 1   // TOUJOURS
val intellijCol  = proparseCol        // pas de conversion
```

### Services

```kotlin
// Injection via service() — jamais instancier directement
val service = project.service<AblProjectAnalysisService>()
val config  = project.service<OpenEdgeProjectService>().config
```

### Loggers

```kotlin
// Logger au niveau companion object (statique), pas instance
companion object {
    private val LOG = Logger.getInstance(MyClass::class.java)
}
```

---

## Gotchas critiques (ne jamais violer)

### 1. treeParser01() lève des exceptions sur du code invalide

```kotlin
// CORRECT — toujours wrappé
try {
    pu.treeParser01()
} catch (e: Exception) {
    LOG.warn("treeParser01 failed: ${e.message}")
    // fallback sur résultat syntaxique
}
```

### 2. getRootScope() n'est pas toujours public

Utiliser le pattern reflection avec `runCatching` (voir AblParserFacade.analyzeInternal).

### 3. Le `.` ABL est ambigu

`.` = terminateur d'instruction + séparateur de package + séparateur de champ.
proparse gère ça nativement — ne pas essayer de le tokeniser côté plugin.

### 4. PROPATH requis pour résoudre les `{include.i}`

Sans PROPATH, chaque include non résolu génère des dizaines d'erreurs en cascade.
→ Limiter à 20 erreurs affichées + message d'avertissement (voir AblAnnotator).

### 5. Vérifier les noms de règles après un update proparse

```bash
jar tf ~/.m2/repository/eu/rssw/openedge/parsers/proparse/*/proparse-*.jar \
    | grep "ABLParserBaseVisitor"
```

### 6. StartupActivity est dépréciée (IntelliJ 2023.1+)

`AblStartupActivity` implémente `StartupActivity.DumbAware` (dépréciée).
À migrer vers `ProjectActivity` (coroutine-based) pour les versions cibles futures.

---

## Bugs connus (à corriger)

| Fichier | Ligne | Sévérité | Description |
|---------|-------|----------|-------------|
| ~~`AblUnusedVariableInspection.kt`~~ | ~~151~~ | ~~**Bug**~~ | ~~`'\$name'` → affiche littéralement `$name`~~ — **CORRIGÉ** |
| ~~`AblKeywordList.kt`~~ | — | ~~RSSW~~ | ~~130 mots-clés codés en dur au lieu d'utiliser `ABLNodeType`~~ — **CORRIGÉ** (ABLNodeType 900+) |
| ~~`AblLexerAdapter.kt`~~ | ~~238~~ | ~~**Bug**~~ | ~~`else -> KEYWORD` colore tous les identifiants utilisateur en mot-clé~~ — **CORRIGÉ** (ABLNodeType.getLiteral) |
| `AblNoUndoInspection.kt` | 24+93 | Qualité | `isStatementEnd()` dupliquée dans la classe principale et dans `AddNoUndoFix`. Extraire dans `AblInspectionHelper`. |
| `AblParserFacade.kt` | 37 | Qualité | `LOG` déclaré comme variable d'instance — déplacer dans `companion object`. |
| `AblProjectAnalysisService.kt` | 184 | Qualité | `catch (_: Exception) {}` silencieux dans `buildIndexInBackground()` — ajouter au moins `LOG.debug(...)`. |
| `AblUnusedVariableInspection.kt` | 62 | Perf | `analyzeFile()` appelé à chaque itération `forEach` — sortir de la boucle (le cache le masque mais l'intention est confuse). |
| `AblCompletionContributor.kt` | 65 | Cohérence | Pas de déduplication entre Source 1 (scope sémantique) et Source 2 (index) — peut afficher le même symbole deux fois. |

---

## Fonctionnalités

| Fonctionnalité | État | Fichier clé |
|----------------|------|-------------|
| Coloration syntaxique | ✅ | `AblLexerAdapter.kt` |
| Folding DO/END, PROC/END... | ✅ | `AblFoldingBuilder.kt` |
| Commenter (// et /* */) | ✅ | `AblCommenter.kt` |
| Live Templates | ✅ | `liveTemplates/abl.xml` |
| Auto-casing mots-clés | ✅ | `AblAutoCaseTypedHandler.kt` |
| Diagnostics syntaxiques | ✅ | `AblAnnotator.kt` |
| Warnings compilateur | ✅ | `AblCompilerWarningAnnotator.kt` |
| Complétion mots-clés | ✅ | `AblCompletionContributor.kt` |
| Complétion symboles projet | ✅ | `AblCompletionContributor.kt` |
| Complétion sémantique (typée) | ✅ | `AblCompletionContributor.kt` |
| Documentation hover built-ins | ✅ (~92) | `AblBuiltinDocs.kt` |
| Documentation hover symboles | ✅ | `AblDocumentationProvider.kt` |
| Go to Declaration | ✅ | `AblGotoDeclarationHandler.kt` |
| Go to Include ({f.i}) | ✅ | `AblGotoDeclarationHandler.kt` |
| Structure View (Alt+7) | ✅ | `AblStructureViewFactory.kt` |
| Inspection NO-UNDO + Quick Fix | ✅ | `AblNoUndoInspection.kt` |
| Inspection FIND sans lock | ✅ | `AblFindNoLockInspection.kt` |
| Inspection CATCH vide | ✅ | `AblEmptyCatchInspection.kt` |
| Inspection variable non utilisée | ✅ | `AblUnusedVariableInspection.kt` |
| Inspection opérateurs Fortran | ✅ | `AblFortranOperatorsInspection.kt` |
| Inspection schema prefix | ✅ | `AblMissingSchemaPrefixInspection.kt` |
| Inspection NO-ERROR sans check | ✅ | `AblNoErrorWithoutCheckInspection.kt` |
| Inspection concat dans WHERE | ✅ | `AblStringConcatInWhereInspection.kt` |
| Run Configuration (.p) | ✅ | `AblRunConfigurationType.kt` |
| Debug ABL (-debugReady) | ✅ expérimental | `AblDebugConnection.kt` |
| Coverage (.prof) | ✅ | `AblProfilerParser.kt` |
| XREF viewer (.xref) | ✅ | `XrefParser.kt` |
| Duplication detector | ✅ | `AblDuplicationDetector.kt` |
| openedge-project.json | ✅ | `OpenEdgeProjectService.kt` |
| Find Usages (Alt+F7) | 🔧 textuel | `AblFindUsagesProvider.kt` |
| Rename (Shift+F6) | 🔧 textuel | `AblRenameHandler.kt` |
| Complétion tables/champs DB | 🔧 TODO | — |
| Chargement schéma .df | 🔧 TODO | `OpenEdgeProjectService.kt` |
| Find References sémantique | 🔧 TODO | `AblFindUsagesProvider.kt` |
| StartupActivity → ProjectActivity | 🔧 TODO | `AblStartupActivity.kt` |

---

## Fichier openedge-project.json

```json
{
  "name": "Mon Projet",
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

Champs reconnus par `OpenEdgeProjectService` :
- `version` → `ProparseSettings.setCustomProversion()`
- `dlcPath` + `propath` → `IProparseEnvironment` (résolution includes)
- `databases[].schemaFile` → **TODO** alimenter `Schema` pour complétion DB

---

## Pipeline Agent Paperclip

Le projet est géré par une équipe d'agents autonomes orchestrés via Paperclip.

### Constantes

```
Company ID : 01420bc5-12ec-4b56-bf6a-2d420be0b2d5
Project ID : cefe7156-21f5-4e8c-bf50-ee9101ccad2c
```

### Agents (fichiers dans `agents/`)

| Agent | Fichier | Rôle |
|-------|---------|------|
| CEO | `agents/ceo.md` | Triage + orchestration pipeline |
| PM | `agents/pm.md` | Spécification features |
| Engineer | `agents/engineer.md` | Implémentation code |
| Test Writer | `agents/test-writer.md` | Écriture des tests |
| Reviewer | `agents/reviewer.md` | Revue qualité + conventions |
| PR Agent | `agents/pr-agent.md` | Ouverture PR GitHub |

### Pipeline par issue

```
CEO (triage) → Engineer → Test Writer → Reviewer → PR Agent
               ←blocked←   ←blocked←    ←blocked←
```

### Skills disponibles pour les agents

- `skills/abl-dev-context/SKILL.md` — référence architecture + conventions + gotchas
  **⚠️ PONT CRITIQUE** : seul lien entre le code plugin et le pipeline agent.
  Le Reviewer l'utilise pour valider la conformité. Si ce skill est désynchronisé
  du code réel, les agents valident du code incorrect sans le savoir.
  → Mettre à jour ce skill à chaque changement de convention ou d'API.

- `skills/graphify-nav/SKILL.md` — navigation du graphe de connaissance

### Conventions commits (pour les agents)

```
feat(scope): description courte

Fixes: SUP-NNN
Co-Authored-By: Paperclip <noreply@paperclip.ing>
```

Scopes : `completion`, `annotator`, `parser`, `inspection`, `navigation`, `refactor`, `debug`, `coverage`, `xref`

### Branches de travail

Format : `agent/<issue-identifier>-<slug>`

---

## Graphify

Ce projet dispose d'un graphe de connaissance dans `graphify-out/`.

- `graphify-out/GRAPH_REPORT.md` — rapport god nodes + communautés
- `graphify-out/graph.html` — visualisation interactive
- `graphify-out/graph.json` — données brutes

**Avant toute question d'architecture** : lire `graphify-out/GRAPH_REPORT.md`.

Mettre à jour après des modifications de code :
```bash
/graphify . --update
```

God nodes actuels (nœuds les plus connectés) :
1. `AblFoldingBuilderTest` — 37 arêtes (tests de folding, forte couverture)
2. `AblSymbolVisitor` — 22 arêtes (collecte de symboles depuis l'AST)
3. `AblDebugConnection` — 16 arêtes (client TCP debug OE)
4. `AblLexerAdapter` — 12 arêtes (pont lexer central)
5. `AblParserFacade` — 12 arêtes (point d'entrée parsing RSSW)

---

## Prochaines étapes prioritaires

1. **Chargement .df** — ajouter `database-parser:3.7.2` en dépendance + `DumpFileUtils.getDatabaseDescription()` dans `OpenEdgeProjectService` → alimenter `Schema` pour complétion tables/champs
2. **Find References sémantique** — parcourir `topNode` post-`treeParser01()` pour `jpNode.getSymbol() === targetSymbol`
3. **Rename sémantique** — baser sur les références JPNode plutôt que la recherche textuelle
4. **Complétion OO** — résoudre le type de l'expression avant `:` pour lister les membres de classe
5. **Migrer StartupActivity** → `ProjectActivity`
6. **isStatementEnd() DRY** — extraire la duplication `AblNoUndoInspection.kt:24+93` dans `AblInspectionHelper`
