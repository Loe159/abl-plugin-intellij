package com.ablls.plugin.navigation

import com.ablls.plugin.core.AblProjectAnalysisService
import com.intellij.openapi.components.service
import com.intellij.testFramework.fixtures.BasePlatformTestCase

class AblGotoDeclarationHandlerTest : BasePlatformTestCase() {
    private val handler = AblGotoDeclarationHandler()

    // ─── Navigation vers la définition ───────────────────────────────────────

    fun testNavigatesToDefinitionOnSameLine() {
        myFixture.configureByText("test.p", "DEFINE VARIABLE myVar AS INTEGER NO-UNDO.\nmy<caret>Var = 5.")
        prewarmSemantic()

        val targets = callHandler()
        assertNotNull("Expected navigation targets for defined symbol", targets)
        val targetLine = myFixture.editor.document.getLineNumber(targets!![0].textOffset)
        assertEquals("Should navigate to DEFINE line (line 0)", 0, targetLine)
    }

    fun testNavigatesToProcedureDefinition() {
        myFixture.configureByText(
            "test.p",
            "PROCEDURE myProc:\nEND PROCEDURE.\nRUN my<caret>Proc.",
        )
        prewarmSemantic()

        val targets = callHandler()
        assertNotNull("Expected navigation target for procedure reference", targets)
        val targetLine = myFixture.editor.document.getLineNumber(targets!![0].textOffset)
        assertEquals("Should navigate to PROCEDURE line (line 0)", 0, targetLine)
    }

    // ─── Discrimination de scope (THE key semantic test) ─────────────────────

    fun testScopeDiscriminationPrefersLocalVariable() {
        myFixture.configureByText(
            "test.p",
            """
            DEFINE VARIABLE myVar AS INTEGER NO-UNDO.
            PROCEDURE foo:
              DEFINE VARIABLE myVar AS INTEGER NO-UNDO.
              my<caret>Var = 5.
            END PROCEDURE.
            """.trimIndent(),
        )
        prewarmSemantic()

        val targets = callHandler()
        assertNotNull("Expected navigation target inside procedure scope", targets)
        val targetLine = myFixture.editor.document.getLineNumber(targets!![0].textOffset)
        assertEquals(
            "Semantic resolution must navigate to local myVar (line 2), not global (line 0)",
            2,
            targetLine,
        )
    }

    // ─── Fallback sur l'index quand la sémantique n'est pas disponible ──────

    fun testIndexFallbackNavigatesToDefinitionWithoutSemanticResult() {
        myFixture.configureByText("test.p", "DEFINE VARIABLE myVar AS INTEGER NO-UNDO.\nmy<caret>Var = 5.")
        // Syntactic analysis only — index is populated but semanticCache is empty
        val service = project.service<AblProjectAnalysisService>()
        service.analyzeFile(myFixture.file.text, myFixture.file.virtualFile.url)

        val targets = callHandler()
        assertNotNull("Index fallback should return a target for a defined symbol", targets)
        val targetLine = myFixture.editor.document.getLineNumber(targets!![0].textOffset)
        assertEquals("Index fallback should navigate to definition (line 0)", 0, targetLine)
    }

    fun testReturnsNullWhenFileNeverAnalyzed() {
        myFixture.configureByText("test.p", "DEFINE VARIABLE myVar AS INTEGER NO-UNDO.\nmy<caret>Var = 5.")
        // No analysis at all — both semantic cache and index are empty
        val targets = callHandler()
        assertNull("Should return null when no analysis has ever been done for the file", targets)
    }

    // ─── Cas négatifs ─────────────────────────────────────────────────────────

    fun testReturnsNullForUndefinedSymbol() {
        myFixture.configureByText("test.p", "un<caret>knownSymbol = 5.")
        prewarmSemantic()

        val targets = callHandler()
        assertNull("Should return null for symbol with no definition", targets)
    }

    // ─── Helpers ──────────────────────────────────────────────────────────────

    private fun prewarmSemantic() {
        val service = project.service<AblProjectAnalysisService>()
        service.analyzeFileSemantic(myFixture.file.text, myFixture.file.virtualFile.url)
    }

    private fun callHandler(): Array<out com.intellij.psi.PsiElement>? {
        val element = myFixture.file.findElementAt(myFixture.caretOffset) ?: return null
        return handler.getGotoDeclarationTargets(element, myFixture.caretOffset, myFixture.editor)
    }
}
