package com.ablls.plugin.project

import com.intellij.icons.AllIcons
import com.intellij.openapi.components.service
import com.intellij.openapi.fileEditor.FileEditorManager
import com.intellij.openapi.project.Project
import com.intellij.openapi.vfs.LocalFileSystem
import com.intellij.openapi.wm.ToolWindow
import com.intellij.openapi.wm.ToolWindowFactory
import com.intellij.ui.content.ContentFactory
import java.awt.BorderLayout
import java.awt.Component
import java.nio.file.Files
import java.nio.file.Paths
import javax.swing.JButton
import javax.swing.JLabel
import javax.swing.JPanel
import javax.swing.JScrollPane
import javax.swing.JToolBar
import javax.swing.JTree
import javax.swing.SwingUtilities
import javax.swing.tree.DefaultMutableTreeNode
import javax.swing.tree.DefaultTreeCellRenderer
import javax.swing.tree.DefaultTreeModel

/**
 * ToolWindow "ABL PROPATH" — visualise et explore le PROPATH du projet.
 *
 * Affiche pour chaque entrée du PROPATH :
 *   - Si le dossier existe : ✓ chemin résolu + nombre de fichiers ABL
 *   - Si introuvable        : ✗ chemin tel quel (rouge)
 *
 * Double-clic sur un nœud de fichier l'ouvre dans l'éditeur.
 */
class AblPropathExplorerFactory : ToolWindowFactory {
    override fun createToolWindowContent(
        project: Project,
        toolWindow: ToolWindow,
    ) {
        val panel = AblPropathExplorerPanel(project)
        val content = ContentFactory.getInstance().createContent(panel, "PROPATH", false)
        toolWindow.contentManager.addContent(content)
    }
}

class AblPropathExplorerPanel(private val project: Project) : JPanel(BorderLayout()) {
    private val tree: JTree
    private val statusLabel: JLabel

    init {
        val root = DefaultMutableTreeNode("PROPATH")
        tree = JTree(DefaultTreeModel(root))
        tree.isRootVisible = true
        tree.cellRenderer = PropathTreeCellRenderer()

        tree.addMouseListener(
            object : java.awt.event.MouseAdapter() {
                override fun mouseClicked(e: java.awt.event.MouseEvent) {
                    if (e.clickCount == 2) {
                        val node = tree.lastSelectedPathComponent as? DefaultMutableTreeNode ?: return
                        val info = node.userObject as? NodeInfo ?: return
                        if (info.kind == NodeKind.FILE) {
                            val vf = LocalFileSystem.getInstance().findFileByPath(info.path) ?: return
                            FileEditorManager.getInstance(project).openFile(vf, true)
                        }
                    }
                }
            },
        )

        val toolbar = JToolBar()
        toolbar.isFloatable = false
        val refreshBtn = JButton(AllIcons.Actions.Refresh)
        refreshBtn.toolTipText = "Refresh PROPATH"
        refreshBtn.addActionListener { refresh() }
        toolbar.add(refreshBtn)

        statusLabel = JLabel(" ")

        val topPanel = JPanel(BorderLayout())
        topPanel.add(toolbar, BorderLayout.WEST)
        topPanel.add(statusLabel, BorderLayout.CENTER)

        add(topPanel, BorderLayout.NORTH)
        add(JScrollPane(tree), BorderLayout.CENTER)

        refresh()
    }

    fun refresh() {
        val config = project.service<OpenEdgeProjectService>().config
        val basePath = project.basePath ?: return
        val dlcPath = config.dlcPath ?: System.getenv("DLC") ?: ""
        val root = DefaultMutableTreeNode("PROPATH (${config.propath.size} entries)")

        var totalFiles = 0
        var missingCount = 0

        config.propath.forEach { pathStr ->
            val resolved =
                pathStr
                    .replace("\${DLC}", dlcPath)
                    .replace("\$DLC", dlcPath)
            val path =
                try {
                    val p = Paths.get(resolved)
                    if (p.isAbsolute) p else Paths.get(basePath).resolve(p)
                } catch (_: Exception) {
                    null
                }

            val exists = path != null && Files.isDirectory(path)
            if (!exists) missingCount++

            val label = if (exists) "✓ $resolved" else "✗ $resolved (not found)"
            val dirNode =
                DefaultMutableTreeNode(
                    NodeInfo(
                        resolved,
                        if (exists) NodeKind.DIR_OK else NodeKind.DIR_MISSING,
                        path?.toString() ?: resolved,
                    ),
                )
            root.add(dirNode)

            if (exists && path != null) {
                try {
                    var count = 0
                    Files.walk(path, 3).use { stream ->
                        stream.filter { f ->
                            Files.isRegularFile(f) &&
                                f.fileName.toString().let { n ->
                                    n.endsWith(".p") || n.endsWith(".cls") ||
                                        n.endsWith(".i") || n.endsWith(".w")
                                }
                        }.limit(200).forEach { file ->
                            val relPath = path.relativize(file).toString()
                            dirNode.add(
                                DefaultMutableTreeNode(
                                    NodeInfo(relPath, NodeKind.FILE, file.toString()),
                                ),
                            )
                            count++
                        }
                    }
                    totalFiles += count
                    // Update dir label to include file count
                    dirNode.userObject = NodeInfo("✓ $resolved ($count files)", NodeKind.DIR_OK, path.toString())
                } catch (_: Exception) {
                }
            }
        }

        statusLabel.text = " $totalFiles ABL files indexed" +
            if (missingCount > 0) " | $missingCount missing paths" else ""

        SwingUtilities.invokeLater {
            (tree.model as DefaultTreeModel).setRoot(root)
            (tree.model as DefaultTreeModel).reload()
        }
    }

    private enum class NodeKind { DIR_OK, DIR_MISSING, FILE }

    private data class NodeInfo(val label: String, val kind: NodeKind, val path: String)

    private inner class PropathTreeCellRenderer : DefaultTreeCellRenderer() {
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
            val info = (value as? DefaultMutableTreeNode)?.userObject as? NodeInfo
            when (info?.kind) {
                NodeKind.DIR_OK -> {
                    icon = AllIcons.Nodes.Folder
                    text = info.label
                }
                NodeKind.DIR_MISSING -> {
                    icon = AllIcons.Nodes.Folder
                    foreground = java.awt.Color.RED
                    text = info.label
                }
                NodeKind.FILE -> {
                    icon =
                        when {
                            info.label.endsWith(".cls") -> AllIcons.Nodes.Class
                            info.label.endsWith(".i") -> AllIcons.FileTypes.Any_type
                            else -> AllIcons.FileTypes.Custom
                        }
                    text = info.label
                }
                null -> {}
            }
            return this
        }
    }
}
