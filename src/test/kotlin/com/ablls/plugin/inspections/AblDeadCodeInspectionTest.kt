package com.ablls.plugin.inspections

import com.intellij.testFramework.fixtures.BasePlatformTestCase

/**
 * Tests for [AblDeadCodeInspection] — procedure/function never referenced in file.
 *
 * Uses WEAK_WARNING level → checkHighlighting(false, false, true).
 * Procedure name length = 9 chars so highlight coincides with "PROCEDURE" at col 0.
 */
class AblDeadCodeInspectionTest : BasePlatformTestCase() {

    override fun setUp() {
        super.setUp()
        myFixture.enableInspections(AblDeadCodeInspection::class.java)
    }

    fun testUnreferencedProcedureTriggersWeakWarning() {
        // "unusedFoo" has 9 chars = "PROCEDURE".length → highlight covers "PROCEDURE"
        myFixture.configureByText("test.p", """<weak_warning>PROCEDURE</weak_warning> unusedFoo:
END PROCEDURE.""")
        myFixture.checkHighlighting(false, false, true)
    }

    fun testProcedureCalledViaRunProducesNoWarning() {
        myFixture.configureByText("test.p", """PROCEDURE usedProc:
END PROCEDURE.
RUN usedProc.""")
        myFixture.checkHighlighting(false, false, true)
    }

    fun testMultipleProceduresOnlyUnreferencedFlagged() {
        // usedFooX (9 chars) is called, unusedBar (9 chars) is not
        myFixture.configureByText("test.p", """PROCEDURE usedFooX:
END PROCEDURE.
<weak_warning>PROCEDURE</weak_warning> unusedBar:
END PROCEDURE.
RUN usedFooX.""")
        myFixture.checkHighlighting(false, false, true)
    }
}
