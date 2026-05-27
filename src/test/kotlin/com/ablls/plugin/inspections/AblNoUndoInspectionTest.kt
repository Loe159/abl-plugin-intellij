package com.ablls.plugin.inspections

import com.intellij.testFramework.fixtures.BasePlatformTestCase

class AblNoUndoInspectionTest : BasePlatformTestCase() {
    override fun setUp() {
        super.setUp()
        myFixture.enableInspections(AblNoUndoInspection::class.java)
    }

    fun testDefineVariableWithoutNoUndoTriggersWarning() {
        myFixture.configureByText(
            "test.p",
            """<warning descr="Missing NO-UNDO modifier on VARIABLE (affects performance)">DEFINE</warning> VARIABLE iCount AS INTEGER.""",
        )
        myFixture.checkHighlighting(true, false, false)
    }

    fun testDefineVariableWithNoUndoProducesNoWarning() {
        myFixture.configureByText("test.p", "DEFINE VARIABLE iCount AS INTEGER NO-UNDO.")
        myFixture.checkHighlighting(true, false, false)
    }

    fun testQuickFixAddsNoUndoToVariable() {
        myFixture.configureByText("test.p", "<caret>DEFINE VARIABLE iCount AS INTEGER.")
        val fix =
            myFixture.getAllQuickFixes()
                .firstOrNull { it.familyName == "Add NO-UNDO to variable" }
        assertNotNull("Quick fix 'Add NO-UNDO to variable' should be available", fix)
        myFixture.launchAction(fix!!)
        myFixture.checkResult("DEFINE VARIABLE iCount AS INTEGER NO-UNDO.")
    }
}
