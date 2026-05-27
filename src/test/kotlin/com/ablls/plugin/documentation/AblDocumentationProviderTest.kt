package com.ablls.plugin.documentation

import com.ablls.plugin.core.AblProjectAnalysisService
import com.intellij.openapi.components.service
import com.intellij.testFramework.fixtures.BasePlatformTestCase

class AblDocumentationProviderTest : BasePlatformTestCase() {
    private val provider = AblDocumentationProvider()

    private fun prewarmSemantic() {
        val service = project.service<AblProjectAnalysisService>()
        service.analyzeFileSemantic(myFixture.file.text, myFixture.file.virtualFile.url)
    }

    private fun docAtWord(
        word: String,
        lastOccurrence: Boolean = true,
    ): String? {
        val text = myFixture.file.text
        val offset = if (lastOccurrence) text.lastIndexOf(word) else text.indexOf(word)
        assertTrue("Word '$word' not found in file", offset >= 0)
        val element = myFixture.file.findElementAt(offset) ?: return null
        return provider.generateDoc(element, element)
    }

    // ─── Chemin sémantique : Routine.getIDESignature ─────────────────────────

    fun testProcedureDocFromSemanticScope() {
        myFixture.configureByText(
            "test.p",
            """
            PROCEDURE myProc:
              DEFINE INPUT PARAMETER p1 AS INTEGER NO-UNDO.
              MESSAGE p1.
            END PROCEDURE.
            """.trimIndent(),
        )
        prewarmSemantic()

        // Semantic path must be taken — doc comes from scope, not just AblSymbol index
        val doc = docAtWord("myProc")
        assertNotNull("Expected doc from semantic scope for procedure", doc)
        assertTrue("Doc must mention the procedure name", doc!!.contains("myProc"))
    }

    fun testFunctionDocFromSemanticScope() {
        myFixture.configureByText(
            "test.p",
            """
            FUNCTION addNums RETURNS INTEGER (INPUT a AS INTEGER, INPUT b AS INTEGER):
              RETURN a + b.
            END FUNCTION.
            """.trimIndent(),
        )
        prewarmSemantic()

        val doc = docAtWord("addNums", lastOccurrence = false)
        assertNotNull("Expected doc from semantic scope for function", doc)
        assertTrue("Doc must mention the function name", doc!!.contains("addNums"))
    }

    // ─── Chemin sémantique : Variable avec EXTENT ─────────────────────────────

    fun testVariableWithExtentShowsExtent() {
        myFixture.configureByText(
            "test.p",
            """
            DEFINE VARIABLE arr AS INTEGER EXTENT 5 NO-UNDO.
            arr[1] = 42.
            """.trimIndent(),
        )
        prewarmSemantic()

        val doc = docAtWord("arr")
        assertNotNull("Expected doc for array variable", doc)
        assertTrue("Signature must include EXTENT", doc!!.contains("EXTENT"))
        assertTrue("Signature must include extent value", doc.contains("5"))
    }

    fun testVariableShowsDataType() {
        myFixture.configureByText(
            "test.p",
            """
            DEFINE VARIABLE myVar AS CHARACTER NO-UNDO.
            myVar = "hello".
            """.trimIndent(),
        )
        prewarmSemantic()

        val doc = docAtWord("myVar")
        assertNotNull("Expected doc for CHARACTER variable", doc)
        assertTrue("Doc must show data type", doc!!.contains("CHARACTER"))
    }

    // ─── Fallback : AblSymbol index sans résultat sémantique ─────────────────

    fun testFallsBackToSymbolIndexWithoutSemanticResult() {
        myFixture.configureByText(
            "test.p",
            "DEFINE VARIABLE myVar AS INTEGER NO-UNDO.\nmyVar = 1.",
        )
        // Analyse syntaxique uniquement — pas de résultat sémantique
        val service = project.service<AblProjectAnalysisService>()
        service.analyzeFile(myFixture.file.text, myFixture.file.virtualFile.url)

        val doc = docAtWord("myVar")
        assertNotNull("Should show doc from AblSymbol index when semantic is absent", doc)
        assertTrue("Fallback doc must mention variable name or type", doc!!.contains("myVar") || doc.contains("INTEGER"))
    }

    // ─── Fallback : built-ins ─────────────────────────────────────────────────

    fun testBuiltinFunctionDocumented() {
        myFixture.configureByText("test.p", """MESSAGE SUBSTRING("hello", 1, 3).""")

        val doc = docAtWord("SUBSTRING", lastOccurrence = false)
        assertNotNull("Expected doc for SUBSTRING built-in", doc)
    }
}
