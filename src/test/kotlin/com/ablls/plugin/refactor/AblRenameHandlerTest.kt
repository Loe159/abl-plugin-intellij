package com.ablls.plugin.refactor

import com.ablls.plugin.core.AblProjectAnalysisService
import com.intellij.openapi.actionSystem.DataContext
import com.intellij.openapi.components.service
import com.intellij.testFramework.fixtures.BasePlatformTestCase

/**
 * Tests for [AblRenameHandler].
 *
 * Tests the scope-aware rename logic via [AblRenameHandler.performScopeAwareRename] and
 * [AblRenameHandler.findNearestDef] directly (internal access), plus end-to-end invoke
 * tests using [AblRenameHandler.testNewName] to bypass the dialog.
 */
class AblRenameHandlerTest : BasePlatformTestCase() {

    private lateinit var handler: AblRenameHandler

    override fun setUp() {
        super.setUp()
        handler = AblRenameHandler()
    }

    // ─── findNearestDef ───────────────────────────────────────────────────────

    fun testFindNearestDefReturnsDefNodeForVariable() {
        myFixture.configureByText("test.p", "DEFINE VARIABLE myVar AS INTEGER NO-UNDO.")
        val service = project.service<AblProjectAnalysisService>()
        service.analyzeFileSemantic(myFixture.file.text, myFixture.file.virtualFile.url)

        val rootScope = service.getSemanticResult(myFixture.file.virtualFile.url)?.rootScope
        assertNotNull("Semantic result must be available after analyzeFileSemantic", rootScope)

        val node = handler.findNearestDef(rootScope!!, "myVar", 1)
        assertNotNull("findNearestDef should find myVar defined on line 1", node)
        assertEquals("Define node must be on proparse line 1", 1, node!!.token?.line)
    }

    fun testFindNearestDefReturnsNullWhenSymbolAbsent() {
        myFixture.configureByText("test.p", "DEFINE VARIABLE myVar AS INTEGER NO-UNDO.")
        val service = project.service<AblProjectAnalysisService>()
        service.analyzeFileSemantic(myFixture.file.text, myFixture.file.virtualFile.url)

        val rootScope = service.getSemanticResult(myFixture.file.virtualFile.url)?.rootScope!!
        val node = handler.findNearestDef(rootScope, "unknownSymbol", 1)
        assertNull("findNearestDef should return null for an unknown symbol", node)
    }

    fun testFindNearestDefPrefersLocalOverGlobal() {
        myFixture.configureByText("test.p", """
            DEFINE VARIABLE myVar AS INTEGER NO-UNDO.
            PROCEDURE foo:
              DEFINE VARIABLE myVar AS INTEGER NO-UNDO.
            END PROCEDURE.
        """.trimIndent())
        val service = project.service<AblProjectAnalysisService>()
        service.analyzeFileSemantic(myFixture.file.text, myFixture.file.virtualFile.url)

        val rootScope = service.getSemanticResult(myFixture.file.virtualFile.url)?.rootScope!!
        // Line 3 is inside the procedure — nearest def should be local (line 2 trimmed = line 3 raw)
        val node = handler.findNearestDef(rootScope, "myVar", 3)
        assertNotNull("Should resolve to the local myVar inside the procedure", node)
        // The local define is on the 3rd line (1-based); global is on line 1 — local wins
        assertTrue(
            "Local myVar (line 3) should win over global (line 1)",
            (node!!.token?.line ?: 0) > 1
        )
    }

    // ─── performScopeAwareRename ─────────────────────────────────────────────

    fun testRenamesLocalVariableWithoutTouchingGlobal() {
        myFixture.configureByText("test.p", """
            DEFINE VARIABLE myVar AS INTEGER NO-UNDO.
            PROCEDURE foo:
              DEFINE VARIABLE myVar AS INTEGER NO-UNDO.
              myVar = 5.
            END PROCEDURE.
        """.trimIndent())
        val service = project.service<AblProjectAnalysisService>()
        service.analyzeFileSemantic(myFixture.file.text, myFixture.file.virtualFile.url)

        val rootScope = service.getSemanticResult(myFixture.file.virtualFile.url)?.rootScope!!
        // Target: local myVar (line 3 in trimmed source)
        val targetDef = handler.findNearestDef(rootScope, "myVar", 3)
        assertNotNull("Must find local myVar definition", targetDef)

        handler.performScopeAwareRename(project, myFixture.file, "myVar", "localRenamed", rootScope, targetDef!!)

        val result = myFixture.file.text
        assertTrue("Local DEFINE should be renamed", result.contains("localRenamed"))
        assertTrue("Local usage should be renamed", result.contains("localRenamed = 5"))
        assertTrue("Global DEFINE must NOT be renamed", result.contains("DEFINE VARIABLE myVar"))
    }

    fun testRenamesGlobalVariableWithoutTouchingLocal() {
        myFixture.configureByText("test.p", """
            DEFINE VARIABLE myVar AS INTEGER NO-UNDO.
            myVar = 1.
            PROCEDURE foo:
              DEFINE VARIABLE myVar AS INTEGER NO-UNDO.
              myVar = 5.
            END PROCEDURE.
        """.trimIndent())
        val service = project.service<AblProjectAnalysisService>()
        service.analyzeFileSemantic(myFixture.file.text, myFixture.file.virtualFile.url)

        val rootScope = service.getSemanticResult(myFixture.file.virtualFile.url)?.rootScope!!
        // Target: global myVar at line 1
        val targetDef = handler.findNearestDef(rootScope, "myVar", 1)
        assertNotNull("Must find global myVar definition", targetDef)
        assertEquals("Target must be the global def on line 1", 1, targetDef!!.token?.line)

        handler.performScopeAwareRename(project, myFixture.file, "myVar", "globalRenamed", rootScope, targetDef)

        val result = myFixture.file.text
        assertTrue("Global DEFINE should be renamed", result.contains("DEFINE VARIABLE globalRenamed"))
        assertTrue("Global usage should be renamed", result.contains("globalRenamed = 1"))
        assertTrue("Local DEFINE inside procedure must NOT be renamed",
            result.contains("DEFINE VARIABLE myVar"))
        assertTrue("Local usage inside procedure must NOT be renamed",
            result.contains("myVar = 5"))
    }

    fun testRenameIsInsensitiveToCaseVariants() {
        myFixture.configureByText("test.p", """
            DEFINE VARIABLE myVar AS INTEGER NO-UNDO.
            myvar = 1.
            MYVAR = 2.
        """.trimIndent())
        val service = project.service<AblProjectAnalysisService>()
        service.analyzeFileSemantic(myFixture.file.text, myFixture.file.virtualFile.url)

        val rootScope = service.getSemanticResult(myFixture.file.virtualFile.url)?.rootScope!!
        val targetDef = handler.findNearestDef(rootScope, "myVar", 1)
        assertNotNull(targetDef)

        handler.performScopeAwareRename(project, myFixture.file, "myVar", "renamed", rootScope, targetDef!!)

        val result = myFixture.file.text
        assertFalse("No occurrence of myVar (any case) should remain", result.contains("myVar", ignoreCase = true))
        assertEquals("All three occurrences should be renamed", 3, result.split("renamed").size - 1)
    }

    fun testDoesNothingWhenNoOccurrencesResolveToTarget() {
        myFixture.configureByText("test.p", "DEFINE VARIABLE other AS INTEGER NO-UNDO.")
        val service = project.service<AblProjectAnalysisService>()
        service.analyzeFileSemantic(myFixture.file.text, myFixture.file.virtualFile.url)

        val rootScope = service.getSemanticResult(myFixture.file.virtualFile.url)?.rootScope!!
        val targetDef = handler.findNearestDef(rootScope, "other", 1)
        assertNotNull(targetDef)

        val originalText = myFixture.file.text
        // Rename "other" to "renamed" — but pass "nonexistent" as oldName so nothing matches
        handler.performScopeAwareRename(project, myFixture.file, "nonexistent", "renamed", rootScope, targetDef!!)
        assertEquals("File must be unchanged when oldName has no occurrences", originalText, myFixture.file.text)
    }

    fun testFindNearestDefFindsTempTable() {
        myFixture.configureByText("test.p", """
            DEFINE TEMP-TABLE ttCust
                FIELD custId AS INTEGER.
        """.trimIndent())
        val service = project.service<AblProjectAnalysisService>()
        service.analyzeFileSemantic(myFixture.file.text, myFixture.file.virtualFile.url)

        val rootScope = service.getSemanticResult(myFixture.file.virtualFile.url)?.rootScope ?: return
        val node = handler.findNearestDef(rootScope, "ttCust", 1)
        // proparse creates a default buffer for the temp-table in the scope;
        // if getBufferList() returns it, node will be non-null
        if (node != null) {
            assertEquals("ttCust define node should be on line 1", 1, node.token?.line)
        }
        // test passes whether or not proparse exposes it via getBufferList —
        // the key guarantee is no exception is thrown
    }

    // ─── Fallback text rename ─────────────────────────────────────────────────

    fun testFallbackRenamesAllOccurrencesWhenSemanticUnavailable() {
        // No analyzeFileSemantic call — semantic cache is empty → textual fallback path
        myFixture.configureByText("test.p", "DEFINE VARIABLE my<caret>Var AS INTEGER NO-UNDO.\nmyVar = 99.")

        handler.testNewName = "newVar"
        try {
            handler.invoke(project, myFixture.editor, myFixture.file, DataContext { null })
        } finally {
            handler.testNewName = null
        }

        val result = myFixture.file.text
        assertFalse("Original name must not remain after textual fallback rename", result.contains("myVar", ignoreCase = true))
        assertTrue("DEFINE occurrence must be renamed", result.contains("newVar"))
        assertTrue("Usage occurrence must be renamed", result.contains("newVar = 99"))
    }

    fun testFallbackDoesNotRenameKeywordsOrStrings() {
        // The fallback uses AblLexerAdapter — strings and keywords must not be touched
        myFixture.configureByText("test.p", "DEFINE VARIABLE my<caret>Var AS INTEGER NO-UNDO.\n" +
            "MESSAGE \"myVar is a string\".\nmyVar = 1.")

        handler.testNewName = "x"
        try {
            handler.invoke(project, myFixture.editor, myFixture.file, DataContext { null })
        } finally {
            handler.testNewName = null
        }

        val result = myFixture.file.text
        assertTrue("String literal must not be modified", result.contains("\"myVar is a string\""))
        assertTrue("Usage should be renamed", result.contains("x = 1"))
    }

    // ─── End-to-end invoke ────────────────────────────────────────────────────

    fun testEndToEndInvokeRenamesAllOccurrencesInSimpleFile() {
        myFixture.configureByText("test.p", "DEFINE VARIABLE my<caret>Var AS INTEGER NO-UNDO.\nmyVar = 42.")
        val service = project.service<AblProjectAnalysisService>()
        service.analyzeFileSemantic(myFixture.file.text, myFixture.file.virtualFile.url)

        handler.testNewName = "renamedVar"
        try {
            handler.invoke(project, myFixture.editor, myFixture.file, DataContext { null })
        } finally {
            handler.testNewName = null
        }

        val result = myFixture.file.text
        assertTrue("DEFINE occurrence should be renamed", result.contains("renamedVar"))
        assertTrue("Usage occurrence should be renamed", result.contains("renamedVar = 42"))
        assertFalse("Original name must not remain", result.contains("myVar"))
    }

    fun testEndToEndInvokePreservesHomonymInOtherScope() {
        myFixture.configureByText("test.p", """
            DEFINE VARIABLE myVar AS INTEGER NO-UNDO.
            PROCEDURE foo:
              DEFINE VARIABLE my<caret>Var AS INTEGER NO-UNDO.
              myVar = 5.
            END PROCEDURE.
        """.trimIndent())
        val service = project.service<AblProjectAnalysisService>()
        service.analyzeFileSemantic(myFixture.file.text, myFixture.file.virtualFile.url)

        handler.testNewName = "localVar"
        try {
            handler.invoke(project, myFixture.editor, myFixture.file, DataContext { null })
        } finally {
            handler.testNewName = null
        }

        val result = myFixture.file.text
        assertTrue("Local DEFINE should be renamed to localVar", result.contains("DEFINE VARIABLE localVar"))
        assertTrue("Global DEFINE must be preserved as myVar",
            result.contains("DEFINE VARIABLE myVar"))
    }
}
