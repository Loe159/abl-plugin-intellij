package com.ablls.plugin.navigation

import com.ablls.plugin.core.AblProjectAnalysisService
import com.intellij.lang.cacheBuilder.DefaultWordsScanner
import com.intellij.openapi.components.service
import com.intellij.testFramework.fixtures.BasePlatformTestCase

/**
 * Tests des méthodes de métadonnées de [AblFindUsagesProvider].
 *
 * Ces tests vérifient : canFindUsagesFor, getWordsScanner, getType, getNodeText,
 * getDescriptiveName. Ils ne vérifient PAS que Find Usages trouve effectivement toutes
 * les occurrences (cela nécessite l'infrastructure complète IntelliJ : index de fichiers,
 * résolution PsiReference) — le comportement de recherche réel repose sur le text fallback
 * d'IntelliJ guidé par getWordsScanner.
 */
class AblFindUsagesProviderTest : BasePlatformTestCase() {
    private val provider = AblFindUsagesProvider()

    // ─── canFindUsagesFor ─────────────────────────────────────────────────────

    fun testCanFindUsagesForIdentifier() {
        myFixture.configureByText("test.p", "DEFINE VARIABLE my<caret>Var AS INTEGER NO-UNDO.")
        val element = myFixture.file.findElementAt(myFixture.caretOffset)
        assertNotNull(element)
        assertTrue("Should accept IDENTIFIER element in ABL file", provider.canFindUsagesFor(element!!))
    }

    fun testCanFindUsagesForKeywordDef() {
        myFixture.configureByText("test.p", "<caret>DEFINE VARIABLE myVar AS INTEGER NO-UNDO.")
        val element = myFixture.file.findElementAt(myFixture.caretOffset)
        assertNotNull(element)
        assertTrue("Should accept KEYWORD_DEF element (DEFINE) in ABL file", provider.canFindUsagesFor(element!!))
    }

    fun testCannotFindUsagesForWhitespace() {
        myFixture.configureByText("test.p", "DEFINE<caret> VARIABLE myVar AS INTEGER NO-UNDO.")
        val element = myFixture.file.findElementAt(myFixture.caretOffset)
        // Whitespace element type is not in the accepted list
        if (element != null) {
            assertFalse("Should reject whitespace element", provider.canFindUsagesFor(element))
        }
    }

    fun testCannotFindUsagesForBlockComment() {
        myFixture.configureByText("test.p", "/* my<caret>Var */")
        val element = myFixture.file.findElementAt(myFixture.caretOffset)
        assertNotNull(element)
        assertFalse("Should reject element inside block comment", provider.canFindUsagesFor(element!!))
    }

    // ─── getWordsScanner ─────────────────────────────────────────────────────

    fun testGetWordsScannerReturnsDefaultWordsScanner() {
        val scanner = provider.getWordsScanner()
        assertNotNull("getWordsScanner() must return a non-null scanner", scanner)
        assertTrue(
            "Scanner should be DefaultWordsScanner (uses AblLexerAdapter for ABL-aware tokenization)",
            scanner is DefaultWordsScanner,
        )
    }

    // ─── getType ─────────────────────────────────────────────────────────────

    fun testGetTypeReturnsVariableForDefinedVar() {
        myFixture.configureByText("test.p", "DEFINE VARIABLE my<caret>Var AS INTEGER NO-UNDO.")
        val service = project.service<AblProjectAnalysisService>()
        service.analyzeFile(myFixture.file.text, myFixture.file.virtualFile.url)

        val element = myFixture.file.findElementAt(myFixture.caretOffset)!!
        val type = provider.getType(element)
        assertEquals("variable", type)
    }

    fun testGetTypeReturnsProcedureForDefinedProcedure() {
        myFixture.configureByText("test.p", "PROCEDURE my<caret>Proc:\nEND PROCEDURE.")
        val service = project.service<AblProjectAnalysisService>()
        service.analyzeFile(myFixture.file.text, myFixture.file.virtualFile.url)

        val element = myFixture.file.findElementAt(myFixture.caretOffset)!!
        val type = provider.getType(element)
        assertEquals("procedure", type)
    }

    fun testGetTypeReturnsSymbolForUnknownElement() {
        myFixture.configureByText("test.p", "un<caret>knownThing = 5.")
        // No analysis done — index and semantic cache both empty
        val element = myFixture.file.findElementAt(myFixture.caretOffset)!!
        val type = provider.getType(element)
        assertEquals("symbol", type)
    }

    // ─── getNodeText / getDescriptiveName ─────────────────────────────────────

    fun testGetNodeTextReturnsElementText() {
        myFixture.configureByText("test.p", "DEFINE VARIABLE my<caret>Var AS INTEGER NO-UNDO.")
        val element = myFixture.file.findElementAt(myFixture.caretOffset)!!
        assertEquals("myVar", provider.getNodeText(element, false))
        assertEquals("myVar", provider.getNodeText(element, true))
    }

    fun testGetDescriptiveNameReturnsElementText() {
        myFixture.configureByText("test.p", "DEFINE VARIABLE my<caret>Var AS INTEGER NO-UNDO.")
        val element = myFixture.file.findElementAt(myFixture.caretOffset)!!
        assertEquals("myVar", provider.getDescriptiveName(element))
    }
}
