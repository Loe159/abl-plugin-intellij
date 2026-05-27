package com.ablls.plugin.navigation

import com.ablls.plugin.core.AblProjectAnalysisService
import com.ablls.plugin.core.AblSymbol
import com.ablls.plugin.language.AblLanguage
import com.intellij.icons.AllIcons
import com.intellij.ide.hierarchy.HierarchyBrowser
import com.intellij.ide.hierarchy.HierarchyProvider
import com.intellij.openapi.actionSystem.CommonDataKeys
import com.intellij.openapi.actionSystem.DataContext
import com.intellij.openapi.components.service
import com.intellij.openapi.fileEditor.OpenFileDescriptor
import com.intellij.openapi.project.Project
import com.intellij.openapi.vfs.VirtualFileManager
import com.intellij.psi.PsiElement
import com.intellij.ui.treeStructure.SimpleTree
import java.awt.BorderLayout
import java.awt.Font
import javax.swing.JComponent
import javax.swing.JLabel
import javax.swing.JPanel
import javax.swing.JScrollPane
import javax.swing.JSplitPane
import javax.swing.JTree
import javax.swing.SwingUtilities
import javax.swing.tree.DefaultMutableTreeNode
import javax.swing.tree.DefaultTreeCellRenderer
import javax.swing.tree.DefaultTreeModel

/**
 * Type Hierarchy ABL (Ctrl+H sur une classe ABL).
 *
 * Affiche dans un panneau dédié :
 *   - Supertypes : chaîne INHERITS remontant depuis la classe cible
 *   - Subtypes   : classes qui INHERITS de la classe cible
 *
 * La hiérarchie est construite depuis [AblSymbolIndex] où le champ [AblSymbol.dataType]
 * encode "CLASS INHERITS ParentName" (renseigné par [AblSymbolCollector.visitClassStatement]).
 */
class AblTypeHierarchyProvider : HierarchyProvider {
    override fun getTarget(dataContext: DataContext): PsiElement? {
        val file = dataContext.getData(CommonDataKeys.PSI_FILE) ?: return null
        val editor = dataContext.getData(CommonDataKeys.EDITOR) ?: return null
        if (file.language != AblLanguage) return null

        val element = file.findElementAt(editor.caretModel.offset) ?: return null
        val word = element.text?.trim() ?: return null
        val uri = file.virtualFile?.url ?: return null
        val service = file.project.service<AblProjectAnalysisService>()

        val isClass =
            service.symbolIndex.findByName(word, uri)
                .any { it.kind == AblSymbol.Kind.CLASS }
        return if (isClass) element else null
    }

    override fun createHierarchyBrowser(target: PsiElement): HierarchyBrowser {
        return AblTypeHierarchyBrowser(target.project, target)
    }

    override fun browserActivated(hierarchyBrowser: HierarchyBrowser) {
        (hierarchyBrowser as? AblTypeHierarchyBrowser)?.refresh()
    }
}

// ─── Browser ─────────────────────────────────────────────────────────────────

class AblTypeHierarchyBrowser(
    private val project: Project,
    private val target: PsiElement,
) : HierarchyBrowser {
    private val panel = JPanel(BorderLayout(0, 4))
    private var initialized = false

    override fun getComponent(): JComponent {
        panel.add(JLabel(" Loading hierarchy…"), BorderLayout.CENTER)
        return panel
    }

    override fun setContent(content: com.intellij.ui.content.Content) {
        content.displayName = "ABL Type Hierarchy"
    }

    fun refresh() {
        if (initialized) return
        initialized = true
        SwingUtilities.invokeLater { buildUI() }
    }

    private fun buildUI() {
        panel.removeAll()
        val className = target.text?.trim() ?: return
        val service = project.service<AblProjectAnalysisService>()

        // ── Supertypes ────────────────────────────────────────────────────────
        val superRoot = DefaultMutableTreeNode("Supertypes of $className")
        buildSupertypes(className, superRoot, service, mutableSetOf())

        // ── Subtypes ──────────────────────────────────────────────────────────
        val subRoot = DefaultMutableTreeNode("Subtypes of $className")
        buildSubtypes(className, subRoot, service, mutableSetOf())

        val splitPane =
            JSplitPane(
                JSplitPane.VERTICAL_SPLIT,
                buildTreePanel(superRoot, "Supertypes"),
                buildTreePanel(subRoot, "Subtypes"),
            )
        splitPane.resizeWeight = 0.4

        panel.add(splitPane, BorderLayout.CENTER)
        panel.revalidate()
        panel.repaint()
    }

    private fun buildSupertypes(
        name: String,
        parent: DefaultMutableTreeNode,
        service: AblProjectAnalysisService,
        visited: MutableSet<String>,
    ) {
        if (!visited.add(name.uppercase())) return
        val sym =
            service.symbolIndex.findByName(name, "")
                .firstOrNull { it.kind == AblSymbol.Kind.CLASS } ?: return
        val parentName = extractInherits(sym.dataType) ?: return
        val node = DefaultMutableTreeNode(SymbolNode(parentName, sym))
        parent.add(node)
        buildSupertypes(parentName, node, service, visited)
    }

    private fun buildSubtypes(
        name: String,
        parent: DefaultMutableTreeNode,
        service: AblProjectAnalysisService,
        visited: MutableSet<String>,
    ) {
        if (!visited.add(name.uppercase())) return
        service.symbolIndex.allSymbols()
            .filter { sym ->
                sym.kind == AblSymbol.Kind.CLASS &&
                    extractInherits(sym.dataType).equals(name, ignoreCase = true)
            }
            .forEach { sym ->
                val node = DefaultMutableTreeNode(SymbolNode(sym.name, sym))
                parent.add(node)
                buildSubtypes(sym.name, node, service, visited)
            }
    }

    private fun buildTreePanel(
        root: DefaultMutableTreeNode,
        title: String,
    ): JPanel {
        val tree = SimpleTree(DefaultTreeModel(root))
        tree.isRootVisible = true
        tree.cellRenderer = SymbolTreeCellRenderer()
        tree.addMouseListener(
            object : java.awt.event.MouseAdapter() {
                override fun mouseClicked(e: java.awt.event.MouseEvent) {
                    if (e.clickCount != 2) return
                    val node = tree.lastSelectedPathComponent as? DefaultMutableTreeNode ?: return
                    (node.userObject as? SymbolNode)?.let { navigateTo(it.symbol) }
                }
            },
        )
        for (i in 0 until root.childCount) tree.expandRow(i + 1)

        val panel = JPanel(BorderLayout())
        val header = JLabel(" $title")
        header.font = header.font.deriveFont(Font.BOLD)
        panel.add(header, BorderLayout.NORTH)
        panel.add(JScrollPane(tree), BorderLayout.CENTER)
        return panel
    }

    private fun navigateTo(symbol: AblSymbol) {
        val uri = symbol.uri?.takeIf { !it.startsWith("db://") } ?: return
        val vf = VirtualFileManager.getInstance().findFileByUrl(uri) ?: return
        val line = (symbol.definitionRange?.startLine ?: 0).coerceAtLeast(0)
        OpenFileDescriptor(project, vf, line, 0).navigate(true)
    }
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

private data class SymbolNode(val label: String, val symbol: AblSymbol)

private class SymbolTreeCellRenderer : DefaultTreeCellRenderer() {
    override fun getTreeCellRendererComponent(
        tree: JTree,
        value: Any?,
        sel: Boolean,
        expanded: Boolean,
        leaf: Boolean,
        row: Int,
        hasFocus: Boolean,
    ): java.awt.Component {
        super.getTreeCellRendererComponent(tree, value, sel, expanded, leaf, row, hasFocus)
        val node = (value as? DefaultMutableTreeNode)?.userObject
        when (node) {
            is SymbolNode -> {
                text = node.label
                icon =
                    if (node.symbol.dataType?.startsWith("INTERFACE") == true) {
                        AllIcons.Nodes.Interface
                    } else {
                        AllIcons.Nodes.Class
                    }
            }
            is String -> {
                icon = null
            }
        }
        return this
    }
}

private fun extractInherits(dataType: String?): String? {
    dataType ?: return null
    val idx = dataType.indexOf("INHERITS", ignoreCase = true)
    if (idx < 0) return null
    return dataType.substring(idx + "INHERITS".length)
        .trimStart()
        .takeWhile { it.isLetterOrDigit() || it == '.' || it == '_' || it == '-' }
        .takeIf { it.isNotBlank() }
}
