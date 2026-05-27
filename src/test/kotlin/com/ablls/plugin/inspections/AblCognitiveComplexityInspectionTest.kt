package com.ablls.plugin.inspections

import com.ablls.plugin.core.AblParserFacade
import com.intellij.testFramework.fixtures.BasePlatformTestCase
import org.prorefactor.core.ABLNodeType

class AblCognitiveComplexityInspectionTest : BasePlatformTestCase() {
    override fun setUp() {
        super.setUp()
        myFixture.enableInspections(AblCognitiveComplexityInspection::class.java)
    }

    // ─── Diagnostic : vérifie que topNode est bien un IStatementBlock ───────────

    fun testTopNodeIsStatementBlock() {
        val facade = AblParserFacade()
        val code = """PROCEDURE foo:
    IF a THEN MESSAGE "".
END PROCEDURE."""
        val result = facade.parse(code, "test.p")
        val topNode = result.topNode
        assertNotNull("topNode must not be null", topNode)
        assertTrue("topNode must be IStatementBlock", topNode!!.isIStatementBlock)

        val procNodes = topNode.queryStateHead(ABLNodeType.PROCEDURE)
        assertFalse("PROCEDURE node must be found", procNodes.isEmpty())
        assertTrue("PROCEDURE node must be IStatementBlock", procNodes[0].isIStatementBlock)
    }

    fun testHighComplexityProcedureTriggersWeakWarning() {
        // 10 levels of nesting: 1+2+…+10 = 55 >> threshold(15)
        myFixture.configureByText(
            "test.p",
            """<weak_warning>PROCEDURE</weak_warning> complexProc:
    IF a1 THEN DO:
        IF a2 THEN DO:
            IF a3 THEN DO:
                IF a4 THEN DO:
                    IF a5 THEN DO:
                        IF a6 THEN DO:
                            IF a7 THEN DO:
                                IF a8 THEN DO:
                                    IF a9 THEN DO:
                                        IF a10 THEN MESSAGE "deep".
                                    END.
                                END.
                            END.
                        END.
                    END.
                END.
            END.
        END.
    END.
END PROCEDURE.""",
        )
        myFixture.checkHighlighting(false, false, true)
    }

    fun testSimpleProcedureProducesNoWeakWarning() {
        myFixture.configureByText(
            "test.p",
            """PROCEDURE simpleProc:
    IF a THEN MESSAGE "yes".
    IF b THEN MESSAGE "no".
END PROCEDURE.""",
        )
        myFixture.checkHighlighting(false, false, true)
    }
}
