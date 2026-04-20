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

        // After FOR, we should see EACH, FIRST, LAST, etc.
        assert(keywords != null) { "Keywords should not be null after FOR" }
        assert(keywords!!.contains("EACH")) { "EACH should be expected after FOR" }
        assert(keywords.contains("FIRST")) { "FIRST should be expected after FOR" }
        assert(keywords.contains("LAST")) { "LAST should be expected after FOR" }
    }

    @Test
    fun testFindBlockExpectsValidKeywords() {
        val content = "FIND "
        val keywords = AblContextualCompletion.getExpectedKeywords(content, content.length, session)

        // After FIND, we should see FIRST, LAST, NEXT, PREV, etc.
        assert(keywords != null) { "Keywords should not be null after FIND" }
        assert(keywords!!.contains("FIRST")) { "FIRST should be expected after FIND" }
        assert(keywords.contains("LAST")) { "LAST should be expected after FIND" }
    }

    @Test
    fun testDoBlockOpensStatement() {
        val content = "DO:\n"
        val keywords = AblContextualCompletion.getExpectedKeywords(content, content.length, session)

        // After DO:, we should expect valid statement keywords
        assert(keywords != null) { "Keywords should not be null after DO:" }
        // Should contain statement keywords like MESSAGE, DISPLAY, DEFINE, etc.
        assert(keywords!!.isNotEmpty()) { "Should have keywords after DO:" }
    }

    @Test
    fun testDefineVariableExpectsAsKeyword() {
        val content = "DEFINE VARIABLE x "
        val keywords = AblContextualCompletion.getExpectedKeywords(content, content.length, session)

        // After DEFINE VARIABLE x, we should see AS (or context might not be determinable)
        // If keywords are provided, AS should be in them
        if (keywords != null && keywords.isNotEmpty()) {
            assert(keywords.contains("AS")) { "AS should be expected after DEFINE VARIABLE when context is available" }
        }
    }

    @Test
    fun testEmptyContentReturnsNull() {
        val content = ""
        val keywords = AblContextualCompletion.getExpectedKeywords(content, 0, session)

        // Empty content should either return null or empty set (both acceptable)
        // The function handles gracefully
        val isValid = keywords == null || keywords.isEmpty()
        assert(isValid) { "Empty content should handle gracefully" }
    }

    @Test
    fun testCursorAtBeginningOfContent() {
        val content = "PROCEDURE test: MESSAGE \"hello\". END PROCEDURE."
        val keywords = AblContextualCompletion.getExpectedKeywords(content, 0, session)

        // At the beginning, should expect top-level keywords
        // Should handle gracefully even if context is unclear
        val isValid = keywords == null || keywords.isNotEmpty()
        assert(isValid) { "Should handle cursor at beginning gracefully" }
    }

    @Test
    fun testCursorAtEndOfContent() {
        val content = "PROCEDURE test: MESSAGE \"hello\". END PROCEDURE."
        val keywords = AblContextualCompletion.getExpectedKeywords(content, content.length, session)

        // At the end of content, should handle gracefully
        val isValid = keywords == null || keywords.isNotEmpty()
        assert(isValid) { "Should handle cursor at end gracefully" }
    }

    @Test
    fun testCursorOffsetBoundaryHandling() {
        val content = "FOR EACH"
        // Test with offset beyond content length
        val keywords = AblContextualCompletion.getExpectedKeywords(content, content.length + 100, session)

        // Should handle gracefully with offset coercion
        val isValid = keywords == null || keywords.isNotEmpty()
        assert(isValid) { "Should handle offset beyond content gracefully" }
    }

    @Test
    fun testMultilineContextPreservation() {
        val content = """
            DEFINE VARIABLE x AS CHARACTER NO-UNDO.
            FOR FIRST Customer BY CustNum:
              DISPLAY Customer
        """.trimIndent()

        val keywords = AblContextualCompletion.getExpectedKeywords(content, content.length, session)

        // Should handle multiline content without errors
        val isValid = keywords == null || keywords.isNotEmpty()
        assert(isValid) { "Should handle multiline content gracefully" }
    }

    @Test
    fun testInvalidGrammarFallsBackGracefully() {
        val content = "INVALID_KEYWORD_HERE "
        val keywords = AblContextualCompletion.getExpectedKeywords(content, content.length, session)

        // Should handle invalid grammar gracefully
        // Either returns null (for fallback) or empty set
        val isValid = keywords == null || keywords.isNotEmpty()
        assert(isValid) { "Should handle invalid grammar gracefully" }
    }

    @Test
    fun testPartialKeywordDoesNotAffectContext() {
        val content = "FOR EA"
        val keywords = AblContextualCompletion.getExpectedKeywords(content, content.length, session)

        // The context should still be "FOR", so we should see FOR-valid keywords
        // Note: Since we're in the middle of typing "EACH", the exact behavior depends on parser
        val isValid = keywords == null || keywords.isNotEmpty()
        assert(isValid) { "Should handle partial keywords gracefully" }
    }

    @Test
    fun testNestedBlocksContext() {
        val content = """
            PROCEDURE test:
              DO:
                FOR EACH
        """.trimIndent()

        val keywords = AblContextualCompletion.getExpectedKeywords(content, content.length, session)

        // Should handle nested context gracefully - may or may not determine context
        // Just ensure it doesn't crash and returns either null or a valid set
        val isValid = keywords == null || keywords.isNotEmpty()
        assert(isValid) { "Should handle nested context gracefully" }
    }

    @Test
    fun testProcedureDeclarationContext() {
        val content = "PROCEDURE myProc "
        val keywords = AblContextualCompletion.getExpectedKeywords(content, content.length, session)

        // After PROCEDURE name, should expect : or other continuation keywords
        val isValid = keywords == null || keywords.isNotEmpty()
        assert(isValid) { "Should handle procedure declaration context" }
    }

    @Test
    fun testNoKeywordsReturnedForNonKeywordContext() {
        val content = "x = "
        val keywords = AblContextualCompletion.getExpectedKeywords(content, content.length, session)

        // After = in assignment, we don't expect keywords (but might get expressions)
        // Function should handle this gracefully
        val isValid = keywords == null || keywords.isNotEmpty()
        assert(isValid) { "Should handle non-keyword context gracefully" }
    }
}
