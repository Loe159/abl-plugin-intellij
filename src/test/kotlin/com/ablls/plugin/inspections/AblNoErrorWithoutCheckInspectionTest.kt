package com.ablls.plugin.inspections

import com.intellij.testFramework.fixtures.BasePlatformTestCase

class AblNoErrorWithoutCheckInspectionTest : BasePlatformTestCase() {
    override fun setUp() {
        super.setUp()
        myFixture.enableInspections(AblNoErrorWithoutCheckInspection::class.java)
    }

    fun testFindWithNoErrorAndNoCheckTriggersWarning() {
        myFixture.configureByText(
            "test.p",
            """FIND Customer WHERE Customer.CustNum = 1 <warning descr="NO-ERROR used without subsequent ERROR-STATUS:ERROR, AVAILABLE or RETURN-VALUE check — errors will be silently ignored">NO-ERROR</warning>.
MESSAGE "done".""",
        )
        myFixture.checkHighlighting(true, false, false)
    }

    fun testFindWithNoErrorFollowedByCheckProducesNoWarning() {
        myFixture.configureByText(
            "test.p",
            """FIND Customer WHERE Customer.CustNum = 1 NO-ERROR.
IF NOT AVAILABLE Customer THEN MESSAGE "not found".""",
        )
        myFixture.checkHighlighting(true, false, false)
    }
}
