package com.ablls.plugin.duplication

import com.intellij.openapi.actionSystem.AnAction
import com.intellij.openapi.actionSystem.AnActionEvent
import com.intellij.openapi.wm.ToolWindowManager

class FindAblDuplicatesAction : AnAction("Find ABL Duplicates") {
    override fun actionPerformed(e: AnActionEvent) {
        val project = e.project ?: return
        ToolWindowManager.getInstance(project).getToolWindow("ABL Duplicates")?.activate(null)
    }
}
