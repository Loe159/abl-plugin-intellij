package com.ablls.plugin.xref

import com.intellij.openapi.project.Project
import com.intellij.openapi.wm.ToolWindow
import com.intellij.openapi.wm.ToolWindowFactory

class XrefToolWindowFactory : ToolWindowFactory {
    override fun createToolWindowContent(project: Project, toolWindow: ToolWindow) {
        val panel   = XrefPanel(project)
        val content = toolWindow.contentManager.factory.createContent(panel, "XREF", false)
        toolWindow.contentManager.addContent(content)
    }
}
