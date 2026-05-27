package com.ablls.plugin.db

import com.ablls.plugin.core.AblProjectAnalysisService
import com.ablls.plugin.core.AblSymbol
import com.intellij.icons.AllIcons
import com.intellij.openapi.components.service
import com.intellij.openapi.project.Project
import com.intellij.openapi.wm.ToolWindow
import com.intellij.openapi.wm.ToolWindowFactory
import com.intellij.ui.content.ContentFactory
import com.intellij.ui.treeStructure.SimpleTree
import java.awt.BorderLayout
import java.awt.Component
import javax.swing.JButton
import javax.swing.JPanel
import javax.swing.JScrollPane
import javax.swing.JToolBar
import javax.swing.JTree
import javax.swing.SwingUtilities
import javax.swing.tree.DefaultMutableTreeNode
import javax.swing.tree.DefaultTreeCellRenderer
import javax.swing.tree.DefaultTreeModel

/**
 * Panneau "ABL Schema" — explore les tables et champs du schéma DB chargé.
 *
 * Affiche l'arborescence : Base → Tables → Champs (avec type)
 * Alimenté depuis [AblSymbolIndex] qui contient les TABLE et FIELD symbols
 * extraits des fichiers .df déclarés dans openedge-project.json.
 */
class AblSchemaExplorerFactory : ToolWindowFactory {
    override fun createToolWindowContent(
        project: Project,
        toolWindow: ToolWindow,
    ) {
        val panel = AblSchemaExplorerPanel(project)
        val content = ContentFactory.getInstance().createContent(panel, "Schema", false)
        toolWindow.contentManager.addContent(content)
    }
}

class AblSchemaExplorerPanel(private val project: Project) : JPanel(BorderLayout()) {
    private val tree: JTree

    init {
        val root = DefaultMutableTreeNode("ABL Schema")
        tree = SimpleTree(DefaultTreeModel(root))
        tree.isRootVisible = true
        tree.cellRenderer = SchemaTreeCellRenderer()

        add(JScrollPane(tree), BorderLayout.CENTER)

        val toolbar = JToolBar()
        toolbar.isFloatable = false
        val refreshBtn = JButton(AllIcons.Actions.Refresh)
        refreshBtn.toolTipText = "Refresh schema"
        refreshBtn.addActionListener { refresh() }
        toolbar.add(refreshBtn)
        add(toolbar, BorderLayout.NORTH)

        refresh()
    }

    fun refresh() {
        val service = project.service<AblProjectAnalysisService>()
        val allSymbols = service.symbolIndex.allSymbols()

        val root = DefaultMutableTreeNode("ABL Schema")

        // Regrouper les champs par table
        val tableNodes = mutableMapOf<String, DefaultMutableTreeNode>()

        // D'abord les tables
        allSymbols.filter { it.kind == AblSymbol.Kind.TABLE }.sortedBy { it.name }.forEach { table ->
            val node = DefaultMutableTreeNode(SchemaNode(table.name, "TABLE", table.dataType))
            tableNodes[table.name.uppercase()] = node
            root.add(node)
        }

        // Puis les champs (FIELD) — format "TableName.FieldName"
        allSymbols.filter { it.kind == AblSymbol.Kind.FIELD }.sortedBy { it.name }.forEach { field ->
            val tableName = field.name.substringBeforeLast('.', "")
            val fieldName = field.name.substringAfterLast('.')
            val tableNode = tableNodes[tableName.uppercase()]
            if (tableNode != null) {
                val fieldNode =
                    DefaultMutableTreeNode(
                        SchemaNode(fieldName, "FIELD", field.dataType),
                    )
                tableNode.add(fieldNode)
            }
        }

        SwingUtilities.invokeLater {
            (tree.model as DefaultTreeModel).setRoot(root)
            (tree.model as DefaultTreeModel).reload()
            if (tableNodes.isEmpty()) {
                root.userObject = "ABL Schema (no .df loaded)"
            } else {
                root.userObject = "ABL Schema (${tableNodes.size} table${if (tableNodes.size != 1) "s" else ""})"
            }
            (tree.model as DefaultTreeModel).reload()
        }
    }

    private data class SchemaNode(val name: String, val kind: String, val type: String?)

    private inner class SchemaTreeCellRenderer : DefaultTreeCellRenderer() {
        override fun getTreeCellRendererComponent(
            tree: JTree,
            value: Any?,
            sel: Boolean,
            expanded: Boolean,
            leaf: Boolean,
            row: Int,
            hasFocus: Boolean,
        ): Component {
            super.getTreeCellRendererComponent(tree, value, sel, expanded, leaf, row, hasFocus)
            val node = (value as? DefaultMutableTreeNode)?.userObject
            when {
                node is SchemaNode && node.kind == "TABLE" -> {
                    icon = AllIcons.Nodes.DataTables
                    text = node.name
                }
                node is SchemaNode && node.kind == "FIELD" -> {
                    icon = AllIcons.Nodes.Field
                    text = if (node.type != null) "${node.name} : ${node.type}" else node.name
                }
                node is String -> {
                    icon = AllIcons.Nodes.DataSchema
                    text = node
                }
            }
            return this
        }
    }
}
