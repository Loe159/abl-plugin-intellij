package com.ablls.plugin.core

import org.junit.Test

class PrintMethodsTest {
    @Test
    fun testParse() {
        val snippet =
            """
            DEFINE VARIABLE oBuilder AS System.Text.StringBuilder NO-UNDO.
            oBuilder = NEW System.Text.StringBuilder().
            """.trimIndent()

        val facade = AblParserFacade()
        val result = facade.parse(snippet, "test.p")
        println("=== ERRORS ===")
        result.syntaxErrors.forEach { println("${it.line + 1}:${it.column} ${it.message}") }
        println("=== END ERRORS ===")
    }
}
