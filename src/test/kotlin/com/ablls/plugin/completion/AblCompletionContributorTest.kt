package com.ablls.plugin.completion

import com.ablls.plugin.core.AblBuiltinDocs
import com.ablls.plugin.core.AblProparseKeywords
import org.junit.Test

/**
 * Tests for AblCompletionContributor.
 * Validates that the proparse-derived keyword set is available and correct.
 */
class AblCompletionContributorTest {

    @Test
    fun testProparseKeywordSetIsNotEmpty() {
        val keywords = AblProparseKeywords.ALL
        assert(keywords.isNotEmpty()) { "Proparse keyword set should not be empty" }
        assert(keywords.size > 100) { "Expected 100+ keywords from proparse, got ${keywords.size}" }
    }

    @Test
    fun testEssentialKeywordsPresent() {
        val keywords = AblProparseKeywords.ALL
        assert("FOR" in keywords) { "FOR keyword should be in proparse set" }
        assert("PROCEDURE" in keywords) { "PROCEDURE keyword should be in proparse set" }
        assert("END" in keywords) { "END keyword should be in proparse set" }
        assert("EACH" in keywords) { "EACH keyword should be in proparse set" }
        assert("FIND" in keywords) { "FIND keyword should be in proparse set" }
        assert("DEFINE" in keywords) { "DEFINE keyword should be in proparse set" }
    }

    @Test
    fun testBuiltinDocumentationAvailable() {
        assert(AblBuiltinDocs.has("LENGTH")) { "LENGTH builtin documentation should be available" }
        assert(AblBuiltinDocs.has("SUBSTRING")) { "SUBSTRING builtin documentation should be available" }
        assert(AblBuiltinDocs.has("MESSAGE")) { "MESSAGE builtin documentation should be available" }
    }
}
