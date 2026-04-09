package com.ablls.plugin.duplication

import com.intellij.openapi.project.Project
import com.intellij.openapi.wm.ToolWindow
import com.intellij.openapi.wm.ToolWindowFactory

class AblDuplicatesToolWindowFactory : ToolWindowFactory {
    override fun createToolWindowContent(project: Project, toolWindow: ToolWindow) {
        val panel   = AblDuplicatesPanel(project)
        val content = toolWindow.contentManager.factory.createContent(panel, "Duplicates", false)
        toolWindow.contentManager.addContent(content)
    }
}
