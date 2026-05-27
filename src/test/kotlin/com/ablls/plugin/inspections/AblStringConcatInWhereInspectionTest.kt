package com.ablls.plugin.inspections

import com.intellij.testFramework.fixtures.BasePlatformTestCase

class AblStringConcatInWhereInspectionTest : BasePlatformTestCase() {
    override fun setUp() {
        super.setUp()
        myFixture.enableInspections(AblStringConcatInWhereInspection::class.java)
    }

    fun testPlusInWhereClauseTriggersWarning() {
        myFixture.configureByText(
            "test.p",
            """FOR EACH Customer WHERE Customer.Name = "Mr." <warning descr="String concatenation (+) in WHERE clause disables index usage — evaluate expression before the query">+</warning> lastName NO-LOCK:
END.""",
        )
        myFixture.checkHighlighting(true, false, false)
    }

    fun testPlusOutsideWhereClauseProducesNoWarning() {
        myFixture.configureByText(
            "test.p",
            """DEFINE VARIABLE fullName AS CHARACTER NO-UNDO.
fullName = "Mr." + lastName.""",
        )
        myFixture.checkHighlighting(true, false, false)
    }
}
