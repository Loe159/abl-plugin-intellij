package com.ablls.plugin.inspections

import com.intellij.testFramework.fixtures.BasePlatformTestCase

class AblFindNoLockInspectionTest : BasePlatformTestCase() {
    override fun setUp() {
        super.setUp()
        myFixture.enableInspections(AblFindNoLockInspection::class.java)
    }

    fun testFindWithoutLockTriggersWarning() {
        val descr = "Missing lock modifier on FIND (defaults to SHARE-LOCK, which is often dangerous)."
        myFixture.configureByText(
            "test.p",
            """<warning descr="$descr">FIND</warning> Customer WHERE Customer.CustNum = 1.""",
        )
        myFixture.checkHighlighting(true, false, false)
    }

    fun testFindWithNoLockProducesNoWarning() {
        myFixture.configureByText("test.p", "FIND Customer WHERE Customer.CustNum = 1 NO-LOCK.")
        myFixture.checkHighlighting(true, false, false)
    }

    fun testQuickFixAddsNoLock() {
        myFixture.configureByText("test.p", "<caret>FIND Customer WHERE Customer.CustNum = 1.")
        val fix =
            myFixture.getAllQuickFixes()
                .firstOrNull { it.familyName == "Add NO-LOCK" }
        assertNotNull("Quick fix 'Add NO-LOCK' should be available", fix)
        myFixture.launchAction(fix!!)
        myFixture.checkResult("FIND Customer WHERE Customer.CustNum = 1 NO-LOCK.")
    }
}
