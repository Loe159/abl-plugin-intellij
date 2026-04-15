package com.ablls.plugin.duplication

import com.ablls.plugin.core.AblProjectAnalysisService
import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.components.service
import com.intellij.openapi.fileEditor.OpenFileDescriptor
import com.intellij.openapi.project.Project
import com.intellij.openapi.vfs.LocalFileSystem
import com.intellij.openapi.vfs.VfsUtil
import com.intellij.ui.components.JBLabel
import com.intellij.ui.components.JBScrollPane
import com.intellij.ui.table.JBTable
import java.awt.BorderLayout
import javax.swing.*
import javax.swing.table.DefaultTableModel

class AblDuplicatesPanel(private val project: Project) : JPanel(BorderLayout()) {

    private val tableModel = object : DefaultTableModel(
        arrayOf("File A", "Start A", "End A", "File B", "Start B", "End B", "Tokens"), 0
    ) {
        override fun isCellEditable(row: Int, col: Int) = false
    }
    private val table  = JBTable(tableModel)
    private val status = JBLabel("Click 'Detect' to find duplicates")
    private var pairs: List<AblDuplicationDetector.DuplicatePair> = emptyList()

    init {
        val toolbar = JPanel()
        val detectBtn = JButton("Detect Duplicates")
        detectBtn.addActionListener { runDetection() }
        toolbar.add(detectBtn)
        toolbar.add(status)

        table.setSelectionMode(ListSelectionModel.SINGLE_SELECTION)
        table.addMouseListener(object : java.awt.event.MouseAdapter() {
            override fun mouseClicked(e: java.awt.event.MouseEvent) {
                if (e.clickCount == 2) navigateToSelected()
            }
        })

        add(toolbar, BorderLayout.NORTH)
        add(JBScrollPane(table), BorderLayout.CENTER)
    }

    private fun runDetection() {
        status.text = "Detecting..."
        ApplicationManager.getApplication().executeOnPooledThread {
            val service = project.service<AblProjectAnalysisService>()
            val files   = mutableMapOf<String, com.ablls.plugin.core.AblParseResult>()

            val basePath = project.basePath ?: return@executeOnPooledThread
            val root = LocalFileSystem.getInstance().findFileByPath(basePath) ?: return@executeOnPooledThread

            VfsUtil.iterateChildrenRecursively(root, null) { vFile ->
                if (!vFile.isDirectory && vFile.extension?.lowercase() in listOf("p", "cls", "w")) {
                    val content = runCatching { VfsUtil.loadText(vFile) }.getOrNull() ?: return@iterateChildrenRecursively true
                    files[vFile.url] = service.analyzeFile(content, vFile.url)
                }
                true
            }

            pairs = AblDuplicationDetector().detect(files)

            ApplicationManager.getApplication().invokeLater {
                tableModel.rowCount = 0
                for (p in pairs) {
                    tableModel.addRow(arrayOf(
                        p.a.uri.substringAfterLast('/'),
                        p.a.startLine, p.a.endLine,
                        p.b.uri.substringAfterLast('/'),
                        p.b.startLine, p.b.endLine,
                        p.a.tokenCount
                    ))
                }
                status.text = "${pairs.size} duplicate fragment(s) found"
            }
        }
    }

    private fun navigateToSelected() {
        val row = table.selectedRow
        if (row < 0 || row >= pairs.size) return
        val pair  = pairs[row]
        val filePath = pair.a.uri.removePrefix("file://").removePrefix("file:/")
        val vFile = LocalFileSystem.getInstance().findFileByPath(filePath) ?: return
        OpenFileDescriptor(project, vFile, pair.a.startLine - 1, 0).navigate(true)
    }
}
