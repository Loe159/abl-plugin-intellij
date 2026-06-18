# Research Recipes

Run commands from the repository root. Keep research read-only.

## Find Existing Plugin Usage

```powershell
rg -n "ABLNodeType|ABLLexer|ParseUnit|treeParser01|TreeParserSymbolScope|JPNode" `
  src/main/kotlin src/test/kotlin
```

Start with these boundaries:

```text
src/main/kotlin/com/ablls/plugin/core/AblParserFacade.kt
src/main/kotlin/com/ablls/plugin/core/AblParseResult.kt
src/main/kotlin/com/ablls/plugin/core/AblProjectAnalysisService.kt
src/main/kotlin/com/ablls/plugin/core/AblSymbolCollector.kt
src/main/kotlin/com/ablls/plugin/parser/AblLexerAdapter.kt
src/main/kotlin/com/ablls/plugin/parser/AblPsiParser.kt
```

## Locate Published RSSW Sources

```powershell
Get-ChildItem D:\.gradle\caches\modules-2\files-2.1\eu.rssw.openedge.parsers `
  -Recurse -Filter "*-sources.jar"
```

The path is machine-specific. Discover it; do not paste it into production code.

## Inspect a Source JAR Without Extracting It

```powershell
tar -tf <sources.jar> | Select-String "ParseUnit|ABLNodeType|JPNode"
tar -xOf <sources.jar> org/prorefactor/treeparser/ParseUnit.java |
  Select-String "treeParser01|getRootScope|getTopNode" -Context 1,2
```

## Use an RSSW Checkout When Supplied

```powershell
rg -n "class ParseUnit|treeParser01|getRootScope" <RSSW_REPO>
rg -n "enum ABLNodeType|getLiteral|isKeyword" <RSSW_REPO>
```

Never guess `<RSSW_REPO>`. Record the commit SHA when a checkout is used.

## Evidence Rules

- Prefer source code and focused tests over comments.
- Record dependency version and source location.
- Mark reflection, fallback behavior, and nullable returns explicitly.
- If only plugin usage is available, say "verified in plugin", not "verified in
  RSSW".
- If an API is absent or unclear, report it as unknown instead of designing
  around an imagined method.
