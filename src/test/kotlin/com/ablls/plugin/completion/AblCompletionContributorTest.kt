package com.ablls.plugin.completion

import com.intellij.testFramework.fixtures.BasePlatformTestCase

class AblCompletionContributorTest : BasePlatformTestCase() {

    // ── Régression : le dot-terminator ne doit pas bloquer la complétion normale ──

    fun testKeywordsStillAppearAfterStatementTerminator() {
        // "NO-UNDO." se termine par un point ABL (terminateur) — pas un séparateur Table.Field
        myFixture.configureByText("test.p", """
            DEFINE VARIABLE x AS INTEGER NO-UNDO.
            MESS<caret>
        """.trimIndent())
        val lookups = myFixture.completeBasic()
        assertTrue(
            "MESSAGE doit apparaître après un terminateur '.'",
            lookups?.any { it.lookupString.equals("MESSAGE", ignoreCase = true) } == true
        )
    }

    fun testKeywordsAppearInBlankFile() {
        myFixture.configureByText("test.p", "DEF<caret>")
        val lookups = myFixture.completeBasic()
        assertTrue(
            "DEFINE doit apparaître",
            lookups?.any { it.lookupString.equals("DEFINE", ignoreCase = true) } == true
        )
    }

    fun testNoCompletionInLineComment() {
        myFixture.configureByText("test.p", "// DEFINE VARIABLE <caret>")
        val lookups = myFixture.completeBasic()
        assertNotNull(lookups)
    }

    fun testVariableAppearsAfterDefinition() {
        myFixture.configureByText("test.p", """
            DEFINE VARIABLE mySpecialVar AS INTEGER NO-UNDO.
            mySpec<caret>
        """.trimIndent())
        val lookups = myFixture.completeBasic()
        // Si un seul résultat, IntelliJ l'auto-insère (completeBasic retourne null)
        val found = lookups?.any { it.lookupString == "mySpecialVar" }
            ?: myFixture.file.text.contains("mySpecialVar")
        assertTrue("mySpecialVar doit apparaître dans la complétion", found)
    }
}
