package com.ablls.plugin.project

import com.ablls.plugin.language.AblIcons
import com.intellij.ide.util.projectWizard.ModuleBuilder
import com.intellij.ide.util.projectWizard.ModuleWizardStep
import com.intellij.ide.util.projectWizard.SettingsStep
import com.intellij.openapi.module.EmptyModuleType
import com.intellij.openapi.module.ModuleType
import com.intellij.openapi.roots.ModifiableRootModel
import com.intellij.openapi.vfs.LocalFileSystem
import com.intellij.openapi.vfs.VfsUtil
import com.intellij.ui.dsl.builder.bindText
import com.intellij.ui.dsl.builder.panel
import java.io.File
import javax.swing.Icon
import javax.swing.JComponent

/**
 * Project Wizard ABL — disponible via File → New → Project → OpenEdge ABL.
 *
 * Crée la structure standard :
 *   src/            → sources .p / .cls
 *   src/includes/   → fichiers include .i
 *   .schemas/       → fichiers .df (schéma DB)
 *   .build/         → répertoire de compilation
 *   openedge-project.json → configuration projet
 *   .gitignore
 *
 * Enregistré via <moduleBuilder builderClass="..."> dans plugin.xml.
 */
class AblModuleBuilder : ModuleBuilder() {

    private var oeVersion: String = "12.7"
    private var dlcPath: String = ""

    override fun getPresentableName(): String = "OpenEdge ABL"

    override fun getDescription(): String =
        "Creates a new OpenEdge ABL project with standard directory structure " +
        "and an <code>openedge-project.json</code> configuration file."

    override fun getNodeIcon(): Icon = AblIcons.FILE

    override fun getModuleType(): ModuleType<*> = EmptyModuleType.getInstance()

    override fun isSuitableSdkType(sdkType: com.intellij.openapi.projectRoots.SdkTypeId?): Boolean = true

    override fun modifyProjectTypeStep(settingsStep: SettingsStep): ModuleWizardStep =
        object : ModuleWizardStep() {
            val panel = createSettingsPanel()
            override fun getComponent(): JComponent = panel
            override fun updateDataModel() {} // binding is live via bindText
        }

    override fun setupRootModel(rootModel: ModifiableRootModel) {
        val contentEntry = doAddContentEntry(rootModel) ?: return
        val basePath = contentEntry.url
            .removePrefix("file://")
            .removePrefix("file:/")

        createProjectStructure(basePath, rootModel.project.name)
    }

    private fun createSettingsPanel(): JComponent = panel {
        row("OpenEdge version:") {
            textField()
                .bindText(::oeVersion)
                .comment("Version OpenEdge (ex. 12.7, 12.2)")
        }
        row("DLC path (optional):") {
            textField()
                .bindText(::dlcPath)
                .comment("Chemin d'installation OpenEdge (\$DLC). Peut être laissé vide.")
        }
    }

    private fun createProjectStructure(basePath: String, projectName: String) {
        listOf("src", "src/includes", ".schemas", ".build", ".build/.warnings").forEach { dir ->
            File(basePath, dir).mkdirs()
        }

        File(basePath, "src/main.p").also {
            if (!it.exists()) it.writeText(
                "/* main.p — Point d'entrée du projet $projectName */\n\n" +
                "MESSAGE \"Hello from $projectName!\" VIEW-AS ALERT-BOX.\n"
            )
        }

        val dlcEntry = if (dlcPath.isNotBlank()) "  \"dlcPath\": \"$dlcPath\",\n" else ""
        File(basePath, "openedge-project.json").also {
            if (!it.exists()) it.writeText(
                "{\n" +
                "  \"name\": \"$projectName\",\n" +
                "  \"version\": \"$oeVersion\",\n" +
                dlcEntry +
                "  \"propath\": [\"src\", \"src/includes\"],\n" +
                "  \"buildPath\": \".build\",\n" +
                "  \"charset\": \"UTF-8\",\n" +
                "  \"databases\": []\n" +
                "}\n"
            )
        }

        File(basePath, ".gitignore").also {
            if (!it.exists()) it.writeText(".build/\n*.r\n*.pl\n*.db\n*.lg\n")
        }

        VfsUtil.markDirtyAndRefresh(
            false, true, true,
            LocalFileSystem.getInstance().findFileByPath(basePath)
        )
    }
}
