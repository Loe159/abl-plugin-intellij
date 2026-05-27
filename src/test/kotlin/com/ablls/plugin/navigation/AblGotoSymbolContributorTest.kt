package com.ablls.plugin.navigation

import com.ablls.plugin.core.AblProjectAnalysisService
import com.intellij.testFramework.fixtures.BasePlatformTestCase

class AblGotoSymbolContributorTest : BasePlatformTestCase() {
    fun testContributorReturnsProcedureNames() {
        // Indexer un fichier avec des symboles
        myFixture.configureByText(
            "procs.p",
            """
            PROCEDURE createCustomer:
            END PROCEDURE.
            PROCEDURE deleteCustomer:
            END PROCEDURE.
            DEFINE VARIABLE localVar AS INTEGER NO-UNDO.
            """.trimIndent(),
        )

        val service = project.getService(AblProjectAnalysisService::class.java)
        service.analyzeFile(myFixture.file.text, myFixture.file.virtualFile.url)

        val contributor = AblGotoSymbolContributor()
        val names = contributor.getNames(project, false)

        // Les procédures doivent être présentes
        assertTrue("createCustomer doit être indexé", names.any { it.equals("createCustomer", ignoreCase = true) })
        assertTrue("deleteCustomer doit être indexé", names.any { it.equals("deleteCustomer", ignoreCase = true) })
        // Les variables locales ne doivent PAS apparaître dans Go to Symbol
        assertFalse("localVar ne doit pas apparaître", names.any { it == "localVar" })
    }

    fun testGetItemsByNameReturnNavigationItems() {
        myFixture.configureByText(
            "funcs.p",
            """
            FUNCTION calcTax RETURNS DECIMAL (INPUT amount AS DECIMAL):
                RETURN amount * 0.2.
            END FUNCTION.
            """.trimIndent(),
        )

        val service = project.getService(AblProjectAnalysisService::class.java)
        service.analyzeFile(myFixture.file.text, myFixture.file.virtualFile.url)

        val contributor = AblGotoSymbolContributor()
        val items = contributor.getItemsByName("calcTax", "calcTax", project, false)

        assertTrue("Au moins un item pour calcTax", items.isNotEmpty())
        assertEquals("calcTax", items[0].name)
        assertNotNull("Presentation ne doit pas être null", items[0].presentation)
    }

    fun testClassContributorFiltersOnlyClasses() {
        myFixture.configureByText(
            "svc.cls",
            """
            CLASS CustomerService:
                METHOD PUBLIC VOID create():
                END METHOD.
            END CLASS.
            """.trimIndent(),
        )

        val service = project.getService(AblProjectAnalysisService::class.java)
        service.analyzeFile(myFixture.file.text, myFixture.file.virtualFile.url)

        val classContributor = AblGotoClassContributor()
        val names = classContributor.getNames(project, false)

        assertTrue("CustomerService doit être indexé", names.any { it.equals("CustomerService", ignoreCase = true) })
        assertFalse("create (méthode) ne doit pas apparaître dans gotoClass", names.any { it == "create" })
    }
}
