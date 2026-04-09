package com.ablls.plugin.coverage

import com.intellij.openapi.actionSystem.AnAction
import com.intellij.openapi.actionSystem.AnActionEvent
import com.intellij.openapi.components.service
import com.intellij.openapi.fileChooser.FileChooser
import com.intellij.openapi.fileChooser.FileChooserDescriptorFactory
import com.intellij.openapi.vfs.VfsUtil
import java.io.File

/**
 * Action "Load ABL Coverage" : permet de choisir un fichier .prof et
 * d'appliquer la couverture de code dans l'éditeur.
 */
class LoadCoverageAction : AnAction("Load ABL Coverage (.prof)") {

    override fun actionPerformed(e: AnActionEvent) {
        val project = e.project ?: return
        val descriptor = FileChooserDescriptorFactory.createSingleFileDescriptor("prof")
            .withTitle("Select OpenEdge Profiler File")

        FileChooser.chooseFile(descriptor, project, null) { vFile ->
            val profFile = VfsUtil.virtualToIoFile(vFile)
            project.service<AblCoverageService>().loadProfFile(profFile)
        }
    }

    override fun update(e: AnActionEvent) {
        e.presentation.isEnabledAndVisible = e.project != null
    }
}
