package com.ablls.plugin.core

import org.junit.Test
import org.prorefactor.refactor.settings.ProparseSettings
import org.prorefactor.core.schema.Schema
import org.prorefactor.proparse.ABLLexer
import org.prorefactor.proparse.Lexer
import org.prorefactor.proparse.PostLexer
import org.prorefactor.proparse.TokenList
import org.prorefactor.proparse.antlr4.Proparse
import java.nio.charset.StandardCharsets
import org.antlr.v4.runtime.*
import org.antlr.v4.runtime.tree.ParseTree

class PrintMethodsTest {

    @Test
    fun testParse() {
        val snippet = """
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
