package com.ablls.plugin.navigation

import com.ablls.plugin.parser.AblTokenTypes
import com.intellij.psi.PsiElement
import com.intellij.psi.tree.IElementType
import com.intellij.testFramework.fixtures.BasePlatformTestCase

/**
 * Tests for [AblBreadcrumbProvider] — structured-PSI block navigation.
 *
 * With composite block nodes in the PSI tree, breadcrumbs are driven by the real
 * parent chain rather than text-based sibling scanning.
 */
class AblBreadcrumbProviderTest : BasePlatformTestCase() {

    private val provider = AblBreadcrumbProvider()

    // ─── acceptElement ────────────────────────────────────────────────────────

    fun testAcceptsProcedureBlock() {
        myFixture.configureByText("test.p", "PROCEDURE foo: END PROCEDURE.")
        val block = topLevelBlock(AblTokenTypes.PROCEDURE_BLOCK)
        assertNotNull("Should find PROCEDURE_BLOCK", block)
        assertTrue("PROCEDURE_BLOCK should be accepted as breadcrumb", provider.acceptElement(block!!))
    }

    fun testAcceptsDoBlock() {
        myFixture.configureByText("test.p", "DO: END.")
        val block = topLevelBlock(AblTokenTypes.DO_BLOCK)
        assertNotNull("Should find DO_BLOCK", block)
        assertTrue("DO_BLOCK should be accepted as breadcrumb", provider.acceptElement(block!!))
    }

    fun testRejectsLeafToken() {
        myFixture.configureByText("test.p", "DEFINE VARIABLE x AS INTEGER NO-UNDO.")
        // A leaf token (non-block) should not be accepted
        val leaf = myFixture.file.firstChild
        assertNotNull("File must have children", leaf)
        assertFalse("Leaf token should NOT be accepted as breadcrumb", provider.acceptElement(leaf!!))
    }

    // ─── getParent ────────────────────────────────────────────────────────────

    fun testGetParentOfTopLevelBlockIsNull() {
        myFixture.configureByText("test.p", "PROCEDURE foo: END PROCEDURE.")
        val block = topLevelBlock(AblTokenTypes.PROCEDURE_BLOCK)
        assertNotNull("Must find PROCEDURE_BLOCK", block)
        val parent = provider.getParent(block!!)
        assertNull("Top-level PROCEDURE_BLOCK should have no parent breadcrumb", parent)
    }

    fun testGetParentOfLeafInsideProcedureIsProcedureBlock() {
        myFixture.configureByText("test.p",
            "PROCEDURE foo:\n  DEFINE VARIABLE x AS INTEGER NO-UNDO.\nEND PROCEDURE.")
        val block = topLevelBlock(AblTokenTypes.PROCEDURE_BLOCK)
        assertNotNull("Must find PROCEDURE_BLOCK", block)
        // A leaf inside the procedure block
        val leaf = firstLeafInside(block!!)
        assertNotNull("Block must have leaf children", leaf)
        val parent = provider.getParent(leaf!!)
        assertNotNull("Leaf inside PROCEDURE_BLOCK should have a breadcrumb parent", parent)
        assertEquals("Parent breadcrumb should be PROCEDURE_BLOCK",
            AblTokenTypes.PROCEDURE_BLOCK, parent!!.node.elementType)
    }

    fun testGetParentOfDoBlockInsideProcedureIsProcedureBlock() {
        myFixture.configureByText("test.p",
            "PROCEDURE foo:\n  DO:\n  END.\nEND PROCEDURE.")
        val procBlock = topLevelBlock(AblTokenTypes.PROCEDURE_BLOCK)
        assertNotNull("Must find PROCEDURE_BLOCK", procBlock)
        val doBlock = firstChildBlock(procBlock!!, AblTokenTypes.DO_BLOCK)
        assertNotNull("Must find DO_BLOCK inside PROCEDURE_BLOCK", doBlock)
        val parent = provider.getParent(doBlock!!)
        assertNotNull("DO_BLOCK should have PROCEDURE_BLOCK as parent", parent)
        assertEquals("Parent of DO_BLOCK should be PROCEDURE_BLOCK",
            AblTokenTypes.PROCEDURE_BLOCK, parent!!.node.elementType)
    }

    fun testGetParentOfLeafInsideNestedDoBlock() {
        myFixture.configureByText("test.p",
            "PROCEDURE foo:\n  DO:\n    DEFINE VARIABLE x AS INTEGER NO-UNDO.\n  END.\nEND PROCEDURE.")
        val procBlock = topLevelBlock(AblTokenTypes.PROCEDURE_BLOCK)
        assertNotNull("Must find PROCEDURE_BLOCK", procBlock)
        val doBlock = firstChildBlock(procBlock!!, AblTokenTypes.DO_BLOCK)
        assertNotNull("Must find DO_BLOCK inside PROCEDURE_BLOCK", doBlock)

        // Leaf inside DO_BLOCK → parent is DO_BLOCK
        val leaf = firstLeafInside(doBlock!!)
        assertNotNull("DO_BLOCK must have leaf children", leaf)
        val doParent = provider.getParent(leaf!!)
        assertNotNull("Leaf inside DO_BLOCK should have parent", doParent)
        assertEquals("Immediate parent breadcrumb should be DO_BLOCK",
            AblTokenTypes.DO_BLOCK, doParent!!.node.elementType)

        // DO_BLOCK's parent → PROCEDURE_BLOCK
        val procParent = provider.getParent(doParent)
        assertNotNull("DO_BLOCK should have PROCEDURE_BLOCK as parent", procParent)
        assertEquals("DO_BLOCK's parent should be PROCEDURE_BLOCK",
            AblTokenTypes.PROCEDURE_BLOCK, procParent!!.node.elementType)
    }

    // ─── getElementInfo ───────────────────────────────────────────────────────

    fun testGetElementInfoForProcedureIncludesName() {
        myFixture.configureByText("test.p", "PROCEDURE calculateTotal: END PROCEDURE.")
        val block = topLevelBlock(AblTokenTypes.PROCEDURE_BLOCK)
        assertNotNull("Must find PROCEDURE_BLOCK", block)
        val info = provider.getElementInfo(block!!)
        assertTrue("Info should start with PROCEDURE", info.startsWith("PROCEDURE"))
        assertTrue("Info should contain the procedure name", info.contains("calculateTotal"))
    }

    fun testGetElementInfoForDoBlockIsJustDo() {
        myFixture.configureByText("test.p", "DO: END.")
        val block = topLevelBlock(AblTokenTypes.DO_BLOCK)
        assertNotNull("Must find DO_BLOCK", block)
        val info = provider.getElementInfo(block!!)
        assertEquals("DO block info should be 'DO'", "DO", info)
    }

    // ─── helpers ─────────────────────────────────────────────────────────────

    /** Returns the first top-level child of the file with the given composite element type. */
    private fun topLevelBlock(type: IElementType): PsiElement? {
        var el: PsiElement? = myFixture.file.firstChild
        while (el != null) {
            if (el.node.elementType == type) return el
            el = el.nextSibling
        }
        return null
    }

    /** Returns the first direct child of [parent] with the given composite element type. */
    private fun firstChildBlock(parent: PsiElement, type: IElementType): PsiElement? {
        var el: PsiElement? = parent.firstChild
        while (el != null) {
            if (el.node.elementType == type) return el
            el = el.nextSibling
        }
        return null
    }

    /** Returns the first leaf (no children) inside a composite block. */
    private fun firstLeafInside(block: PsiElement): PsiElement? {
        fun search(el: PsiElement): PsiElement? {
            if (el.firstChild == null) return el
            var child = el.firstChild
            while (child != null) {
                val found = search(child)
                if (found != null) return found
                child = child.nextSibling
            }
            return null
        }
        // Start from second child (skip the block-opening keyword itself at position 0)
        return block.firstChild?.nextSibling?.let { search(it) }
    }
}
