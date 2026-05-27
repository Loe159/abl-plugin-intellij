package com.ablls.plugin.inspections

import com.intellij.testFramework.fixtures.BasePlatformTestCase

class AblUnusedVariableInspectionTest : BasePlatformTestCase() {
    override fun setUp() {
        super.setUp()
        myFixture.enableInspections(AblUnusedVariableInspection::class.java)
    }

    fun testDefinedButNeverReadVariableTriggersWarning() {
        myFixture.configureByText(
            "test.p",
            """DEFINE VARIABLE <warning descr="Variable 'iCount' is defined but never read">iCount</warning> AS INTEGER NO-UNDO.""",
        )
        myFixture.checkHighlighting(true, false, false)
    }

    fun testVariableUsedAfterDefinitionProducesNoWarning() {
        myFixture.configureByText(
            "test.p",
            """DEFINE VARIABLE iCount AS INTEGER NO-UNDO.
iCount = 1.
MESSAGE iCount.""",
        )
        myFixture.checkHighlighting(true, false, false)
    }
}
