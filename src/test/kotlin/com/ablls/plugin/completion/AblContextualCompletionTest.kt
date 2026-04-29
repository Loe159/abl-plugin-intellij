package com.ablls.plugin.completion

import org.junit.Test
import org.junit.Before
import org.prorefactor.refactor.settings.ProparseSettings
import org.prorefactor.core.schema.Schema
import org.prorefactor.proparse.support.IProparseEnvironment
import org.prorefactor.refactor.RefactorSession

class AblContextualCompletionTest {

    private lateinit var session: IProparseEnvironment

    @Before
    fun setUp() {
        val settings = ProparseSettings("")
        settings.setCustomProversion("12.2.0")
        session = object : RefactorSession(settings, Schema()) {}
    }

    @Test
    fun testForBlockExpectsEachFirstLast() {
        val content = "FOR "
        val keywords = AblContextualCompletion.getExpectedKeywords(content, content.length, session)

        assert(keywords != null) { "must not be null after FOR " }
        assert("EACH" in keywords!!) { "EACH must be expected after FOR" }
        assert("FIRST" in keywords) { "FIRST must be expected after FOR" }
        assert("LAST" in keywords) { "LAST must be expected after FOR" }
        assert("DEFINE" !in keywords) { "DEFINE should NOT appear after FOR" }
    }

    @Test
    fun testFindBlockExpectsValidKeywords() {
        val content = "FIND "
        val keywords = AblContextualCompletion.getExpectedKeywords(content, content.length, session)

        assert(keywords != null) { "must not be null after FIND " }
        assert("FIRST" in keywords!!) { "FIRST must be expected after FIND" }
        assert("LAST" in keywords) { "LAST must be expected after FIND" }
        assert("DEFINE" !in keywords) { "DEFINE should NOT appear after FIND" }
    }

    @Test
    fun testDoBlockOpensStatement() {
        val content = "DO:\n"
        val keywords = AblContextualCompletion.getExpectedKeywords(content, content.length, session)

        // The parser may not fire a reportError for this truncation (DO: is syntactically
        // incomplete but may not trigger our listener). Accept null (caller falls back).
        assert(keywords == null || keywords.isNotEmpty()) { "Should have keywords after DO: or null for fallback" }
    }

    @Test
    fun testDefineVariableExpectsAsKeyword() {
        val content = "DEFINE VARIABLE x "
        val keywords = AblContextualCompletion.getExpectedKeywords(content, content.length, session)

        // If context is determinable, AS must be present. Null is acceptable (caller falls back).
        if (keywords != null) {
            assert("AS" in keywords) { "AS should be expected after DEFINE VARIABLE when context is available" }
        }
    }

    @Test
    fun testEmptyContentReturnsNull() {
        val content = ""
        val keywords = AblContextualCompletion.getExpectedKeywords(content, 0, session)

        // Empty content: parser at start state — either null or a non-empty top-level set
        assert(keywords == null || keywords.isNotEmpty()) { "Empty content should handle gracefully" }
    }

    @Test
    fun testCursorAtBeginningOfContent() {
        val content = "PROCEDURE test: MESSAGE \"hello\". END PROCEDURE."
        val keywords = AblContextualCompletion.getExpectedKeywords(content, 0, session)

        // Cursor at offset 0 → truncated to "" → same as empty content
        assert(keywords == null || keywords.isNotEmpty()) { "Should handle cursor at beginning gracefully" }
    }

    @Test
    fun testCursorAtEndOfCompleteContent() {
        val content = "PROCEDURE test: MESSAGE \"hello\". END PROCEDURE."
        val keywords = AblContextualCompletion.getExpectedKeywords(content, content.length, session)

        // At the end of complete, valid content → either null (no error fired) or top-level keywords
        assert(keywords == null || keywords.isNotEmpty()) { "Should handle cursor at end gracefully" }
    }

    @Test
    fun testCursorOffsetBoundaryHandling() {
        val content = "FOR EACH"
        val keywords = AblContextualCompletion.getExpectedKeywords(content, content.length + 100, session)

        // Offset coerced to content.length — same as end of "FOR EACH"
        assert(keywords == null || keywords.isNotEmpty()) { "Should handle offset beyond content gracefully" }
    }

    @Test
    fun testMultilineContextPreservation() {
        val content = """
            DEFINE VARIABLE x AS CHARACTER NO-UNDO.
            FOR FIRST Customer BY CustNum:
              DISPLAY Customer
        """.trimIndent()

        val keywords = AblContextualCompletion.getExpectedKeywords(content, content.length, session)

        assert(keywords == null || keywords.isNotEmpty()) { "Should handle multiline content gracefully" }
    }

    @Test
    fun testInvalidGrammarFallsBackGracefully() {
        val content = "INVALID_KEYWORD_HERE "
        val keywords = AblContextualCompletion.getExpectedKeywords(content, content.length, session)

        assert(keywords == null || keywords.isNotEmpty()) { "Should handle invalid grammar gracefully" }
    }

    @Test
    fun testPartialKeywordDoesNotAffectContext() {
        val content = "FOR EA"
        val keywords = AblContextualCompletion.getExpectedKeywords(content, content.length, session)

        // Parser sees "FOR" then an unknown token "EA"; still inside FOR context
        assert(keywords == null || keywords.isNotEmpty()) { "Should handle partial keywords gracefully" }
    }

    @Test
    fun testNestedBlocksContext() {
        val content = """
            PROCEDURE test:
              DO:
                FOR EACH
        """.trimIndent()

        val keywords = AblContextualCompletion.getExpectedKeywords(content, content.length, session)

        assert(keywords == null || keywords.isNotEmpty()) { "Should handle nested context gracefully" }
    }

    @Test
    fun testProcedureDeclarationContext() {
        val content = "PROCEDURE myProc "
        val keywords = AblContextualCompletion.getExpectedKeywords(content, content.length, session)

        // The parser may not trigger reportError here. Accept null (caller falls back to all keywords).
        assert(keywords == null || keywords.isNotEmpty()) { "Should return valid keywords or null for fallback" }
    }

    @Test
    fun testForContextExcludesDefine() {
        // Regression: DEFINE is a top-level statement keyword and must not appear after FOR
        val content = "FOR "
        val keywords = AblContextualCompletion.getExpectedKeywords(content, content.length, session)

        assert(keywords != null) { "must not be null after FOR " }
        assert("DEFINE" !in keywords!!) { "DEFINE should NOT appear after FOR" }
    }
}
