---
name: abl-dev-context
description: "Référence architecture + conventions + gotchas pour le plugin ABL IntelliJ (Kotlin/RSSW). À lire avant toute implémentation ou revue."
---

# ABL IntelliJ Plugin — Developer Context

## Constantes

- **Company ID:** `01420bc5-12ec-4b56-bf6a-2d420be0b2d5`
- **Project ID:** `cefe7156-21f5-4e8c-bf50-ee9101ccad2c`
- **Repo:** `https://github.com/Loe159/abl-plugin-intellij`
- **Local:** `/home/aiagent/workspace/abl-plugin-intellij`
- **Worktrees:** `/home/aiagent/workspace/abl-worktrees/`
- **proparse:** `3.7.2` (ne pas changer sans vérifier sonar-openedge releases)
- **IntelliJ cible:** 2023.2+ (`sinceBuild=232`), testé sur 2023.2, 2023.3, 2024.1

## Architecture — fichiers critiques

```
src/main/kotlin/com/ablls/plugin/
├── core/AblParserFacade.kt          ENTRY POINT : parse() + analyze()
│                                    parse()   → rapide, appel sur chaque frappe
│                                    analyze() → sémantique, background uniquement
├── core/AblProjectAnalysisService.kt  @Service(PROJECT) : cache + index + PROPATH
│                                    analyzeFile()         → syntaxique + update index
│                                    analyzeFileSemantic() → treeParser01 complet (bloquant)
│                                    analyzeSemanticAsync() → lance en background
│                                    buildIndexInBackground() → indexation initiale
├── core/AblSymbolCollector.kt       AST visitor + TreeParserSymbolScope → List<AblSymbol>
├── core/AblSymbolIndex.kt           findByName(), findByPrefix(), getSymbolsForFile()
├── parser/AblLexerAdapter.kt        PONT LEXER : scanner de caractères maison → IntelliJ Lexer
│                                    NE PAS utiliser ABLLexer ici (trop lourd pour streaming)
├── parser/AblParserDefinition.kt    PSI entry point
├── highlight/AblFoldingBuilder.kt   DO..END, PROCEDURE..END, CLASS..END
├── annotator/AblAnnotator.kt        ExternalAnnotator : squiggles temps réel
│                                    collectInformation(EDT) → doAnnotate(bg) → apply(EDT)
├── completion/AblCompletionContributor.kt  3 sources : scope > index > mots-clés
├── navigation/AblGotoDeclarationHandler.kt  Symboles + {include.i} → fichier source
├── inspections/AblInspectionHelper.kt  toRange(doc, line1based, col, len) → TextRange
├── inspections/AblNoUndoInspection.kt  DEFINE sans NO-UNDO + Quick Fix
├── inspections/AblFindNoLockInspection.kt  FIND sans lock
├── inspections/AblEmptyCatchInspection.kt  CATCH vide
├── inspections/AblUnusedVariableInspection.kt  Variable non lue (sémantique + fallback)
├── inspections/AblFortranOperatorsInspection.kt  EQ/NE/GT → =/<>/> Quick Fix
├── inspections/AblMissingSchemaPrefixInspection.kt
├── inspections/AblNoErrorWithoutCheckInspection.kt
├── inspections/AblStringConcatInWhereInspection.kt
├── debug/AblDebugConnection.kt      Client TCP vers OE (-debugReady PORT)
├── coverage/AblProfilerParser.kt    Parse .prof RSSW
├── xref/XrefParser.kt               Parse .xref RSSW
├── duplication/AblDuplicationDetector.kt  Hash de tokens normalisés
└── project/OpenEdgeProjectService.kt  Lit openedge-project.json
```

## Commandes build

```bash
./gradlew compileKotlin --no-daemon   # vérification rapide (~30s)
./gradlew test --no-daemon            # tests (~60s)
./gradlew buildPlugin --no-daemon     # → build/distributions/
./gradlew verifyPlugin --no-daemon    # compatibilité multi-versions
```

## Gotchas critiques (ne jamais violer)

1. **1-based → 0-based** : positions proparse sont 1-based (ligne), IntelliJ est 0-based
   → toujours `line - 1`; la colonne (`charPositionInLine`) est déjà 0-based, pas de conversion

2. **treeParser01() lève des exceptions** sur du code ABL invalide
   → Toujours wrapper individuellement dans try/catch, fallback sur résultat syntaxique

3. **getRootScope() peut ne pas être public** selon la version proparse
   → Utiliser `runCatching { pu.javaClass.getMethod("getRootScope").invoke(pu) as? TreeParserSymbolScope }.getOrNull()`

4. **Jamais bloquer l'EDT**
   → Analyses sémantiques sur `executeOnPooledThread`, updates UI via `invokeLater`
   → `doAnnotate()` est déjà sur background thread (ExternalAnnotator) : OK d'y appeler `analyzeFile()`

5. **Le `.` ABL est ambigu** : terminateur d'instruction + séparateur de package + de champ
   → Ne pas essayer de le tokeniser côté plugin, proparse le gère

6. **PROPATH requis** pour résoudre les `{include.i}`
   → Sans PROPATH : cascade d'erreurs → limiter à 20 erreurs + avertissement

7. **Logger = companion object**, pas variable d'instance
   ```kotlin
   companion object { private val LOG = Logger.getInstance(MyClass::class.java) }
   ```

8. **Services via `project.service<X>()`**, jamais instanciés directement

## ABLNodeType — source de vérité RSSW (NE PAS coder en dur les mots-clés)

```kotlin
// ✅ CORRECT — enumerate depuis proparse
val keywords: Set<String> = buildSet {
    for (type in ABLNodeType.values()) {
        if (!type.isKeyword()) continue
        val text = type.getText() ?: continue
        if (text.isNotBlank()) add(text.uppercase())
        type.alternate?.let  { alt -> if (alt.isNotBlank()) add(alt.uppercase()) }
        type.alternate2?.let { alt -> if (alt.isNotBlank()) add(alt.uppercase()) }
    }
}

// ✅ CORRECT — identifier vs mot-clé dans le lexer
val nodeType = ABLNodeType.getLiteral(word.lowercase())
return if (nodeType != null && nodeType.isKeyword()) AblTokenTypes.KEYWORD else AblTokenTypes.IDENTIFIER

// ❌ INTERDIT — ne jamais maintenir une liste statique de mots-clés ABL
val KEYWORDS = setOf("DEFINE", "VARIABLE", "IF", "THEN"...)  // incomplet, pas maintenable
```

## Bugs connus à ne pas reproduire

- `AblNoUndoInspection.kt` — `isStatementEnd()` dupliquée (classe principale + inner class)
- Ne jamais écrire `'\$name'` en Kotlin — le `\$` échappe le dollar et affiche littéralement `$name`. Écrire `'$name'` (avec interpolation normale).

## Modules RSSW disponibles (à ajouter si besoin)

| Module | Artefact | Usage |
|--------|----------|-------|
| `database-parser` | `eu.rssw.openedge.parsers:database-parser:3.7.2` | Parse `.df` → `DumpFileUtils.getDatabaseDescription(path)` → tables+champs |
| `rcode-reader` | `eu.rssw.openedge.parsers:rcode-reader:3.7.2` | Lit `.r` compilés → symboles sans source |

## Patterns de test

```kotlin
// LightPlatformTestCase pour les tests unitaires plugin
class MyTest : LightPlatformTestCase() {
    fun testSomething() {
        val file = LightVirtualFile("test.p", AblFileType.INSTANCE,
            "DEFINE VARIABLE x AS INTEGER NO-UNDO.")
        // ...
    }
}
```

## Dépendances proparse

```kotlin
implementation("eu.rssw.openedge.parsers:proparse:3.7.2") {
    exclude(group = "org.sonarsource.sonarqube")
    exclude(group = "org.sonarsource.analyzer-commons")
}
// Maven : https://dl.cloudsmith.io/public/riverside-software/openedge-dev/maven/
// Source RSSW cloné : /home/aiagent/workspace/sonar-openedge (référence des APIs)
```

## Convention commits

```
feat(scope): description courte

Fixes: SUP-NNN
Co-Authored-By: Paperclip <noreply@paperclip.ing>
```

Scopes : `completion`, `annotator`, `parser`, `inspection`, `navigation`, `refactor`, `debug`, `coverage`, `xref`

## Branches agent

Format : `agent/<issue-identifier>-<slug>`
