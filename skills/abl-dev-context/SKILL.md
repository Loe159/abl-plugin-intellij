---
name: abl-dev-context
description: "Compact architecture + conventions reference for the ABL IntelliJ plugin (Kotlin/RSSW). Read before any implementation or test task to avoid hallucination."
---

# ABL IntelliJ Plugin — Developer Context

## Key Constants

- **Company ID:** `01420bc5-12ec-4b56-bf6a-2d420be0b2d5`
- **Project ID:** `cefe7156-21f5-4e8c-bf50-ee9101ccad2c`
- **Agent IDs:** Engineer `9f9f4b8b`, TestWriter `1706a714`, PRAgent `0db5710d`
- **Repo:** `https://github.com/Loe159/abl-plugin-intellij`
- **Local workspace:** `/home/aiagent/workspace/abl-plugin-intellij`
- **Worktrees:** `/home/aiagent/workspace/abl-worktrees/`

## Architecture Map (critical files only)

```
src/main/kotlin/com/ablls/plugin/
├── core/AblParserFacade.kt      ← ENTRY POINT: parse() + analyze()
├── core/AblProjectAnalysisService.kt ← cache + symbol index + PROPATH
├── core/AblSymbolCollector.kt   ← collects vars/routines from AST & scope
├── core/AblSymbolIndex.kt       ← findByName(), findByPrefix(), getSymbolsForFile()
├── parser/AblLexerAdapter.kt    ← CENTRAL BRIDGE: ABLLexer → IntelliJ Lexer
├── parser/AblParserDefinition.kt ← PSI entry point
├── highlight/AblSyntaxHighlighter.kt
├── completion/AblCompletionContributor.kt ← 3 sources: scope+index+keywords
├── annotator/AblAnnotator.kt    ← real-time syntax errors (ExternalAnnotator)
├── navigation/AblGotoDeclarationHandler.kt
├── inspections/AblNoUndoInspection.kt
├── inspections/AblFindNoLockInspection.kt
└── project/OpenEdgeProjectService.kt ← reads openedge-project.json
```

## Build Commands

```bash
./gradlew compileKotlin --no-daemon   # fast compile check (~30s)
./gradlew test --no-daemon            # run tests (~60s)
./gradlew buildPlugin --no-daemon     # full build → build/distributions/
./gradlew verifyPlugin --no-daemon    # compatibility check
```

## Critical Gotchas (do not violate)

1. **1-based → 0-based**: proparse positions are 1-based; IntelliJ is 0-based → always `line - 1`
2. **treeParser01() throws** on invalid ABL → always `try/catch`, fallback to syntactic result
3. **getRootScope() may need reflection** — see `AblParserFacade.kt` pattern with `runCatching`
4. **No EDT blocking** — semantic analyses go on `executeOnPooledThread`, UI updates via `invokeLater`
5. **`.` is ambiguous in ABL** — statement terminator + package separator + field separator; never try to tokenize it yourself
6. **PROPATH required** for include resolution — without it, thousands of cascade errors

## Dependency

```kotlin
// build.gradle.kts — do NOT change version without checking sonar-openedge releases
implementation("eu.rssw.openedge.parsers:proparse:3.7.2") {
    exclude(group = "org.sonarsource.sonarqube")
    exclude(group = "org.sonarsource.analyzer-commons")
}
// Maven: https://dl.cloudsmith.io/public/riverside-software/openedge-dev/maven/
```

## Test Patterns

```kotlin
// Unit test — LightPlatformTestCase pattern
class MyFeatureTest : LightPlatformTestCase() {
    fun testSomething() {
        val file = LightVirtualFile("test.p", AblFileType.INSTANCE, "DEFINE VARIABLE x AS INTEGER NO-UNDO.")
        // ...
    }
}
```

## Commit Message Convention

```
feat(scope): short description

Fixes: SUP-NNN
Co-Authored-By: Paperclip <noreply@paperclip.ing>
```

Scope examples: `completion`, `annotator`, `parser`, `inspection`, `navigation`, `refactor`
