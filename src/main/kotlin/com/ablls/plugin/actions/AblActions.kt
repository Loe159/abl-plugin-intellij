package com.ablls.plugin.actions

import com.ablls.plugin.core.AblProjectAnalysisService
import com.ablls.plugin.project.OpenEdgeProjectService
import com.intellij.notification.NotificationGroupManager
import com.intellij.notification.NotificationType
import com.intellij.openapi.actionSystem.AnAction
import com.intellij.openapi.actionSystem.AnActionEvent
import com.intellij.openapi.components.service
import com.intellij.openapi.fileEditor.FileEditorManager
import com.intellij.openapi.vfs.LocalFileSystem
import java.io.File
import java.nio.charset.StandardCharsets

// ─── Action : Ré-indexer le projet ────────────────────────────────────────────

class ReindexProjectAction : AnAction() {

    override fun actionPerformed(e: AnActionEvent) {
        val project = e.project ?: return
        val service = project.service<AblProjectAnalysisService>()

        service.symbolIndex.clear()
        service.updateEnvironment()
        service.buildIndexInBackground()

        NotificationGroupManager.getInstance()
            .getNotificationGroup("ABL Language Support")
            .createNotification(
                "ABL Language Support",
                "Re-indexation du projet lancée en arrière-plan.",
                NotificationType.INFORMATION
            )
            .notify(project)
    }

    override fun update(e: AnActionEvent) {
        e.presentation.isEnabledAndVisible = e.project != null
    }
}

// ─── Action : Ouvrir / créer openedge-project.json ───────────────────────────

class OpenProjectConfigAction : AnAction() {

    private val DEFAULT_CONFIG = """
{
  "name": "Mon Projet ABL",
  "version": "12.7",
  "dlcPath": "/usr/dlc",
  "propath": [
    "src",
    "src/includes",
    "${'$'}{DLC}/tty"
  ],
  "buildPath": ".build",
  "charset": "UTF-8",
  "databases": [
    {
      "logicalName": "mydb",
      "database": "mydb",
      "host": "localhost",
      "port": 8500,
      "schemaFile": ".schemas/mydb.df"
    }
  ]
}
""".trimIndent()

    override fun actionPerformed(e: AnActionEvent) {
        val project = e.project ?: return
        val basePath = project.basePath ?: return
        val configFile = File(basePath, "openedge-project.json")

        if (!configFile.exists()) {
            configFile.writeText(DEFAULT_CONFIG, StandardCharsets.UTF_8)
        }

        val vFile = LocalFileSystem.getInstance().refreshAndFindFileByIoFile(configFile)
        if (vFile != null) {
            FileEditorManager.getInstance(project).openFile(vFile, true)
        }
    }

    override fun update(e: AnActionEvent) {
        e.presentation.isEnabledAndVisible = e.project != null
    }
}
