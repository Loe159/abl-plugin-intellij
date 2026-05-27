package com.ablls.plugin.project

import com.ablls.plugin.core.AblProjectAnalysisService
import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.components.service
import com.intellij.openapi.project.Project
import com.intellij.openapi.startup.ProjectActivity
import com.intellij.openapi.vfs.VirtualFileManager
import com.intellij.openapi.vfs.newvfs.BulkFileListener
import com.intellij.openapi.vfs.newvfs.events.VFileEvent

/**
 * Listener de projet — recharge la configuration openedge-project.json
 * automatiquement quand le fichier est modifié sur disque, puis met à jour
 * l'environnement proparse (PROPATH) et l'index de symboles.
 */
class AblProjectListener : ProjectActivity {
    override suspend fun execute(project: Project) {
        val connection = project.messageBus.connect()
        connection.subscribe(
            VirtualFileManager.VFS_CHANGES,
            object : BulkFileListener {
                override fun after(events: List<VFileEvent>) {
                    val shouldReload =
                        events.any { event ->
                            event.file?.name == "openedge-project.json"
                        }
                    if (shouldReload) {
                        onConfigChanged(project)
                    }
                }
            },
        )
    }

    private fun onConfigChanged(project: Project) {
        ApplicationManager.getApplication().executeOnPooledThread {
            project.service<OpenEdgeProjectService>().reload()
            // Recharger l'environnement proparse avec le nouveau PROPATH
            project.service<AblProjectAnalysisService>().updateEnvironment()
        }
    }
}
