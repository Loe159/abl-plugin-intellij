package com.ablls.plugin.inspections

import com.intellij.testFramework.fixtures.BasePlatformTestCase

/**
 * Tests for [AblCyclomaticComplexityInspection] — McCabe CC > 10.
 *
 * Uses WEAK_WARNING level → checkHighlighting(false, false, true).
 * Inspection highlights "PROCEDURE" or "FUNCTION" keyword (9 chars at col 0).
 */
class AblCyclomaticComplexityInspectionTest : BasePlatformTestCase() {

    override fun setUp() {
        super.setUp()
        myFixture.enableInspections(AblCyclomaticComplexityInspection::class.java)
    }

    fun testHighComplexityProcedureTriggersWeakWarning() {
        // 11 IF branches → CC = 1 + 11 = 12 > threshold(10)
        myFixture.configureByText("test.p", """<weak_warning>PROCEDURE</weak_warning> complexProc:
    IF a1 THEN MESSAGE "1".
    IF a2 THEN MESSAGE "2".
    IF a3 THEN MESSAGE "3".
    IF a4 THEN MESSAGE "4".
    IF a5 THEN MESSAGE "5".
    IF a6 THEN MESSAGE "6".
    IF a7 THEN MESSAGE "7".
    IF a8 THEN MESSAGE "8".
    IF a9 THEN MESSAGE "9".
    IF a10 THEN MESSAGE "10".
    IF a11 THEN MESSAGE "11".
END PROCEDURE.""")
        myFixture.checkHighlighting(false, false, true)
    }

    fun testSimpleProcedureProducesNoWeakWarning() {
        myFixture.configureByText("test.p", """PROCEDURE simpleProc:
    IF a THEN MESSAGE "yes".
    IF b THEN MESSAGE "no".
END PROCEDURE.""")
        myFixture.checkHighlighting(false, false, true)
    }

    fun testEmptyProcedureProducesNoWeakWarning() {
        myFixture.configureByText("test.p", """PROCEDURE emptyProc:
END PROCEDURE.""")
        myFixture.checkHighlighting(false, false, true)
    }
}
