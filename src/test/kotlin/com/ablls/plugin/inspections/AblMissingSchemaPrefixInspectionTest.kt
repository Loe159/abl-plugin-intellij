package com.ablls.plugin.inspections

import com.ablls.plugin.project.OpenEdgeProjectService
import com.intellij.testFramework.fixtures.BasePlatformTestCase
import java.io.File

class AblMissingSchemaPrefixInspectionTest : BasePlatformTestCase() {

    override fun setUp() {
        super.setUp()
        myFixture.enableInspections(AblMissingSchemaPrefixInspection::class.java)
    }

    override fun tearDown() {
        project.basePath?.let { File(it, "openedge-project.json").delete() }
        // Reload to reset config to default (0 databases) before the next test
        runCatching { project.getService(OpenEdgeProjectService::class.java).reload() }
        super.tearDown()
    }

    private fun setupMultiDb() {
        val basePath = project.basePath ?: return
        File(basePath).mkdirs()
        File(basePath, "openedge-project.json").writeText(
            """{"databases":[{"logicalName":"sports","database":"/data/sports"},{"logicalName":"empdb","database":"/data/empdb"}]}"""
        )
        project.getService(OpenEdgeProjectService::class.java).reload()
    }

    fun testTableWithoutPrefixInMultiDbEnvironmentTriggersWarning() {
        setupMultiDb()
        myFixture.configureByText(
            "test.p",
            // descr omitted — Set join order in the message is non-deterministic
            """FOR EACH <warning>Customer</warning> NO-LOCK:
END."""
        )
        myFixture.checkHighlighting(true, false, false)
    }

    fun testTableWithDatabasePrefixProducesNoWarning() {
        setupMultiDb()
        // sports.Customer has a NAMEDOT child — inspection must skip it
        myFixture.configureByText("test.p", "FOR EACH sports.Customer NO-LOCK:\nEND.")
        myFixture.checkHighlighting(true, false, false)
    }

    fun testInspectionIsInactiveWithSingleDatabase() {
        // No setupMultiDb() call — default config has 0 databases, inspection must not fire
        myFixture.configureByText("test.p", "FOR EACH Customer NO-LOCK:\nEND.")
        myFixture.checkHighlighting(true, false, false)
    }
}
