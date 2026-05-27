package com.ablls.plugin.coverage

import com.intellij.icons.AllIcons
import com.intellij.openapi.components.service
import com.intellij.openapi.fileEditor.OpenFileDescriptor
import com.intellij.openapi.project.Project
import com.intellij.openapi.vfs.LocalFileSystem
import com.intellij.openapi.wm.ToolWindow
import com.intellij.openapi.wm.ToolWindowFactory
import com.intellij.ui.content.ContentFactory
import java.awt.BorderLayout
import java.awt.Component
import java.io.File
import javax.swing.JButton
import javax.swing.JLabel
import javax.swing.JPanel
import javax.swing.JScrollPane
import javax.swing.JTable
import javax.swing.JToolBar
import javax.swing.table.DefaultTableCellRenderer
import javax.swing.table.DefaultTableModel

/**
 * Vue Profiler ABL — affiche les performances par procédure/fichier.
 *
 * Après chargement d'un fichier .prof via "Load ABL Coverage",
 * affiche pour chaque module :
 *   - Nom du fichier
 *   - Nombre de lignes couvertes
 *   - Pourcentage de couverture
 *
 * Double-clic sur une ligne → ouvre le fichier source dans l'éditeur.
 */
class AblProfilerViewFactory : ToolWindowFactory {
    override fun createToolWindowContent(
        project: Project,
        toolWindow: ToolWindow,
    ) {
        val panel = AblProfilerViewPanel(project)
        val content = ContentFactory.getInstance().createContent(panel, "Profiler", false)
        toolWindow.contentManager.addContent(content)
    }
}

class AblProfilerViewPanel(private val project: Project) : JPanel(BorderLayout()) {
    private val tableModel =
        DefaultTableModel(
            arrayOf("File", "Covered Lines", "Total Executions", "Coverage"),
            0,
        )
    private val table = JTable(tableModel)

    init {
        table.autoCreateRowSorter = true
        table.setDefaultRenderer(Any::class.java, CoverageBarRenderer())

        table.addMouseListener(
            object : java.awt.event.MouseAdapter() {
                override fun mouseClicked(e: java.awt.event.MouseEvent) {
                    if (e.clickCount == 2) {
                        val row = table.rowAtPoint(e.point)
                        if (row >= 0) {
                            val modelRow = table.convertRowIndexToModel(row)
                            val filePath = tableModel.getValueAt(modelRow, 0) as? String ?: return
                            openFile(filePath)
                        }
                    }
                }
            },
        )

        val toolbar = JToolBar()
        toolbar.isFloatable = false

        val loadBtn = JButton(AllIcons.Actions.Upload)
        loadBtn.toolTipText = "Load .prof file"
        loadBtn.addActionListener {
            val chooser = javax.swing.JFileChooser()
            chooser.fileFilter = javax.swing.filechooser.FileNameExtensionFilter("Profiler files (*.prof)", "prof")
            if (chooser.showOpenDialog(this) == javax.swing.JFileChooser.APPROVE_OPTION) {
                loadProfiler(chooser.selectedFile)
            }
        }
        toolbar.add(loadBtn)

        val clearBtn = JButton(AllIcons.Actions.GC)
        clearBtn.toolTipText = "Clear coverage"
        clearBtn.addActionListener {
            project.service<AblCoverageService>().clearCoverage()
            tableModel.rowCount = 0
        }
        toolbar.add(clearBtn)

        add(toolbar, BorderLayout.NORTH)
        add(JScrollPane(table), BorderLayout.CENTER)

        val status = JLabel(" No profiler data loaded")
        add(status, BorderLayout.SOUTH)
    }

    fun loadProfiler(profFile: File) {
        val service = project.service<AblCoverageService>()
        service.loadProfFile(profFile)

        // Parse directement pour avoir les counts d'exécution complets
        val data = AblProfilerParser.parseWithCounts(profFile)

        tableModel.rowCount = 0
        data.forEach { (filePath, counts) ->
            val fileName = filePath.substringAfterLast('/').substringAfterLast('\\')
            val coveredLines = counts.size
            val totalExecs = counts.values.sum()
            val pct = if (coveredLines > 0) "$coveredLines lines" else "0%"
            tableModel.addRow(arrayOf(fileName, coveredLines, totalExecs, pct))
        }
    }

    private fun openFile(fileName: String) {
        val basePath = project.basePath ?: return
        val found =
            java.nio.file.Files.walk(java.nio.file.Paths.get(basePath), 5).use { stream ->
                stream.filter { f -> f.fileName.toString() == fileName }.findFirst().orElse(null)
            } ?: return
        val vf = LocalFileSystem.getInstance().findFileByPath(found.toString()) ?: return
        OpenFileDescriptor(project, vf, 0, 0).navigate(true)
    }

    private class CoverageBarRenderer : DefaultTableCellRenderer() {
        override fun getTableCellRendererComponent(
            table: JTable,
            value: Any?,
            isSelected: Boolean,
            hasFocus: Boolean,
            row: Int,
            column: Int,
        ): Component {
            val c = super.getTableCellRendererComponent(table, value, isSelected, hasFocus, row, column)
            if (!isSelected && column == 1) {
                c.background = java.awt.Color(0x90, 0xEE, 0x90)
            }
            return c
        }
    }
}
