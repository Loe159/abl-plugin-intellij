package com.ablls.plugin.annotator

import com.intellij.codeInsight.daemon.DaemonCodeAnalyzer
import com.intellij.openapi.project.Project
import com.intellij.openapi.vfs.newvfs.BulkFileListener
import com.intellij.openapi.vfs.newvfs.events.VFileEvent

/**
 * Écoute les changements de fichiers .warnings dans le projet.
 * Quand un nouveau fichier .warnings est détecté, relance le DaemonCodeAnalyzer
 * pour afficher les avertissements compilateur dans l'éditeur.
 */
class AblWarningFileListener(private val project: Project) : BulkFileListener {

    override fun after(events: List<VFileEvent>) {
        val hasWarnings = events.any { it.file?.extension == "warnings" }
        if (!hasWarnings) return
        if (!project.isDisposed) {
            DaemonCodeAnalyzer.getInstance(project).restart()
        }
    }
}
