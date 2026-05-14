package com.ablls.plugin.inspections

import com.intellij.testFramework.fixtures.BasePlatformTestCase

/**
 * Tests for [AblIntegerOverflowInspection] — INTEGER variable with a name suggesting large values.
 *
 * Uses WEAK_WARNING level → checkHighlighting(false, false, true).
 * Inspection highlights the variable name token.
 */
class AblIntegerOverflowInspectionTest : BasePlatformTestCase() {

    override fun setUp() {
        super.setUp()
        myFixture.enableInspections(AblIntegerOverflowInspection::class.java)
    }

    fun testCountVariableTriggersWeakWarning() {
        myFixture.configureByText("test.p",
            "DEFINE VARIABLE <weak_warning>iCount</weak_warning> AS INTEGER NO-UNDO.")
        myFixture.checkHighlighting(false, false, true)
    }

    fun testTotalVariableTriggersWeakWarning() {
        myFixture.configureByText("test.p",
            "DEFINE VARIABLE <weak_warning>iTotal</weak_warning> AS INTEGER NO-UNDO.")
        myFixture.checkHighlighting(false, false, true)
    }

    fun testDecimalTypeProducesNoWarning() {
        myFixture.configureByText("test.p",
            "DEFINE VARIABLE iCount AS DECIMAL NO-UNDO.")
        myFixture.checkHighlighting(false, false, true)
    }

    fun testInt64TypeProducesNoWarning() {
        myFixture.configureByText("test.p",
            "DEFINE VARIABLE iCount AS INT64 NO-UNDO.")
        myFixture.checkHighlighting(false, false, true)
    }

    fun testNeutralNameProducesNoWarning() {
        myFixture.configureByText("test.p",
            "DEFINE VARIABLE iMyVar AS INTEGER NO-UNDO.")
        myFixture.checkHighlighting(false, false, true)
    }

    fun testMightOverflowHeuristicMatchesKnownHints() {
        assertTrue(AblIntegerOverflowInspection.mightOverflow("iCount"))
        assertTrue(AblIntegerOverflowInspection.mightOverflow("totalAmount"))
        assertTrue(AblIntegerOverflowInspection.mightOverflow("iByteSize"))
        assertFalse(AblIntegerOverflowInspection.mightOverflow("iMyVariable"))
        assertFalse(AblIntegerOverflowInspection.mightOverflow("cName"))
    }
}
