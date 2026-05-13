package com.ablls.plugin.run

import com.ablls.plugin.language.AblFileType
import com.ablls.plugin.language.AblLanguage
import com.ablls.plugin.project.OpenEdgeProjectService
import com.intellij.execution.lineMarker.RunLineMarkerContributor
import com.intellij.icons.AllIcons
import com.intellij.openapi.actionSystem.AnAction
import com.intellij.openapi.actionSystem.AnActionEvent
import com.intellij.openapi.actionSystem.CommonDataKeys
import com.intellij.openapi.components.service
import com.intellij.openapi.ui.Messages
import com.intellij.openapi.vfs.VirtualFile
import com.intellij.psi.PsiElement
import com.intellij.psi.PsiFile

/**
 * Gutter icon "Compile this file" pour les fichiers `.p` ABL.
 *
 * Affiche une icône "Build" dans la gouttière à la première ligne des fichiers
 * `.p` et `.cls`. En cliquant, lance la compilation ABL via `prowin /compile`.
 *
 * Conditions :
 *   - `dlcPath` ou variable `DLC` doit être défini
 *   - Le fichier doit être un `.p` ou `.cls`
 */
class AblCompileGutterIconProvider : RunLineMarkerContributor() {

    override fun getInfo(element: PsiElement): Info? {
        if (element.language != AblLanguage) return null
        val file = element.containingFile ?: return null
        val vf   = file.virtualFile ?: return null

        // Seulement sur le premier token du fichier (pour n'afficher qu'une icône)
        if (element.textRange.startOffset != 0) return null
        if (vf.extension?.lowercase() !in setOf("p", "cls", "w")) return null

        val project = element.project
        val config  = project.service<OpenEdgeProjectService>().config
        val dlcPath = config.dlcPath ?: System.getenv("DLC")

        val action = CompileAblFileAction(vf, dlcPath)
        return Info(
            AllIcons.Actions.Compile,
            { "Compile ${vf.name}" },
            action
        )
    }
}

// ─── Action de compilation ────────────────────────────────────────────────────

private class CompileAblFileAction(
    private val file: VirtualFile,
    private val dlcPath: String?
) : AnAction("Compile ${file.name}", "Compile ABL file", AllIcons.Actions.Compile) {

    override fun actionPerformed(e: AnActionEvent) {
        val project = e.project ?: return

        if (dlcPath == null) {
            Messages.showWarningDialog(
                project,
                "DLC path is not configured.\n\nSet 'dlcPath' in openedge-project.json\nor define the DLC environment variable.",
                "ABL Compilation"
            )
            return
        }

        val filePath = file.path
        val prowin   = "$dlcPath/bin/prowin" // Linux/Mac
        val prowinWin = "$dlcPath\\bin\\prowin32.exe"  // Windows

        val executable = when {
            java.io.File(prowinWin).exists() -> prowinWin
            java.io.File("$prowin.exe").exists() -> "$prowin.exe"
            java.io.File(prowin).exists() -> prowin
            else -> {
                Messages.showWarningDialog(
                    project,
                    "prowin not found in '$dlcPath/bin/'.\nCheck your DLC installation.",
                    "ABL Compilation"
                )
                return
            }
        }

        // Lancer la compilation dans un thread background
        com.intellij.openapi.application.ApplicationManager.getApplication().executeOnPooledThread {
            try {
                val cmd = listOf(executable, "-b", "-p", "prolib/compile.p", "-param", filePath)
                val proc = ProcessBuilder(cmd)
                    .redirectErrorStream(true)
                    .start()
                val output = proc.inputStream.bufferedReader().readText()
                val exitCode = proc.waitFor()

                com.intellij.openapi.application.ApplicationManager.getApplication().invokeLater {
                    if (exitCode == 0) {
                        Messages.showInfoMessage(project, "Compilation successful: ${file.name}", "ABL Compilation")
                    } else {
                        Messages.showErrorDialog(project, "Compilation failed:\n$output", "ABL Compilation")
                    }
                }
            } catch (ex: Exception) {
                com.intellij.openapi.application.ApplicationManager.getApplication().invokeLater {
                    Messages.showErrorDialog(project, "Could not run compiler: ${ex.message}", "ABL Compilation")
                }
            }
        }
    }

    override fun update(e: AnActionEvent) {
        e.presentation.isEnabled = dlcPath != null
    }
}
