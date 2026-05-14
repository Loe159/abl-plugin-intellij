package com.ablls.plugin.inspections

import com.intellij.testFramework.fixtures.BasePlatformTestCase

/**
 * Tests for [AblUnlabeledLoopControlInspection] — LEAVE/NEXT without label in nested loop.
 *
 * Uses WARNING level → checkHighlighting(true, false, false).
 * Inspection highlights the LEAVE or NEXT keyword.
 */
class AblUnlabeledLoopControlInspectionTest : BasePlatformTestCase() {

    override fun setUp() {
        super.setUp()
        myFixture.enableInspections(AblUnlabeledLoopControlInspection::class.java)
    }

    fun testLeaveInNestedDoLoopTriggersWarning() {
        myFixture.configureByText("test.p", """DO:
  DO:
    <warning descr="LEAVE without label in nested loop — add a block label to make the target loop explicit">LEAVE</warning>.
  END.
END.""")
        myFixture.checkHighlighting(true, false, false)
    }

    fun testNextInNestedDoLoopTriggersWarning() {
        myFixture.configureByText("test.p", """DO:
  DO:
    <warning descr="NEXT without label in nested loop — add a block label to make the target loop explicit">NEXT</warning>.
  END.
END.""")
        myFixture.checkHighlighting(true, false, false)
    }

    fun testLeaveWithLabelInNestedLoopProducesNoWarning() {
        myFixture.configureByText("test.p", """outerLoop:
DO:
  DO:
    LEAVE outerLoop.
  END.
END.""")
        myFixture.checkHighlighting(true, false, false)
    }

    fun testLeaveInSimpleDoLoopProducesNoWarning() {
        myFixture.configureByText("test.p", """DO:
  LEAVE.
END.""")
        myFixture.checkHighlighting(true, false, false)
    }
}
