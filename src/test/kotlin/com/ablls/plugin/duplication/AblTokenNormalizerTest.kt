package com.ablls.plugin.duplication

import com.ablls.plugin.core.AblParserFacade
import org.junit.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class AblTokenNormalizerTest {

    private val facade = AblParserFacade()

    private fun normalize(code: String): List<AblTokenNormalizer.NormalToken> {
        val tokens = facade.parse(code, "test.p").tokens ?: error("no token stream")
        return AblTokenNormalizer.normalize(tokens)
    }

    @Test
    fun `different quoted strings produce identical normalized streams`() {
        val a = normalize("""MESSAGE "foo".""").map { it.text }
        val b = normalize("""MESSAGE "bar".""").map { it.text }
        assertEquals(a, b)
    }

    @Test
    fun `single-quoted strings are also normalized to STR`() {
        val withDouble = normalize("""MESSAGE "hello".""").map { it.text }
        val withSingle = normalize("MESSAGE 'hello'.").map { it.text }
        assertEquals(withDouble, withSingle)
    }

    @Test
    fun `different numeric literals produce identical normalized streams`() {
        val a = normalize("DEFINE VARIABLE x AS INTEGER NO-UNDO. x = 1.").map { it.text }
        val b = normalize("DEFINE VARIABLE x AS INTEGER NO-UNDO. x = 999.").map { it.text }
        assertEquals(a, b)
    }

    @Test
    fun `string literals collapse to STR token`() {
        val tokens = normalize("""MESSAGE "hello".""")
        assertTrue(tokens.any { it.text == "<STR>" }, "Expected <STR> token")
        assertTrue(tokens.none { it.text.startsWith("\"") }, "Raw string must not appear")
    }

    @Test
    fun `numeric literals collapse to NUM token`() {
        val tokens = normalize("DEFINE VARIABLE x AS INTEGER NO-UNDO. x = 42.")
        assertTrue(tokens.any { it.text == "<NUM>" }, "Expected <NUM> token")
        assertTrue(tokens.none { it.text == "42" }, "Raw number must not appear")
    }

    @Test
    fun `keywords are uppercased`() {
        val tokens = normalize("DEFINE VARIABLE x AS INTEGER NO-UNDO.")
        assertTrue(tokens.any { it.text == "DEFINE" })
        assertTrue(tokens.any { it.text == "VARIABLE" })
    }

    @Test
    fun `comments are excluded from output`() {
        val with    = normalize("/* a comment */ DEFINE VARIABLE x AS INTEGER NO-UNDO.")
        val without = normalize("DEFINE VARIABLE x AS INTEGER NO-UNDO.")
        assertEquals(with.map { it.text }, without.map { it.text })
    }

    @Test
    fun `decimal literal is handled without crash`() {
        // ABL period ambiguity: proparse may or may not produce NUMBER for 3.14
        // This test documents actual behaviour — do not assert a specific token.
        val tokens = normalize("PROCEDURE p: DEFINE VARIABLE r AS DECIMAL NO-UNDO. r = 3.14. END PROCEDURE.")
        assertTrue(tokens.isNotEmpty())
    }
}
