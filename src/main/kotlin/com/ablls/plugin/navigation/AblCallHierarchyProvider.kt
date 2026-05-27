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
import com.intellij.psi.PsiManager
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
 * Call Hierarchy ABL (Ctrl+Alt+H sur une procédure/fonction).
 *
 * Affiche dans un panneau dédié :
 *   - Callers : fichiers/procédures qui appellent la cible via RUN
 *   - Callees : procédures que la cible appelle via RUN
 *
 * La recherche est lexicale (`RUN procName`). Les appels OO (myObj:method)
 * nécessitent une résolution sémantique non disponible avec le PSI plat actuel.
 */
class AblCallHierarchyProvider : HierarchyProvider {
    override fun getTarget(dataContext: DataContext): PsiElement? {
        val file = dataContext.getData(CommonDataKeys.PSI_FILE) ?: return null
        val editor = dataContext.getData(CommonDataKeys.EDITOR) ?: return null
        if (file.language != AblLanguage) return null

        val element = file.findElementAt(editor.caretModel.offset) ?: return null
        val word = element.text?.trim() ?: return null
        val uri = file.virtualFile?.url ?: return null
        val service = file.project.service<AblProjectAnalysisService>()

        val isCallable =
            service.symbolIndex.findByName(word, uri).any { sym ->
                sym.kind == AblSymbol.Kind.PROCEDURE ||
                    sym.kind == AblSymbol.Kind.FUNCTION ||
                    sym.kind == AblSymbol.Kind.METHOD
            }
        return if (isCallable) element else null
    }

    override fun createHierarchyBrowser(target: PsiElement): HierarchyBrowser {
        return AblCallHierarchyBrowser(target.project, target)
    }

    override fun browserActivated(hierarchyBrowser: HierarchyBrowser) {
        (hierarchyBrowser as? AblCallHierarchyBrowser)?.refresh()
    }
}

// ─── Browser ─────────────────────────────────────────────────────────────────

class AblCallHierarchyBrowser(
    private val project: Project,
    private val target: PsiElement,
) : HierarchyBrowser {
    private val panel = JPanel(BorderLayout(0, 4))
    private var initialized = false

    override fun getComponent(): JComponent {
        panel.add(JLabel(" Loading call hierarchy…"), BorderLayout.CENTER)
        return panel
    }

    override fun setContent(content: com.intellij.ui.content.Content) {
        content.displayName = "ABL Call Hierarchy"
    }

    fun refresh() {
        if (initialized) return
        initialized = true
        SwingUtilities.invokeLater { buildUI() }
    }

    private fun buildUI() {
        panel.removeAll()
        val procName = target.text?.trim() ?: return
        val service = project.service<AblProjectAnalysisService>()

        // ── Callers ───────────────────────────────────────────────────────────
        val callerRoot = DefaultMutableTreeNode("Callers of $procName")
        buildCallers(procName, callerRoot, service)

        // ── Callees ───────────────────────────────────────────────────────────
        val calleeRoot = DefaultMutableTreeNode("Callees of $procName")
        buildCallees(procName, calleeRoot, service)

        val splitPane =
            JSplitPane(
                JSplitPane.VERTICAL_SPLIT,
                buildTreePanel(callerRoot, "Callers"),
                buildTreePanel(calleeRoot, "Callees"),
            )
        splitPane.resizeWeight = 0.5

        panel.add(splitPane, BorderLayout.CENTER)
        panel.revalidate()
        panel.repaint()
    }

    /**
     * Callers : parcourt tous les fichiers indexés à la recherche de `RUN procName`.
     * Un fichier est un caller si son texte source contient le pattern.
     */
    private fun buildCallers(
        procName: String,
        root: DefaultMutableTreeNode,
        service: AblProjectAnalysisService,
    ) {
        val runPattern = Regex("\\bRUN\\s+${Regex.escape(procName)}\\b", RegexOption.IGNORE_CASE)
        val visitedUris = mutableSetOf<String>()

        service.symbolIndex.allSymbols()
            .filter { sym ->
                (sym.kind == AblSymbol.Kind.PROCEDURE || sym.kind == AblSymbol.Kind.FUNCTION) &&
                    sym.uri != null && !sym.uri.startsWith("db://") && visitedUris.add(sym.uri)
            }
            .forEach { sym ->
                val uri = sym.uri ?: return@forEach
                val vf = VirtualFileManager.getInstance().findFileByUrl(uri) ?: return@forEach
                val psiFile = PsiManager.getInstance(project).findFile(vf) ?: return@forEach
                if (!runPattern.containsMatchIn(psiFile.text)) return@forEach
                root.add(DefaultMutableTreeNode(CallNode(sym.name, sym)))
            }
    }

    /**
     * Callees : cherche les `RUN xxx` dans le corps de la procédure cible.
     */
    private fun buildCallees(
        procName: String,
        root: DefaultMutableTreeNode,
        service: AblProjectAnalysisService,
    ) {
        val targetSym =
            service.symbolIndex.findByName(procName, "")
                .firstOrNull { it.kind == AblSymbol.Kind.PROCEDURE || it.kind == AblSymbol.Kind.FUNCTION }
                ?: return
        val uri = targetSym.uri?.takeIf { !it.startsWith("db://") } ?: return
        val vf = VirtualFileManager.getInstance().findFileByUrl(uri) ?: return
        val psiFile = PsiManager.getInstance(project).findFile(vf) ?: return

        val runPattern = Regex("\\bRUN\\s+(\\w[\\w.-]*)\\b", RegexOption.IGNORE_CASE)
        val calleeNames = runPattern.findAll(psiFile.text).map { it.groupValues[1] }.distinct()

        calleeNames.forEach { calleeName ->
            val calleeSym =
                service.symbolIndex.findByName(calleeName, "")
                    .firstOrNull { it.kind == AblSymbol.Kind.PROCEDURE || it.kind == AblSymbol.Kind.FUNCTION }
                    ?: AblSymbol(calleeName, AblSymbol.Kind.PROCEDURE, null, null, null, null)
            root.add(DefaultMutableTreeNode(CallNode(calleeName, calleeSym)))
        }
    }

    private fun buildTreePanel(
        root: DefaultMutableTreeNode,
        title: String,
    ): JPanel {
        val tree = SimpleTree(DefaultTreeModel(root))
        tree.isRootVisible = true
        tree.cellRenderer = CallTreeCellRenderer()
        tree.expandRow(0)
        tree.addMouseListener(
            object : java.awt.event.MouseAdapter() {
                override fun mouseClicked(e: java.awt.event.MouseEvent) {
                    if (e.clickCount != 2) return
                    val node = tree.lastSelectedPathComponent as? DefaultMutableTreeNode ?: return
                    (node.userObject as? CallNode)?.let { navigateTo(it.symbol) }
                }
            },
        )
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

private data class CallNode(val label: String, val symbol: AblSymbol)

private class CallTreeCellRenderer : DefaultTreeCellRenderer() {
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
            is CallNode -> {
                text = node.label
                icon =
                    when (node.symbol.kind) {
                        AblSymbol.Kind.FUNCTION -> AllIcons.Nodes.Function
                        else -> AllIcons.Nodes.Method
                    }
            }
            is String -> {
                icon = null
            }
        }
        return this
    }
}
