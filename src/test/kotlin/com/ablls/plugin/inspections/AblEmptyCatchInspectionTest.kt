package com.ablls.plugin.inspections

import com.intellij.testFramework.fixtures.BasePlatformTestCase

class AblEmptyCatchInspectionTest : BasePlatformTestCase() {
    override fun setUp() {
        super.setUp()
        myFixture.enableInspections(AblEmptyCatchInspection::class.java)
    }

    fun testEmptyCatchBlockTriggersWarning() {
        // proparse 3.7.2 cannot parse dotted class names (e.g. Progress.Lang.Error)
        // in CATCH clauses without a syntax error — use a simple identifier instead.
        myFixture.configureByText(
            "test.p",
            """DO ON ERROR UNDO, THROW:
    RUN someProc.
<warning descr="Empty CATCH block silently swallows exceptions — add error handling or logging">CATCH</warning> eFoo AS AppError:
END.""",
        )
        myFixture.checkHighlighting(true, false, false)
    }

    fun testCatchBlockWithHandlingProducesNoWarning() {
        myFixture.configureByText(
            "test.p",
            """DO ON ERROR UNDO, THROW:
    RUN someProc.
CATCH eFoo AS AppError:
    MESSAGE "error handled".
END.""",
        )
        myFixture.checkHighlighting(true, false, false)
    }
}
