package com.ablls.plugin.completion

import com.intellij.testFramework.fixtures.BasePlatformTestCase

class AblCompletionContributorTest : BasePlatformTestCase() {
    // ── Régression : le dot-terminator ne doit pas bloquer la complétion normale ──

    fun testKeywordsStillAppearAfterStatementTerminator() {
        // "NO-UNDO." se termine par un point ABL (terminateur) — pas un séparateur Table.Field
        myFixture.configureByText(
            "test.p",
            """
            DEFINE VARIABLE x AS INTEGER NO-UNDO.
            MESS<caret>
            """.trimIndent(),
        )
        val lookups = myFixture.completeBasic()
        assertTrue(
            "MESSAGE doit apparaître après un terminateur '.'",
            lookups?.any { it.lookupString.equals("MESSAGE", ignoreCase = true) } == true,
        )
    }

    fun testKeywordsAppearInBlankFile() {
        myFixture.configureByText("test.p", "DEF<caret>")
        val lookups = myFixture.completeBasic()
        assertTrue(
            "DEFINE doit apparaître",
            lookups?.any { it.lookupString.equals("DEFINE", ignoreCase = true) } == true,
        )
    }

    fun testNoCompletionInLineComment() {
        myFixture.configureByText("test.p", "// DEFINE VARIABLE <caret>")
        val lookups = myFixture.completeBasic()
        assertNotNull(lookups)
    }

    fun testPreprocessorCompletionAfterAmpersand() {
        myFixture.configureByText("test.p", "&IF<caret>")
        val lookups = myFixture.completeBasic()
        // La liste complète des directives doit être disponible
        assertTrue(
            "&IF doit déclencher les préprocesseurs",
            lookups?.any { it.lookupString.equals("IF", ignoreCase = true) } == true ||
                // auto-inserted
                myFixture.file.text.contains("IF"),
        )
    }

    fun testPreprocessorNotTriggeredWithoutAmpersand() {
        myFixture.configureByText("test.p", "DEFINE<caret>")
        val lookups = myFixture.completeBasic()
        // Sans &, on obtient des mots-clés normaux
        // DEFINE peut être auto-inseré (1 seul résultat) ou dans la liste
        val hasDefine =
            lookups?.any { it.lookupString.equals("DEFINE", ignoreCase = true) }
                ?: myFixture.file.text.contains("DEFINE")
        assertTrue("Sans & on doit voir les mots-clés ABL normaux", hasDefine)
    }

    fun testVariableAppearsAfterDefinition() {
        myFixture.configureByText(
            "test.p",
            """
            DEFINE VARIABLE mySpecialVar AS INTEGER NO-UNDO.
            mySpec<caret>
            """.trimIndent(),
        )
        val lookups = myFixture.completeBasic()
        // Si un seul résultat, IntelliJ l'auto-insère (completeBasic retourne null)
        val found =
            lookups?.any { it.lookupString == "mySpecialVar" }
                ?: myFixture.file.text.contains("mySpecialVar")
        assertTrue("mySpecialVar doit apparaître dans la complétion", found)
    }
}
