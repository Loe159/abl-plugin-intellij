package com.ablls.plugin.inspections

import com.intellij.testFramework.fixtures.BasePlatformTestCase

class AblFortranOperatorsInspectionTest : BasePlatformTestCase() {
    override fun setUp() {
        super.setUp()
        myFixture.enableInspections(AblFortranOperatorsInspection::class.java)
    }

    fun testFortranEqOperatorTriggersWarning() {
        myFixture.configureByText(
            "test.p",
            """IF x <warning descr="Deprecated Fortran-style operator 'eq' — use '=' instead">EQ</warning> 5 THEN MESSAGE "yes".""",
        )
        myFixture.checkHighlighting(true, false, false)
    }

    fun testModernEqualityOperatorProducesNoWarning() {
        myFixture.configureByText("test.p", """IF x = 5 THEN MESSAGE "yes".""")
        myFixture.checkHighlighting(true, false, false)
    }

    fun testQuickFixReplacesEqWithModernEqualsSign() {
        myFixture.configureByText("test.p", """IF x <caret>EQ 5 THEN MESSAGE "yes".""")
        val fix =
            myFixture.getAllQuickFixes()
                .firstOrNull { it.familyName == "Replace 'eq' with '='" }
        assertNotNull("Quick fix should be available for EQ operator", fix)
        myFixture.launchAction(fix!!)
        myFixture.checkResult("""IF x = 5 THEN MESSAGE "yes".""")
    }
}
