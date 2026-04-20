package com.ablls.plugin.completion

import com.ablls.plugin.core.AblBuiltinDocs
import com.ablls.plugin.core.AblKeywordList
import org.junit.Test

/**
 * Tests for AblCompletionContributor.
 * Validates that keyword completion data is available.
 */
class AblCompletionContributorTest {

    @Test
    fun testKeywordListIsNotEmpty() {
        val keywords = AblKeywordList.KEYWORDS
        assert(keywords.isNotEmpty()) { "Keyword list should not be empty" }
    }

    @Test
    fun testEssentialKeywordsPresent() {
        val keywords = AblKeywordList.KEYWORDS
        assert(keywords.contains("FOR")) { "FOR keyword should be in list" }
        assert(keywords.contains("PROCEDURE")) { "PROCEDURE keyword should be in list" }
        assert(keywords.contains("END")) { "END keyword should be in list" }
    }

    @Test
    fun testBuiltinDocumentationAvailable() {
        assert(AblBuiltinDocs.has("LENGTH")) { "LENGTH builtin documentation should be available" }
        assert(AblBuiltinDocs.has("SUBSTRING")) { "SUBSTRING builtin documentation should be available" }
        assert(AblBuiltinDocs.has("MESSAGE")) { "MESSAGE builtin documentation should be available" }
    }
}
