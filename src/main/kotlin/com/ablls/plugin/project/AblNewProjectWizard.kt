@file:Suppress("ktlint:standard:filename")

package com.ablls.plugin.project

import com.intellij.ide.wizard.AbstractNewProjectWizardStep
import com.intellij.ide.wizard.NewProjectWizardStep
import com.intellij.openapi.project.Project
import com.intellij.openapi.vfs.VfsUtil
import com.intellij.ui.dsl.builder.Panel
import com.intellij.ui.dsl.builder.bindText
import java.io.File

/**
 * Project Wizard — template "New OpenEdge ABL Project".
 *
 * Crée la structure de projet ABL standard :
 *   /src/           → sources ABL (.p, .cls)
 *   /src/includes/  → fichiers include (.i)
 *   /.schemas/      → fichiers .df (schéma DB)
 *   /.build/        → répertoire de compilation
 *   /openedge-project.json → configuration du projet
 *
 * Intégré dans le menu File → New → Project → OpenEdge ABL.
 */
class AblNewProjectWizardStep(parent: NewProjectWizardStep) : AbstractNewProjectWizardStep(parent) {
    var projectName: String = "my-abl-project"
    var oeVersion: String = "12.7"
    var dlcPath: String = ""

    override fun setupUI(builder: Panel) {
        builder.apply {
            row("OE Version:") {
                textField()
                    .bindText(::oeVersion)
                    .comment("OpenEdge version (e.g. 12.7, 12.2)")
            }
            row("DLC Path:") {
                textField()
                    .bindText(::dlcPath)
                    .comment("Path to OpenEdge installation (DLC), e.g. /usr/dlc or C:\\Progress\\OpenEdge")
            }
        }
    }

    override fun setupProject(project: Project) {
        val basePath = context.projectDirectory.toString()

        // Créer la structure de répertoires
        listOf("src", "src/includes", ".schemas", ".build", ".build/.warnings").forEach { dir ->
            File(basePath, dir).mkdirs()
        }

        // Créer un fichier .p de démarrage
        File(basePath, "src/main.p").writeText(
            "/* main.p — Point d'entrée du projet ${context.projectName} */\n\n" +
                "MESSAGE \"Hello from ${context.projectName}!\" VIEW-AS ALERT-BOX.\n",
        )

        // Créer openedge-project.json
        val configContent =
            buildString {
                appendLine("{")
                appendLine("  \"name\": \"${context.projectName}\",")
                appendLine("  \"version\": \"$oeVersion\",")
                if (dlcPath.isNotBlank()) {
                    appendLine("  \"dlcPath\": \"$dlcPath\",")
                }
                appendLine("  \"propath\": [\"src\", \"src/includes\"],")
                appendLine("  \"buildPath\": \".build\",")
                appendLine("  \"charset\": \"UTF-8\",")
                appendLine("  \"databases\": []")
                appendLine("}")
            }
        File(basePath, "openedge-project.json").writeText(configContent)

        // Créer un .gitignore
        File(basePath, ".gitignore").writeText(
            ".build/\n*.r\n*.pl\n*.db\n*.lg\n",
        )

        // Rafraîchir le VFS
        VfsUtil.markDirtyAndRefresh(
            false,
            true,
            true,
            com.intellij.openapi.vfs.LocalFileSystem.getInstance().findFileByPath(basePath),
        )
    }
}
