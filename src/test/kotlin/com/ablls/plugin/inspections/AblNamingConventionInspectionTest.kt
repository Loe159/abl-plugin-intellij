package com.ablls.plugin.inspections

import com.intellij.testFramework.fixtures.BasePlatformTestCase

/**
 * Tests for [AblNamingConventionInspection] — Hungarian-notation prefix check.
 *
 * Uses WEAK_WARNING level → checkHighlighting(false, false, true).
 * Inspection highlights the variable name token.
 */
class AblNamingConventionInspectionTest : BasePlatformTestCase() {
    override fun setUp() {
        super.setUp()
        myFixture.enableInspections(AblNamingConventionInspection::class.java)
    }

    fun testIntegerWithoutPrefixTriggersWeakWarning() {
        myFixture.configureByText(
            "test.p",
            "DEFINE VARIABLE <weak_warning>myCount</weak_warning> AS INTEGER NO-UNDO.",
        )
        myFixture.checkHighlighting(false, false, true)
    }

    fun testCharacterWithoutPrefixTriggersWeakWarning() {
        myFixture.configureByText(
            "test.p",
            "DEFINE VARIABLE <weak_warning>myName</weak_warning> AS CHARACTER NO-UNDO.",
        )
        myFixture.checkHighlighting(false, false, true)
    }

    fun testIntegerWithCorrectPrefixProducesNoWarning() {
        myFixture.configureByText(
            "test.p",
            "DEFINE VARIABLE iCount AS INTEGER NO-UNDO.",
        )
        myFixture.checkHighlighting(false, false, true)
    }

    fun testCharacterWithCorrectPrefixProducesNoWarning() {
        myFixture.configureByText(
            "test.p",
            "DEFINE VARIABLE cName AS CHARACTER NO-UNDO.",
        )
        myFixture.checkHighlighting(false, false, true)
    }

    fun testLogicalWithBPrefixProducesNoWarning() {
        myFixture.configureByText(
            "test.p",
            "DEFINE VARIABLE bIsActive AS LOGICAL NO-UNDO.",
        )
        myFixture.checkHighlighting(false, false, true)
    }

    fun testUnderscorePrefixIsIgnored() {
        myFixture.configureByText(
            "test.p",
            "DEFINE VARIABLE _internal AS INTEGER NO-UNDO.",
        )
        myFixture.checkHighlighting(false, false, true)
    }

    fun testSingleLetterVariableIsIgnored() {
        myFixture.configureByText(
            "test.p",
            "DEFINE VARIABLE i AS INTEGER NO-UNDO.",
        )
        myFixture.checkHighlighting(false, false, true)
    }

    fun testGlobalPrefixIsIgnored() {
        myFixture.configureByText(
            "test.p",
            "DEFINE VARIABLE giMyGlobal AS INTEGER NO-UNDO.",
        )
        myFixture.checkHighlighting(false, false, true)
    }
}
