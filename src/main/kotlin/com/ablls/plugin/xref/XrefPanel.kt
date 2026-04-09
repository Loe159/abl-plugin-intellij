package com.ablls.plugin.xref

import com.intellij.openapi.fileChooser.FileChooserDescriptorFactory
import com.intellij.openapi.fileEditor.OpenFileDescriptor
import com.intellij.openapi.project.Project
import com.intellij.openapi.ui.TextFieldWithBrowseButton
import com.intellij.openapi.vfs.LocalFileSystem
import com.intellij.ui.components.JBScrollPane
import com.intellij.ui.table.JBTable
import java.awt.BorderLayout
import java.io.File
import javax.swing.*
import javax.swing.table.DefaultTableModel

/**
 * Panneau affiché dans le tool window "ABL XREF".
 * Affiche les références XREF d'un fichier .xref.xml en tableau.
 */
class XrefPanel(private val project: Project) : JPanel(BorderLayout()) {

    private val tableModel = object : DefaultTableModel(arrayOf("Type", "Object", "Line", "Detail"), 0) {
        override fun isCellEditable(row: Int, col: Int) = false
    }
    private val table = JBTable(tableModel)
    private var records: List<XrefRecord> = emptyList()

    init {
        val toolbar = JPanel()
        val fileField = TextFieldWithBrowseButton()
        fileField.addBrowseFolderListener(
            "Open XREF File", null, project,
            FileChooserDescriptorFactory.createSingleFileDescriptor("xml")
        )
        val loadBtn = JButton("Load")
        loadBtn.addActionListener {
            val path = fileField.text.trim()
            if (path.isNotEmpty()) loadXref(File(path))
        }
        toolbar.add(fileField)
        toolbar.add(loadBtn)

        table.setSelectionMode(ListSelectionModel.SINGLE_SELECTION)
        table.addMouseListener(object : java.awt.event.MouseAdapter() {
            override fun mouseClicked(e: java.awt.event.MouseEvent) {
                if (e.clickCount == 2) navigateToSelected()
            }
        })

        add(toolbar, BorderLayout.NORTH)
        add(JBScrollPane(table), BorderLayout.CENTER)
    }

    private fun loadXref(file: File) {
        try {
            val xref = XrefParser.parse(file)
            records = xref.records
            tableModel.rowCount = 0
            for (r in records) {
                tableModel.addRow(arrayOf(r.type.name, r.objectName, r.line, r.detail))
            }
        } catch (e: Exception) {
            JOptionPane.showMessageDialog(this, "Error loading XREF: ${e.message}", "Error", JOptionPane.ERROR_MESSAGE)
        }
    }

    private fun navigateToSelected() {
        val row = table.selectedRow
        if (row < 0 || row >= records.size) return
        val record = records[row]
        if (record.line <= 0) return

        // Chercher le fichier source dans le projet
        val basePath = project.basePath ?: return
        val objName  = record.objectName.replace('.', '/').replace('\\', '/')
        val extensions = listOf(".p", ".cls", ".w", ".i", ".t", "")
        for (ext in extensions) {
            val vFile = LocalFileSystem.getInstance().findFileByPath("$basePath/$objName$ext")
                ?: continue
            OpenFileDescriptor(project, vFile, record.line - 1, 0).navigate(true)
            return
        }
    }
}
