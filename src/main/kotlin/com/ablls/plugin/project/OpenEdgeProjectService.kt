package com.ablls.plugin.project

import com.intellij.notification.NotificationGroupManager
import com.intellij.notification.NotificationType
import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.components.Service
import com.intellij.openapi.components.service
import com.intellij.openapi.project.Project
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import java.io.File

// ─── Modèle de données ────────────────────────────────────────────────────────

@Serializable
data class OpenEdgeProjectConfig(
    val name: String = "Unnamed Project",
    val version: String = "12.2",
    val dlcPath: String? = null,
    val propath: List<String> = listOf("."),
    val buildPath: String = ".build",
    val charset: String = "UTF-8",
    val databases: List<DatabaseConnection> = emptyList(),
    val aliases: List<DatabaseAlias> = emptyList(),
    val warningsDir: String = ".build/.warnings",
    val profilerDir: String? = null
)

@Serializable
data class DatabaseConnection(
    val logicalName: String,
    val database: String,
    val host: String = "localhost",
    val port: Int = 8500,
    val schemaFile: String? = null,
    val singleUser: Boolean = false
)

@Serializable
data class DatabaseAlias(
    val alias: String,
    val database: String
)

// ─── Service IntelliJ ─────────────────────────────────────────────────────────

interface OpenEdgeProjectService {
    val config: OpenEdgeProjectConfig
    fun reload()
    fun hasConfig(): Boolean
    fun getConfigFilePath(): String?
}

@Service(Service.Level.PROJECT)
class OpenEdgeProjectServiceImpl(
    private val project: Project
) : OpenEdgeProjectService {

    private val json = Json {
        ignoreUnknownKeys = true
        isLenient          = true
        coerceInputValues  = true
    }

    @Volatile
    private var _config: OpenEdgeProjectConfig = OpenEdgeProjectConfig()

    override val config: OpenEdgeProjectConfig get() = _config

    init {
        // Chargement initial hors EDT pour éviter SlowOperations
        ApplicationManager.getApplication().executeOnPooledThread { reload() }
    }

    override fun reload() {
        val configFile = findConfigFile()
        if (configFile == null) {
            _config = OpenEdgeProjectConfig()
            return
        }

        try {
            val content = configFile.readText(Charsets.UTF_8)
            _config = json.decodeFromString(content)

            // Notification sur l'EDT
            ApplicationManager.getApplication().invokeLater {
                if (!project.isDisposed) {
                    NotificationGroupManager.getInstance()
                        .getNotificationGroup("ABL Language Support")
                        .createNotification(
                            "ABL Project Loaded",
                            "Projet '${_config.name}' (OE ${_config.version})",
                            NotificationType.INFORMATION
                        )
                        .notify(project)
                }
            }
        } catch (e: Exception) {
            ApplicationManager.getApplication().invokeLater {
                if (!project.isDisposed) {
                    NotificationGroupManager.getInstance()
                        .getNotificationGroup("ABL Language Support")
                        .createNotification(
                            "ABL Project Error",
                            "Impossible de lire openedge-project.json : ${e.message}",
                            NotificationType.WARNING
                        )
                        .notify(project)
                }
            }
        }
    }

    override fun hasConfig(): Boolean = findConfigFile() != null

    override fun getConfigFilePath(): String? = findConfigFile()?.path

    private fun findConfigFile(): File? {
        val basePath = project.basePath ?: return null
        val f = File(basePath, "openedge-project.json")
        return if (f.exists()) f else null
    }
}
