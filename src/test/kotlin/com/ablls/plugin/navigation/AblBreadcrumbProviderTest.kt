package com.ablls.plugin.navigation

import com.intellij.psi.PsiElement
import com.intellij.testFramework.fixtures.BasePlatformTestCase

/**
 * Tests for [AblBreadcrumbProvider.getParent] — text-based scope traversal with flat PSI.
 */
class AblBreadcrumbProviderTest : BasePlatformTestCase() {

    private val provider = AblBreadcrumbProvider()

    // ─── acceptElement ────────────────────────────────────────────────────────

    fun testAcceptsBlockOpenerKeywords() {
        myFixture.configureByText("test.p", "PROCEDURE foo: END PROCEDURE.")
        val procToken = siblingNamed("PROCEDURE")
        assertNotNull("Should find PROCEDURE token", procToken)
        assertTrue("PROCEDURE token should be accepted as breadcrumb", provider.acceptElement(procToken!!))
    }

    fun testRejectsNonBlockToken() {
        myFixture.configureByText("test.p", "DEFINE VARIABLE x AS INTEGER NO-UNDO.")
        val defineToken = siblingNamed("DEFINE")
        assertNotNull("Should find DEFINE token", defineToken)
        assertFalse("DEFINE token should NOT be accepted as breadcrumb", provider.acceptElement(defineToken!!))
    }

    // ─── getParent ────────────────────────────────────────────────────────────

    fun testGetParentReturnsNullAtTopLevel() {
        myFixture.configureByText("test.p", "DEFINE VARIABLE x AS INTEGER NO-UNDO.")
        val first = myFixture.file.firstChild ?: return
        val parent = provider.getParent(first)
        assertNull("Top-level token should have no parent breadcrumb", parent)
    }

    fun testGetParentReturnsEnclosingProcedure() {
        myFixture.configureByText("test.p",
            "PROCEDURE foo:\n  DEFINE VARIABLE x AS INTEGER NO-UNDO.\nEND PROCEDURE.")
        val defineToken = siblingNamed("DEFINE")
        assertNotNull("Must find DEFINE token inside PROCEDURE", defineToken)

        val parent = provider.getParent(defineToken!!)
        assertNotNull("DEFINE inside PROCEDURE should have a breadcrumb parent", parent)
        assertEquals("Parent breadcrumb should be PROCEDURE", "PROCEDURE", parent!!.text.trim().uppercase())
    }

    fun testGetParentOfProcedureTokenIsNull() {
        myFixture.configureByText("test.p", "PROCEDURE foo:\nEND PROCEDURE.")
        val procToken = siblingNamed("PROCEDURE")
        assertNotNull("Must find PROCEDURE token", procToken)
        val parent = provider.getParent(procToken!!)
        assertNull("Top-level PROCEDURE should have no parent breadcrumb", parent)
    }

    fun testGetParentWithNestedDoBlock() {
        myFixture.configureByText("test.p",
            "PROCEDURE foo:\n  DO:\n    DEFINE VARIABLE x AS INTEGER NO-UNDO.\n  END.\nEND PROCEDURE.")
        val defineToken = siblingNamed("DEFINE")
        assertNotNull("Must find DEFINE inside DO block", defineToken)

        val doParent = provider.getParent(defineToken!!)
        assertNotNull("DEFINE inside DO should have DO as breadcrumb parent", doParent)
        assertEquals("Immediate parent should be DO", "DO", doParent!!.text.trim().uppercase())

        val procParent = provider.getParent(doParent)
        assertNotNull("DO should have PROCEDURE as parent", procParent)
        assertEquals("DO's parent should be PROCEDURE", "PROCEDURE", procParent!!.text.trim().uppercase())
    }

    fun testEndProcedureQualifierDoesNotPushNewBlock() {
        myFixture.configureByText("test.p",
            "PROCEDURE foo:\nEND PROCEDURE.\nDEFINE VARIABLE x AS INTEGER NO-UNDO.")
        val defineToken = siblingNamed("DEFINE")
        assertNotNull("Must find DEFINE after END PROCEDURE.", defineToken)

        val parent = provider.getParent(defineToken!!)
        assertNull("DEFINE after END PROCEDURE. should have no breadcrumb parent", parent)
    }

    // ─── getElementInfo ───────────────────────────────────────────────────────

    fun testGetElementInfoForProcedureIncludesName() {
        myFixture.configureByText("test.p", "PROCEDURE calculateTotal: END PROCEDURE.")
        val procToken = siblingNamed("PROCEDURE")
        assertNotNull("Must find PROCEDURE token", procToken)
        val info = provider.getElementInfo(procToken!!)
        assertTrue("Info should start with PROCEDURE", info.startsWith("PROCEDURE"))
        assertTrue("Info should contain the procedure name", info.contains("calculateTotal"))
    }

    fun testGetElementInfoForDoBlock() {
        myFixture.configureByText("test.p", "DO: END.")
        val doToken = siblingNamed("DO")
        assertNotNull("Must find DO token", doToken)
        val info = provider.getElementInfo(doToken!!)
        assertEquals("DO block info should be 'DO'", "DO", info)
    }

    // ─── helpers ─────────────────────────────────────────────────────────────

    private fun siblingNamed(name: String): PsiElement? {
        var el: PsiElement? = myFixture.file.firstChild
        while (el != null) {
            if (el.text.trim().uppercase() == name) return el
            el = el.nextSibling
        }
        return null
    }
}
