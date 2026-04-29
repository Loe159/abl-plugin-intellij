# Graph Report - .  (2026-04-29)

## Corpus Check
- Corpus is ~32,303 words - fits in a single context window. You may not need a graph.

## Summary
- 637 nodes · 578 edges · 89 communities detected
- Extraction: 98% EXTRACTED · 2% INFERRED · 0% AMBIGUOUS · INFERRED: 10 edges (avg confidence: 0.82)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Folding Builder Tests|Folding Builder Tests]]
- [[_COMMUNITY_Plugin Architecture Overview|Plugin Architecture Overview]]
- [[_COMMUNITY_Symbol Collection|Symbol Collection]]
- [[_COMMUNITY_Run Configuration|Run Configuration]]
- [[_COMMUNITY_Debug Configuration|Debug Configuration]]
- [[_COMMUNITY_Built-in Documentation|Built-in Documentation]]
- [[_COMMUNITY_Syntax Helpers (BracketsComments)|Syntax Helpers (Brackets/Comments)]]
- [[_COMMUNITY_File Structure View|File Structure View]]
- [[_COMMUNITY_Debug Breakpoints|Debug Breakpoints]]
- [[_COMMUNITY_Debug Connection|Debug Connection]]
- [[_COMMUNITY_Debug Process & Evaluator|Debug Process & Evaluator]]
- [[_COMMUNITY_Lexer Adapter|Lexer Adapter]]
- [[_COMMUNITY_Program Runner|Program Runner]]
- [[_COMMUNITY_Project Config & DB|Project Config & DB]]
- [[_COMMUNITY_Parser Facade|Parser Facade]]
- [[_COMMUNITY_Paperclip Agent Pipeline|Paperclip Agent Pipeline]]
- [[_COMMUNITY_Code Inspections (NO-UNDO)|Code Inspections (NO-UNDO)]]
- [[_COMMUNITY_Plugin Core & Icons|Plugin Core & Icons]]
- [[_COMMUNITY_Syntax Highlighting|Syntax Highlighting]]
- [[_COMMUNITY_Parser Definition|Parser Definition]]
- [[_COMMUNITY_Documentation Provider|Documentation Provider]]
- [[_COMMUNITY_Project Analysis Service|Project Analysis Service]]
- [[_COMMUNITY_Color Settings|Color Settings]]
- [[_COMMUNITY_Operator Inspection|Operator Inspection]]
- [[_COMMUNITY_Unused Variable Inspection|Unused Variable Inspection]]
- [[_COMMUNITY_PSI Elements & File|PSI Elements & File]]
- [[_COMMUNITY_Symbol Index|Symbol Index]]
- [[_COMMUNITY_Find Usages|Find Usages]]
- [[_COMMUNITY_Code Completion|Code Completion]]
- [[_COMMUNITY_Console Filter|Console Filter]]
- [[_COMMUNITY_Project Config Actions|Project Config Actions]]
- [[_COMMUNITY_Compiler Warning Annotator|Compiler Warning Annotator]]
- [[_COMMUNITY_Coverage Service|Coverage Service]]
- [[_COMMUNITY_Duplication Detector|Duplication Detector]]
- [[_COMMUNITY_Duplicates Panel|Duplicates Panel]]
- [[_COMMUNITY_Module Group 35|Module Group 35]]
- [[_COMMUNITY_Module Group 36|Module Group 36]]
- [[_COMMUNITY_Module Group 37|Module Group 37]]
- [[_COMMUNITY_Module Group 38|Module Group 38]]
- [[_COMMUNITY_Module Group 39|Module Group 39]]
- [[_COMMUNITY_Module Group 40|Module Group 40]]
- [[_COMMUNITY_Module Group 41|Module Group 41]]
- [[_COMMUNITY_Module Group 42|Module Group 42]]
- [[_COMMUNITY_Module Group 43|Module Group 43]]
- [[_COMMUNITY_Module Group 44|Module Group 44]]
- [[_COMMUNITY_Module Group 45|Module Group 45]]
- [[_COMMUNITY_Module Group 46|Module Group 46]]
- [[_COMMUNITY_Module Group 47|Module Group 47]]
- [[_COMMUNITY_Module Group 48|Module Group 48]]
- [[_COMMUNITY_Module Group 49|Module Group 49]]
- [[_COMMUNITY_Module Group 50|Module Group 50]]
- [[_COMMUNITY_Module Group 51|Module Group 51]]
- [[_COMMUNITY_Module Group 52|Module Group 52]]
- [[_COMMUNITY_Module Group 53|Module Group 53]]
- [[_COMMUNITY_Module Group 54|Module Group 54]]
- [[_COMMUNITY_Module Group 55|Module Group 55]]
- [[_COMMUNITY_Module Group 56|Module Group 56]]
- [[_COMMUNITY_Module Group 57|Module Group 57]]
- [[_COMMUNITY_Module Group 58|Module Group 58]]
- [[_COMMUNITY_Module Group 59|Module Group 59]]
- [[_COMMUNITY_Module Group 60|Module Group 60]]
- [[_COMMUNITY_Module Group 61|Module Group 61]]
- [[_COMMUNITY_Module Group 62|Module Group 62]]
- [[_COMMUNITY_Module Group 63|Module Group 63]]
- [[_COMMUNITY_Module Group 64|Module Group 64]]
- [[_COMMUNITY_Module Group 65|Module Group 65]]
- [[_COMMUNITY_Module Group 66|Module Group 66]]
- [[_COMMUNITY_Module Group 67|Module Group 67]]
- [[_COMMUNITY_Module Group 68|Module Group 68]]
- [[_COMMUNITY_Module Group 69|Module Group 69]]
- [[_COMMUNITY_Module Group 70|Module Group 70]]
- [[_COMMUNITY_Module Group 71|Module Group 71]]
- [[_COMMUNITY_Module Group 72|Module Group 72]]
- [[_COMMUNITY_Module Group 73|Module Group 73]]
- [[_COMMUNITY_Module Group 74|Module Group 74]]
- [[_COMMUNITY_Module Group 75|Module Group 75]]
- [[_COMMUNITY_Module Group 76|Module Group 76]]
- [[_COMMUNITY_Module Group 77|Module Group 77]]
- [[_COMMUNITY_Module Group 78|Module Group 78]]
- [[_COMMUNITY_Module Group 79|Module Group 79]]
- [[_COMMUNITY_Module Group 80|Module Group 80]]
- [[_COMMUNITY_Module Group 81|Module Group 81]]
- [[_COMMUNITY_Module Group 82|Module Group 82]]
- [[_COMMUNITY_Module Group 83|Module Group 83]]
- [[_COMMUNITY_Module Group 84|Module Group 84]]
- [[_COMMUNITY_Module Group 85|Module Group 85]]
- [[_COMMUNITY_Module Group 86|Module Group 86]]
- [[_COMMUNITY_Module Group 87|Module Group 87]]
- [[_COMMUNITY_Module Group 88|Module Group 88]]

## God Nodes (most connected - your core abstractions)
1. `AblFoldingBuilderTest` - 37 edges
2. `AblSymbolVisitor` - 22 edges
3. `AblDebugConnection` - 16 edges
4. `AblDebugProcess` - 12 edges
5. `AblLexerAdapter` - 12 edges
6. `AblParserFacade.kt — RSSW Parsing Entry Point` - 12 edges
7. `Skill: abl-dev-context — ABL Architecture Reference` - 10 edges
8. `AblParserDefinition` - 9 edges
9. `AblDocumentationProvider` - 9 edges
10. `ABL IntelliJ Plugin` - 9 edges

## Surprising Connections (you probably didn't know these)
- `ABL File Icon — Green Rhombus/Diamond Logo` --conceptually_related_to--> `ABL IntelliJ Plugin`  [INFERRED]
  src/main/resources/icons/abl-file.svg → README.md
- `ABL Engineer Agent` --references--> `AblParserDefinition.kt — PSI Entry Point`  [INFERRED]
  agents/engineer.md → CLAUDE.md
- `ABL File Icon — Green Rhombus/Diamond Logo` --references--> `AblIcons.kt — SVG Icons`  [EXTRACTED]
  src/main/resources/icons/abl-file.svg → CLAUDE.md
- `Rationale: No LSP — Native IntelliJ Extension Points` --rationale_for--> `ABL IntelliJ Plugin`  [EXTRACTED]
  CLAUDE.md → README.md
- `Skill: abl-dev-context — ABL Architecture Reference` --references--> `AblAnnotator.kt — Real-time Syntax Diagnostics`  [EXTRACTED]
  skills/abl-dev-context/SKILL.md → CLAUDE.md

## Hyperedges (group relationships)
- **ABL Agent Delivery Pipeline** — agents_ceo, agents_engineer, agents_test_writer, agents_reviewer, agents_pr_agent [EXTRACTED 1.00]
- **RSSW proparse API Surface** — claude_rssw_abllexer, claude_rssw_proparse_class, claude_rssw_parseunit, claude_rssw_tree_parser_symbol_scope, claude_rssw_jpnode, claude_rssw_refactor_session, claude_rssw_schema, claude_rssw_ablnodetype [EXTRACTED 1.00]
- **Core Parsing Layer** — claude_abl_parser_facade, claude_abl_project_analysis_service, claude_abl_symbol_collector, claude_abl_symbol_index, claude_abl_symbol, claude_abl_parse_result, claude_abl_semantic_result [EXTRACTED 1.00]
- **IntelliJ Extension Point Implementations** — claude_abl_lexer_adapter, claude_abl_parser_definition, claude_abl_syntax_highlighter, claude_abl_folding_builder, claude_abl_bracket_matcher, claude_abl_commenter, claude_abl_annotator, claude_abl_completion_contributor, claude_abl_documentation_provider, claude_abl_goto_declaration_handler, claude_abl_find_usages_provider, claude_abl_no_undo_inspection, claude_abl_find_no_lock_inspection, claude_abl_rename_handler, claude_abl_structure_view_factory, claude_abl_run_config_type [EXTRACTED 1.00]

## Communities

### Community 0 - "Folding Builder Tests"
Cohesion: 0.05
Nodes (1): AblFoldingBuilderTest

### Community 1 - "Plugin Architecture Overview"
Cohesion: 0.09
Nodes (32): AblAnnotator.kt — Real-time Syntax Diagnostics, AblCompletionContributor.kt — 3-Source Completion, AblGotoDeclarationHandler.kt — Go to Declaration, AblKeywordList.kt — 200 Static ABL Keywords, AblLexerAdapter.kt — ABLLexer to IntelliJ Bridge, AblParseResult.kt — Syntactic Result DTO, AblParserDefinition.kt — PSI Entry Point, AblParserFacade.kt — RSSW Parsing Entry Point (+24 more)

### Community 2 - "Symbol Collection"
Cohesion: 0.07
Nodes (2): AblSymbolCollector, AblSymbolVisitor

### Community 3 - "Run Configuration"
Cohesion: 0.08
Nodes (5): AblRunConfiguration, AblRunConfigurationEditor, AblRunConfigurationFactory, AblRunConfigurationType, AblRunState

### Community 4 - "Debug Configuration"
Cohesion: 0.09
Nodes (5): AblDebugConfiguration, AblDebugConfigurationEditor, AblDebugConfigurationFactory, AblDebugConfigurationType, AblDebugRunState

### Community 5 - "Built-in Documentation"
Cohesion: 0.12
Nodes (9): AblBuiltinDocs, buildSafeEnv(), gracefulShutdown(), jsonError(), jsonResponse(), log(), messagesToPrompt(), spawnClaudeStreaming() (+1 more)

### Community 6 - "Syntax Helpers (Brackets/Comments)"
Cohesion: 0.1
Nodes (5): AblBracketMatcher, AblCommenter, AblFoldingBuilder, BlockStart, Tok

### Community 7 - "File Structure View"
Cohesion: 0.1
Nodes (4): AblFileStructureElement, AblStructureViewFactory, AblStructureViewModel, AblSymbolStructureElement

### Community 8 - "Debug Breakpoints"
Cohesion: 0.12
Nodes (6): AblBreakpointHandler, AblDebugEditorsProvider, AblLineBreakpointType, AblStackFrame, AblSuspendContext, AblValue

### Community 9 - "Debug Connection"
Cohesion: 0.12
Nodes (1): AblDebugConnection

### Community 10 - "Debug Process & Evaluator"
Cohesion: 0.13
Nodes (2): AblDebugEvaluator, AblDebugProcess

### Community 11 - "Lexer Adapter"
Cohesion: 0.15
Nodes (1): AblLexerAdapter

### Community 12 - "Program Runner"
Cohesion: 0.15
Nodes (2): AblProgramRunner, AblRemoteProcessHandler

### Community 13 - "Project Config & DB"
Cohesion: 0.15
Nodes (5): DatabaseAlias, DatabaseConnection, OpenEdgeProjectConfig, OpenEdgeProjectService, OpenEdgeProjectServiceImpl

### Community 14 - "Parser Facade"
Cohesion: 0.17
Nodes (2): AblParserFacade, CollectingErrorListener

### Community 15 - "Paperclip Agent Pipeline"
Cohesion: 0.29
Nodes (12): ABL CEO Agent — Pipeline Orchestrator, Company ID: 01420bc5-12ec-4b56-bf6a-2d420be0b2d5, ABL Engineer Agent, Paperclip Orchestration Platform, ABL Product Manager Agent, ABL PR Agent, Project ID: cefe7156-21f5-4e8c-bf50-ee9101ccad2c, ABL Reviewer Agent — Code Review (+4 more)

### Community 16 - "Code Inspections (NO-UNDO)"
Cohesion: 0.18
Nodes (2): AblNoUndoInspection, AddNoUndoFix

### Community 17 - "Plugin Core & Icons"
Cohesion: 0.18
Nodes (11): ABL File Icon — Green Rhombus/Diamond Logo, AblIcons.kt — SVG Icons, Rationale: No LSP — Native IntelliJ Extension Points, ABL IntelliJ Plugin, Feature: Code Completion, Feature: Go to Declaration, Feature: Inspections and Quick Fix, Feature: Run Configuration (+3 more)

### Community 18 - "Syntax Highlighting"
Cohesion: 0.2
Nodes (2): AblFindNoLockInspection, AddNoLockFix

### Community 19 - "Parser Definition"
Cohesion: 0.2
Nodes (1): AblParserDefinition

### Community 20 - "Documentation Provider"
Cohesion: 0.2
Nodes (1): AblDocumentationProvider

### Community 21 - "Project Analysis Service"
Cohesion: 0.22
Nodes (1): AblProjectAnalysisService

### Community 22 - "Color Settings"
Cohesion: 0.22
Nodes (1): AblColorSettingsPage

### Community 23 - "Operator Inspection"
Cohesion: 0.22
Nodes (2): AblFortranOperatorsInspection, ReplaceFortranOperatorFix

### Community 24 - "Unused Variable Inspection"
Cohesion: 0.22
Nodes (1): AblUnusedVariableInspection

### Community 25 - "PSI Elements & File"
Cohesion: 0.22
Nodes (3): AblElementFactory, AblFile, AblPsiParser

### Community 26 - "Symbol Index"
Cohesion: 0.25
Nodes (1): AblSymbolIndex

### Community 27 - "Find Usages"
Cohesion: 0.25
Nodes (1): AblFindUsagesProvider

### Community 28 - "Code Completion"
Cohesion: 0.25
Nodes (2): AblCompletionContributor, AblCompletionProvider

### Community 29 - "Console Filter"
Cohesion: 0.29
Nodes (2): AblConsoleFilterProvider, AblErrorConsoleFilter

### Community 30 - "Project Config Actions"
Cohesion: 0.29
Nodes (2): OpenProjectConfigAction, ReindexProjectAction

### Community 31 - "Compiler Warning Annotator"
Cohesion: 0.29
Nodes (3): AblCompilerWarningAnnotator, CompilerWarning, Input

### Community 32 - "Coverage Service"
Cohesion: 0.33
Nodes (1): AblCoverageService

### Community 33 - "Duplication Detector"
Cohesion: 0.33
Nodes (3): AblDuplicationDetector, DuplicatePair, Fragment

### Community 34 - "Duplicates Panel"
Cohesion: 0.33
Nodes (1): AblDuplicatesPanel

### Community 35 - "Module Group 35"
Cohesion: 0.33
Nodes (1): AblEmptyCatchInspection

### Community 36 - "Module Group 36"
Cohesion: 0.33
Nodes (1): AblMissingSchemaPrefixInspection

### Community 37 - "Module Group 37"
Cohesion: 0.33
Nodes (1): AblNoErrorWithoutCheckInspection

### Community 38 - "Module Group 38"
Cohesion: 0.33
Nodes (1): AblStringConcatInWhereInspection

### Community 39 - "Module Group 39"
Cohesion: 0.33
Nodes (1): AblFileType

### Community 40 - "Module Group 40"
Cohesion: 0.33
Nodes (1): XrefPanel

### Community 41 - "Module Group 41"
Cohesion: 0.33
Nodes (2): AblAnnotator, Input

### Community 42 - "Module Group 42"
Cohesion: 0.4
Nodes (1): AblProfilerParser

### Community 43 - "Module Group 43"
Cohesion: 0.4
Nodes (3): AblRange, AblSymbol, Kind

### Community 44 - "Module Group 44"
Cohesion: 0.4
Nodes (1): AblRunConfigurationProducer

### Community 45 - "Module Group 45"
Cohesion: 0.5
Nodes (1): AblAnnotatorIntegrationTest

### Community 46 - "Module Group 46"
Cohesion: 0.5
Nodes (1): LoadCoverageAction

### Community 47 - "Module Group 47"
Cohesion: 0.5
Nodes (1): AblRenameHandler

### Community 48 - "Module Group 48"
Cohesion: 0.5
Nodes (1): AblSyntaxHighlighter

### Community 49 - "Module Group 49"
Cohesion: 0.5
Nodes (1): AblLanguage

### Community 50 - "Module Group 50"
Cohesion: 0.5
Nodes (1): AblGotoDeclarationHandler

### Community 51 - "Module Group 51"
Cohesion: 0.5
Nodes (3): XrefFile, XrefRecord, XrefType

### Community 52 - "Module Group 52"
Cohesion: 0.5
Nodes (1): AblProjectListener

### Community 53 - "Module Group 53"
Cohesion: 0.67
Nodes (1): PrintMethodsTest

### Community 54 - "Module Group 54"
Cohesion: 0.67
Nodes (1): AblSemanticResult

### Community 55 - "Module Group 55"
Cohesion: 0.67
Nodes (1): AblParseResult

### Community 56 - "Module Group 56"
Cohesion: 0.67
Nodes (1): AblStartupActivity

### Community 57 - "Module Group 57"
Cohesion: 0.67
Nodes (1): FindAblDuplicatesAction

### Community 58 - "Module Group 58"
Cohesion: 0.67
Nodes (1): AblDuplicatesToolWindowFactory

### Community 59 - "Module Group 59"
Cohesion: 0.67
Nodes (1): AblHighlighterFactory

### Community 60 - "Module Group 60"
Cohesion: 0.67
Nodes (1): AblInspectionHelper

### Community 61 - "Module Group 61"
Cohesion: 0.67
Nodes (1): XrefToolWindowFactory

### Community 62 - "Module Group 62"
Cohesion: 0.67
Nodes (1): XrefParser

### Community 63 - "Module Group 63"
Cohesion: 0.67
Nodes (1): ShowXrefAction

### Community 64 - "Module Group 64"
Cohesion: 0.67
Nodes (1): AblTemplateContextType

### Community 65 - "Module Group 65"
Cohesion: 0.67
Nodes (1): AblAutoCaseTypedHandler

### Community 66 - "Module Group 66"
Cohesion: 0.67
Nodes (1): AblWarningFileListener

### Community 67 - "Module Group 67"
Cohesion: 1.0
Nodes (1): AblKeywordList

### Community 68 - "Module Group 68"
Cohesion: 1.0
Nodes (1): SyntaxError

### Community 69 - "Module Group 69"
Cohesion: 1.0
Nodes (1): AblIcons

### Community 70 - "Module Group 70"
Cohesion: 1.0
Nodes (2): AblBuiltinDocs.kt — 92 Built-in Function Docs, AblDocumentationProvider.kt — Hover Documentation

### Community 71 - "Module Group 71"
Cohesion: 1.0
Nodes (0): 

### Community 72 - "Module Group 72"
Cohesion: 1.0
Nodes (0): 

### Community 73 - "Module Group 73"
Cohesion: 1.0
Nodes (1): AblLanguage.kt — ABL Language Singleton

### Community 74 - "Module Group 74"
Cohesion: 1.0
Nodes (1): AblFileType.kt — ABL File Extensions

### Community 75 - "Module Group 75"
Cohesion: 1.0
Nodes (1): AblPsiParser.kt — Flat PSI Tree

### Community 76 - "Module Group 76"
Cohesion: 1.0
Nodes (1): AblHighlighterFactory.kt

### Community 77 - "Module Group 77"
Cohesion: 1.0
Nodes (1): AblColorSettingsPage.kt — Editor Color Scheme

### Community 78 - "Module Group 78"
Cohesion: 1.0
Nodes (1): AblFoldingBuilder.kt — DO/END Folding

### Community 79 - "Module Group 79"
Cohesion: 1.0
Nodes (1): AblBracketMatcher.kt — Bracket Matching

### Community 80 - "Module Group 80"
Cohesion: 1.0
Nodes (1): AblCommenter.kt — Line and Block Comments

### Community 81 - "Module Group 81"
Cohesion: 1.0
Nodes (1): SyntaxError.kt — Error DTO

### Community 82 - "Module Group 82"
Cohesion: 1.0
Nodes (1): AblAutoCaseTypedHandler.kt — Keyword Auto-casing

### Community 83 - "Module Group 83"
Cohesion: 1.0
Nodes (1): AblTemplateContextType.kt — Live Template Context

### Community 84 - "Module Group 84"
Cohesion: 1.0
Nodes (1): AblFindUsagesProvider.kt — Find Usages

### Community 85 - "Module Group 85"
Cohesion: 1.0
Nodes (1): AblNoUndoInspection.kt — NO-UNDO Warning + Quick Fix

### Community 86 - "Module Group 86"
Cohesion: 1.0
Nodes (1): AblFindNoLockInspection.kt — FIND Lock Warning

### Community 87 - "Module Group 87"
Cohesion: 1.0
Nodes (1): AblRunConfigurationType.kt — Run .p Files

### Community 88 - "Module Group 88"
Cohesion: 1.0
Nodes (1): AblActions.kt — Reindex and Config Actions

## Knowledge Gaps
- **65 isolated node(s):** `AblKeywordList`, `AblRange`, `Kind`, `AblSemanticResult`, `SyntaxError` (+60 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Module Group 67`** (2 nodes): `AblKeywordList`, `AblKeywordList.kt`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 68`** (2 nodes): `SyntaxError.kt`, `SyntaxError`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 69`** (2 nodes): `AblIcons`, `AblIcons.kt`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 70`** (2 nodes): `AblBuiltinDocs.kt — 92 Built-in Function Docs`, `AblDocumentationProvider.kt — Hover Documentation`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 71`** (1 nodes): `build.gradle.kts`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 72`** (1 nodes): `settings.gradle.kts`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 73`** (1 nodes): `AblLanguage.kt — ABL Language Singleton`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 74`** (1 nodes): `AblFileType.kt — ABL File Extensions`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 75`** (1 nodes): `AblPsiParser.kt — Flat PSI Tree`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 76`** (1 nodes): `AblHighlighterFactory.kt`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 77`** (1 nodes): `AblColorSettingsPage.kt — Editor Color Scheme`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 78`** (1 nodes): `AblFoldingBuilder.kt — DO/END Folding`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 79`** (1 nodes): `AblBracketMatcher.kt — Bracket Matching`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 80`** (1 nodes): `AblCommenter.kt — Line and Block Comments`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 81`** (1 nodes): `SyntaxError.kt — Error DTO`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 82`** (1 nodes): `AblAutoCaseTypedHandler.kt — Keyword Auto-casing`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 83`** (1 nodes): `AblTemplateContextType.kt — Live Template Context`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 84`** (1 nodes): `AblFindUsagesProvider.kt — Find Usages`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 85`** (1 nodes): `AblNoUndoInspection.kt — NO-UNDO Warning + Quick Fix`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 86`** (1 nodes): `AblFindNoLockInspection.kt — FIND Lock Warning`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 87`** (1 nodes): `AblRunConfigurationType.kt — Run .p Files`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 88`** (1 nodes): `AblActions.kt — Reindex and Config Actions`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Skill: abl-dev-context — ABL Architecture Reference` connect `Plugin Architecture Overview` to `Paperclip Agent Pipeline`?**
  _High betweenness centrality (0.003) - this node is a cross-community bridge._
- **Why does `AblDebugConnection` connect `Debug Connection` to `Built-in Documentation`?**
  _High betweenness centrality (0.002) - this node is a cross-community bridge._
- **What connects `AblKeywordList`, `AblRange`, `Kind` to the rest of the system?**
  _65 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Folding Builder Tests` be split into smaller, more focused modules?**
  _Cohesion score 0.05 - nodes in this community are weakly interconnected._
- **Should `Plugin Architecture Overview` be split into smaller, more focused modules?**
  _Cohesion score 0.09 - nodes in this community are weakly interconnected._
- **Should `Symbol Collection` be split into smaller, more focused modules?**
  _Cohesion score 0.07 - nodes in this community are weakly interconnected._
- **Should `Run Configuration` be split into smaller, more focused modules?**
  _Cohesion score 0.08 - nodes in this community are weakly interconnected._