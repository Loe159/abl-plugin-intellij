# Verified Proparse Entry Points

Evidence date: 2026-06-09.

## Dependency

- `build.gradle.kts` pins `eu.rssw.openedge.parsers:proparse:3.7.2`.
- `settings.gradle.kts` configures the Riverside Software Maven repository.
- The local Gradle cache contains `proparse-3.7.2-sources.jar`.
- No RSSW `sonar-openedge` source checkout was found under `D:\` to depth 3.

## Verified In RSSW 3.7.2 Source JAR

| API | Verified behavior |
| --- | --- |
| `org.prorefactor.core.ABLNodeType` | `getLiteral(String)` resolves literals and `isKeyword()` identifies keyword node types. |
| `org.prorefactor.proparse.ABLLexer` | Public constructor accepts `IProparseEnvironment`, `Charset`, source bytes, file name, and `lexOnly`. |
| `org.prorefactor.treeparser.ParseUnit` | `getTopNode()` and `getRootScope()` are public nullable methods. `treeParser01()` calls `parse()` when needed. |
| `org.prorefactor.core.JPNode` | `query(ABLNodeType, ...)` returns matching nodes and `getSymbol()` exposes the attached symbol. |
| `org.prorefactor.treeparser.TreeParserSymbolScope` | Exposes child scopes, variables, routines, `lookupVariable(String)`, and `lookupRoutines(String)`. |

## Verified Plugin Boundaries

- `core/AblParserFacade.kt`
  - Builds the syntax pipeline with `ABLLexer`, `Lexer`, `PostLexer`,
    `TokenList`, and generated `Proparse`.
  - Calls `ParseUnit.treeParser01()` inside `try/catch`.
  - Creates minimal and project `RefactorSession` environments.
- `core/AblParseResult.kt`
  - Lazily constructs and parses `ParseUnit`.
  - Exposes `topNode` and delegates `queryNodes()` to `JPNode.query()`.
- `core/AblProjectAnalysisService.kt`
  - Owns project-level analysis, schema creation, caching, and indexing.
- `core/AblSymbolCollector.kt`
  - Reads the generated ANTLR tree and `TreeParserSymbolScope`.
- `parser/AblLexerAdapter.kt`
  - Is a handwritten streaming IntelliJ lexer.
  - Uses `ABLNodeType.getLiteral()` for word classification; it does not use
    `ABLLexer` directly.
- `parser/AblPsiParser.kt`
  - Builds composite PSI block nodes with a stack-based parser.

## Important Correction

The old claim that `AblParserFacade` is the only file that instantiates RSSW
parser classes is not exact: `AblParseResult` constructs `ParseUnit`. Treat the
two files together as the current core parsing boundary.

## Still Unknown

- Behavior that depends on a full RSSW repository checkout rather than the
  published 3.7.2 source JAR.
- Compatibility with Proparse versions other than the pinned 3.7.2.
- Remote branch protection and repository settings.
