package com.ablls.plugin.inspections

import com.intellij.testFramework.fixtures.BasePlatformTestCase

/**
 * Tests for [AblFindFirstNoErrorInspection] — FIND FIRST/LAST without NO-ERROR.
 *
 * Uses WARNING level → checkHighlighting(true, false, false).
 * Inspection highlights "FIND" (4 chars at col 0).
 */
class AblFindFirstNoErrorInspectionTest : BasePlatformTestCase() {

    override fun setUp() {
        super.setUp()
        myFixture.enableInspections(AblFindFirstNoErrorInspection::class.java)
    }

    fun testFindFirstWithoutNoErrorTriggersWarning() {
        myFixture.configureByText("test.p",
            """<warning descr="FIND FIRST/LAST without NO-ERROR throws a fatal error when no record is found — add NO-ERROR and check AVAILABLE">FIND</warning> FIRST Customer WHERE Customer.CustNum = 1 NO-LOCK.""")
        myFixture.checkHighlighting(true, false, false)
    }

    fun testFindLastWithoutNoErrorTriggersWarning() {
        myFixture.configureByText("test.p",
            """<warning descr="FIND FIRST/LAST without NO-ERROR throws a fatal error when no record is found — add NO-ERROR and check AVAILABLE">FIND</warning> LAST Customer WHERE Customer.CustNum = 1 NO-LOCK.""")
        myFixture.checkHighlighting(true, false, false)
    }

    fun testFindFirstWithNoErrorProducesNoWarning() {
        myFixture.configureByText("test.p",
            "FIND FIRST Customer WHERE Customer.CustNum = 1 NO-LOCK NO-ERROR.")
        myFixture.checkHighlighting(true, false, false)
    }

    fun testQuickFixAddsNoError() {
        myFixture.configureByText("test.p",
            "<caret>FIND FIRST Customer WHERE Customer.CustNum = 1 NO-LOCK.")
        val fix = myFixture.getAllQuickFixes().firstOrNull { it.familyName == "Add NO-ERROR" }
        assertNotNull("Quick fix 'Add NO-ERROR' should be available", fix)
        myFixture.launchAction(fix!!)
        myFixture.checkResult(
            "FIND FIRST Customer WHERE Customer.CustNum = 1 NO-LOCK NO-ERROR.")
    }
}
