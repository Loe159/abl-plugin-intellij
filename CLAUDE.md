# CLAUDE.md — Plugin IntelliJ ABL (natif proparse)

Fichier de contexte pour Claude. Décrit l'architecture réelle, les commandes de build,
les APIs RSSW disponibles et les conventions du projet.

---

## Vue d'ensemble

Plugin IntelliJ IDEA **100 % natif** pour **Progress OpenEdge ABL**.
Pas de LSP server externe. Pas de LSP4IJ. Tout passe par les extension
points IntelliJ + la bibliothèque **proparse** (Riverside Software / RSSW)
embarquée directement dans le plugin.

```
abl-intellij-plugin/     ← Kotlin, Gradle — plugin JetBrains standalone
```

---

## Commandes essentielles

```bash
cd abl-intellij-plugin

# Lancer l'IDE sandbox (développement)
./gradlew runIde

# Construire le .zip distribuable
./gradlew buildPlugin
# → build/distributions/abl-intellij-plugin-1.0.0.zip

# Vérifier la compatibilité multi-versions IntelliJ
./gradlew verifyPlugin

# Tests unitaires
./gradlew test
```

---

## Architecture

```
src/main/kotlin/com/ablls/plugin/
├── language/
│   ├── AblLanguage.kt           Singleton Language("ABL"). Référencé partout.
│   ├── AblFileType.kt           .p .cls .i .w .t → langue ABL.
│   └── AblIcons.kt              Icônes SVG (resources/icons/).
│
├── parser/
│   ├── AblTokenTypes.kt         IElementType pour ~10 catégories de tokens.
│   ├── AblLexerAdapter.kt       PONT CENTRAL : org.prorefactor.proparse.ABLLexer
│   │                            (RSSW) → IntelliJ Lexer API.
│   │                            mapTokenType() : ABLNodeType → AblTokenType.
│   ├── AblParserDefinition.kt   Point d'entrée PSI : createLexer, createParser.
│   └── AblPsiParser.kt          AblFile (PsiFileBase), AblPsiParser (arbre plat).
│
├── highlight/
│   ├── AblSyntaxHighlighter.kt  AblTokenType → TextAttributesKey (couleurs).
│   ├── AblHighlighterFactory.kt Factory pour IntelliJ.
│   ├── AblColorSettingsPage.kt  Settings → Editor → Color Scheme → ABL.
│   ├── AblFoldingBuilder.kt     Folding DO..END, PROCEDURE..END, CLASS..END.
│   ├── AblBracketMatcher.kt     Correspondance parenthèses/crochets.
│   └── AblCommenter.kt          // et /* */ (Ctrl+/).
│
├── core/
│   ├── AblParserFacade.kt       POINT D'ENTRÉE PARSING RSSW.
│   │                            Niveau 1 : parse() → AST Proparse + erreurs.
│   │                            Niveau 2 : analyze() → ParseUnit.treeParser01()
│   │                            (types résolus, signatures, scope complet).
│   ├── AblProjectAnalysisService.kt  Service projet : cache parse + sémantique,
│   │                            index de symboles, gestion PROPATH.
│   ├── AblSymbolCollector.kt    Deux sources :
│   │                            1. ProparseBaseVisitor (AST ANTLR4)
│   │                            2. TreeParserSymbolScope (après treeParser01)
│   ├── AblSymbolIndex.kt        Index global par fichier + par nom.
│   │                            findByName(), findByPrefix(), getSymbolsForFile().
│   ├── AblSymbol.kt             DTO symbole : nom, Kind, URI, Range, dataType, doc.
│   ├── AblSemanticResult.kt     DTO résultat sémantique : JPNode + TreeParserSymbolScope.
│   ├── AblParseResult.kt        DTO résultat syntaxique : ProgramContext + tokens + erreurs.
│   ├── SyntaxError.kt           DTO erreur (ligne, colonne, message, URI).
│   ├── AblKeywordList.kt        ~200 mots-clés ABL statiques.
│   └── AblBuiltinDocs.kt        Documentation Markdown de ~92 fonctions built-in ABL.
│
├── annotator/
│   └── AblAnnotator.kt          ExternalAnnotator : diagnostics syntaxiques CABL
│                                 en temps réel (squiggles rouges).
│
├── completion/
│   ├── AblCompletionContributor.kt  3 sources de complétion :
│   │                                1. TreeParserSymbolScope (types exacts)
│   │                                2. AblSymbolIndex (projet entier)
│   │                                3. Mots-clés ABL statiques
│   ├── AblAutoCaseTypedHandler.kt   Auto-casing des mots-clés à la frappe.
│   └── AblTemplateContextType.kt    Contexte pour les live templates.
│
├── documentation/
│   └── AblDocumentationProvider.kt  Hover : built-ins + symboles utilisateur
│                                     (commentaires /* */ précédant la définition).
│
├── navigation/
│   ├── AblGotoDeclarationHandler.kt Go to Declaration (Ctrl+B / Ctrl+Click) :
│   │                                - Symboles via AblSymbolIndex
│   │                                - Includes {file.i} → fichier source
│   └── AblFindUsagesProvider.kt     Find Usages (Alt+F7).
│
├── inspections/
│   ├── AblNoUndoInspection.kt   Avertissement NO-UNDO manquant sur DEFINE VARIABLE/TEMP-TABLE.
│   │                            Inclut un Quick Fix automatique.
│   └── AblFindNoLockInspection.kt  Avertissement FIND sans SHARE-LOCK/NO-LOCK/EXCLUSIVE-LOCK.
│
├── refactor/
│   └── AblRenameHandler.kt      Renommage de symboles (Shift+F6) via index.
│
├── structure/
│   └── AblStructureViewFactory.kt  Panneau Structure (Alt+7) : hiérarchie
│                                    des symboles depuis AblSymbolIndex.
│
├── project/
│   ├── OpenEdgeProjectService.kt   Service IntelliJ : lit openedge-project.json.
│   │                               Modèle : name, version, dlcPath, propath, databases.
│   └── AblProjectListener.kt       Recharge automatiquement la config quand le fichier change.
│
├── startup/
│   └── AblStartupActivity.kt    Post-startup : lance l'indexation du projet en background.
│
├── run/
│   └── AblRunConfigurationType.kt  Configuration d'exécution (.p via _progres/prowin).
│
└── actions/
    └── AblActions.kt            ReindexProjectAction, OpenProjectConfigAction.
```

---

## Dépendances critiques

### eu.rssw.openedge.parsers:proparse (RSSW — Riverside Software)

**C'est la seule dépendance de parsing — elle remplace entièrement les grammaires .g4 maison.**

- Contient `ABLLexer`, `ABLParser`, `ABLNodeType` (~900 tokens), `ProparseBaseVisitor`.
- Maintenu par Riverside Software pour chaque version OpenEdge.
- Dépôt Maven : `https://dl.cloudsmith.io/public/riverside-software/openedge-dev/maven/`
- Versions : https://github.com/Riverside-Software/sonar-openedge/releases

```kotlin
// build.gradle.kts
implementation("eu.rssw.openedge.parsers:proparse:3.7.2") {
    exclude(group = "org.sonarsource.sonarqube")
    exclude(group = "org.sonarsource.analyzer-commons")
}
```

---

## APIs RSSW disponibles et utilisées

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
```

Produit :
- `Proparse.ProgramContext` — arbre ANTLR4 visitable avec `ProparseBaseVisitor`
- `CommonTokenStream` — pour accéder aux tokens du hidden channel (commentaires)

### Niveau 2 — Analyse sémantique complète (AblParserFacade.analyze)

```kotlin
val pu = object : ParseUnit(content, uri, session) {}
pu.parse()
pu.treeParser01()   // ← résout symboles, types, références
val scope: TreeParserSymbolScope = pu.getRootScope()
val topNode: JPNode = pu.getTopNode()
```

Produit :
- `TreeParserSymbolScope` — scope racine avec variables, routines, buffers
- `JPNode` — arbre sémantique avec `JPNode.getSymbol()` résolu

### APIs TreeParserSymbolScope

```kotlin
scope.variables          // List<Variable> — toutes les variables définies
scope.routines           // List<Routine> — procédures, fonctions, méthodes
scope.childScopes        // List<TreeParserSymbolScope> — sous-scopes (corps de proc...)
scope.getBufferList()    // Collection<TableBuffer> — buffers table définis
```

### APIs Variable (org.prorefactor.treeparser.symbols.Variable)

```kotlin
variable.name
variable.dataType        // DataType enum : INTEGER, CHARACTER, LOGICAL...
variable.getDefineNode() // JPNode → position dans le source (line, charPositionInLine)
```

### APIs Routine (org.prorefactor.treeparser.symbols.Routine)

```kotlin
routine.name
routine.ideSignature     // String complet : "PROCEDURE foo(INPUT x AS INTEGER)"
routine.signature        // Signature courte
routine.parameters       // List<Parameter> — paramètres avec nom et type
routine.getDefineNode()  // JPNode → position de définition
```

### APIs JPNode (org.prorefactor.core.JPNode)

```kotlin
node.token               // Token ANTLR4 : line (1-based), charPositionInLine, text
node.getSymbol()         // Symbol RSSW résolu — null si pas une référence
node.firstChild          // Arbre JPNode navigable (firstChild, nextSibling...)
```

### IProparseEnvironment — création

```kotlin
// Minimal (syntaxe seule)
val settings = ProparseSettings("")
settings.setCustomProversion("12.2.0")
val env: IProparseEnvironment = object : RefactorSession(settings, Schema()) {}

// Avec PROPATH (résolution d'includes)
val settings = ProparseSettings(propath.joinToString(",") { it.toString() })
val env: IProparseEnvironment = object : RefactorSession(settings, Schema()) {
    override fun findFile3(fileName: String?): File? = super.findFile3(fileName) ?: dummyFile
}
```

### Schema — chargement de schéma DB (.df)

```kotlin
// TODO : charger les fichiers .df pour la complétion tables/champs
val schema = Schema()
schema.createTable("sports2020", "Customer", listOf("CustNum", "Name", "CreditLimit"))
val env = RefactorSession(settings, schema)
```

---

## Conventions de code

### Kotlin (plugin)

- `AblLexerAdapter.mapTokenType()` : `when` exhaustif sur `ABLNodeType`, `else → KEYWORD` générique.
- Services IntelliJ (`@Service`) : injectés via `project.service<X>()`, jamais instanciés directement.
- Toujours convertir les positions proparse (1-based) → IntelliJ (0-based) : `line - 1`.
- Les analyses sémantiques (`treeParser01`) sont lancées en background via `executeOnPooledThread`.
- Pas de blocage sur l'EDT — toujours `invokeLater` pour les updates UI.

---

## Points chauds

### 1. treeParser01() peut lever des exceptions sur du code invalide
Entourer systématiquement d'un `try/catch` et fallback sur le résultat syntaxique simple.

### 2. getRootScope() est reflété (pas toujours public)
```kotlin
val scope = runCatching {
    pu.javaClass.getMethod("getRootScope").invoke(pu) as? TreeParserSymbolScope
}.getOrNull()
```

### 3. Le `.` ABL est ambigu
`.` est à la fois terminateur d'instruction, séparateur de package et de champ.
CABL gère ça nativement — ne pas essayer de le tokeniser côté plugin.

### 4. PROPATH nécessaire pour résoudre les `{include.i}`
Sans PROPATH, les includes non résolus génèrent des centaines d'erreurs de syntaxe en cascade.
Le service limite l'affichage à 20 erreurs + message d'avertissement.

### 5. Vérifier les noms de règles après un update proparse
```bash
jar tf ~/.m2/repository/eu/rssw/openedge/parsers/proparse/*/proparse-*.jar \
    | grep "ABLParserBaseVisitor"
```

---

## État des fonctionnalités

| Fonctionnalité                    | État                     | Fichier clé                   |
|-----------------------------------|--------------------------|-------------------------------|
| Coloration syntaxique             | ✅ Opérationnel          | `AblLexerAdapter.kt`          |
| Folding (DO/END, PROC/END...)     | ✅ Opérationnel          | `AblFoldingBuilder.kt`        |
| Commenter (// et /* */)           | ✅ Opérationnel          | `AblCommenter.kt`             |
| Live Templates (snippets)         | ✅ Opérationnel          | `liveTemplates/abl.xml`       |
| Auto-casing des mots-clés         | ✅ Opérationnel          | `AblAutoCaseTypedHandler.kt`  |
| Diagnostics syntaxiques (CABL)    | ✅ Opérationnel          | `AblAnnotator.kt`             |
| Complétion mots-clés              | ✅ Opérationnel          | `AblCompletionContributor.kt` |
| Complétion symboles projet        | ✅ Opérationnel          | `AblCompletionContributor.kt` |
| Complétion sémantique (typée)     | ✅ Opérationnel          | `AblCompletionContributor.kt` |
| Documentation hover (built-ins)   | ✅ Opérationnel (~92)    | `AblBuiltinDocs.kt`           |
| Documentation hover (symboles)    | ✅ Opérationnel          | `AblDocumentationProvider.kt` |
| Go to Declaration                 | ✅ Opérationnel          | `AblGotoDeclarationHandler.kt`|
| Go to Include (Ctrl+B sur {f.i}) | ✅ Opérationnel          | `AblGotoDeclarationHandler.kt`|
| Structure View (Alt+7)            | ✅ Opérationnel          | `AblStructureViewFactory.kt`  |
| Inspection NO-UNDO + Quick Fix    | ✅ Opérationnel          | `AblNoUndoInspection.kt`      |
| Inspection FIND sans lock         | ✅ Opérationnel          | `AblFindNoLockInspection.kt`  |
| Run Configuration (.p)            | ✅ Opérationnel          | `AblRunConfigurationType.kt`  |
| openedge-project.json             | ✅ Opérationnel          | `OpenEdgeProjectService.kt`   |
| Find Usages (Alt+F7)              | 🔧 Textuel (sans scope)  | `AblFindUsagesProvider.kt`    |
| Rename (Shift+F6)                 | 🔧 Textuel (sans scope)  | `AblRenameHandler.kt`         |
| Complétion tables/champs DB       | 🔧 TODO                  | `AblSymbolCollector.kt`       |
| Chargement schéma .df             | 🔧 TODO                  | `OpenEdgeProjectService.kt`   |
| Find References sémantique        | 🔧 TODO (JPNode.getSymbol) | `AblFindUsagesProvider.kt`  |

---

## Prochaines étapes (utilisation maximale de RSSW)

### 1. Chargement des fichiers .df (schéma DB)
Lire `databases[].schemaFile` depuis `openedge-project.json` et alimenter `Schema` :
```kotlin
val schema = Schema()
// Lire le .df et appeler schema.createTable(...)
val env = RefactorSession(ProparseSettings(propath), schema)
```
Permet la complétion des tables, champs, et validation des FIND/FOR EACH.

### 2. Find References sémantique via JPNode
Après `treeParser01()`, parcourir `topNode` et collecter tous les noeuds où
`jpNode.getSymbol() === targetSymbol`. Remplace la recherche textuelle naïve.

### 3. Rename sémantique
Utiliser les références JPNode (étape 2) pour ne renommer que les vraies
références au même symbole — pas les homonymes dans d'autres scopes.

### 4. Complétion de membres OO (TYPE:method)
Résoudre le type de l'expression avant `:` depuis le scope, puis lister
les membres de la classe dans `TreeParserSymbolScope`.

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

Champs reconnus par `OpenEdgeProjectService` :
- `version` → passé à `ProparseSettings.setCustomProversion()`
- `dlcPath` + `propath` → alimentent `IProparseEnvironment` pour la résolution d'includes
- `databases[].schemaFile` → **TODO** : alimenter `Schema` pour la complétion DB
