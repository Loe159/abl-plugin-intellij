package com.ablls.plugin.startup

import com.ablls.plugin.core.AblProjectAnalysisService
import com.intellij.openapi.components.service
import com.intellij.openapi.project.Project
import com.intellij.openapi.startup.StartupActivity

/**
 * Activité de démarrage — lance l'indexation du projet en arrière-plan
 * une fois le projet entièrement chargé.
 */
class AblStartupActivity : StartupActivity.DumbAware {
    override fun runActivity(project: Project) {
        val service = project.service<AblProjectAnalysisService>()
        service.updateEnvironment()
        service.buildIndexInBackground()
    }
}
