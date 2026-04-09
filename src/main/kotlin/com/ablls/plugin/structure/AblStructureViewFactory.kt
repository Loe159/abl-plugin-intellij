package com.ablls.plugin.structure

import com.ablls.plugin.core.AblProjectAnalysisService
import com.ablls.plugin.core.AblSymbol
import com.ablls.plugin.language.AblIcons
import com.intellij.icons.AllIcons
import com.intellij.ide.structureView.*
import com.intellij.ide.util.treeView.smartTree.TreeElement
import com.intellij.lang.PsiStructureViewFactory
import com.intellij.navigation.ItemPresentation
import com.intellij.openapi.components.service
import com.intellij.openapi.editor.Editor
import com.intellij.psi.PsiDocumentManager
import com.intellij.psi.PsiElement
import com.intellij.psi.PsiFile
import javax.swing.Icon

/**
 * Panneau "Structure" (Alt+7) pour les fichiers ABL.
 *
 * Affiche la hiérarchie des symboles extraits par [AblProjectAnalysisService] :
 *   Fichier.p
 *   ├── PROCEDURE myProc
 *   ├── FUNCTION myFunc RETURNS CHARACTER
 *   └── CLASS com.myapp.MyClass
 *       ├── CONSTRUCTOR MyClass
 *       ├── PROPERTY counter AS INTEGER
 *       ├── METHOD doSomething
 *       └── EVENT onChanged
 *
 * La structure est construite depuis [AblSymbolIndex] — toujours disponible
 * sans attendre l'analyse LSP.
 */
class AblStructureViewFactory : PsiStructureViewFactory {

    override fun getStructureViewBuilder(psiFile: PsiFile): StructureViewBuilder {
        return object : TreeBasedStructureViewBuilder() {
            override fun createStructureViewModel(editor: Editor?): StructureViewModel =
                AblStructureViewModel(psiFile, editor)
            override fun isRootNodeShown(): Boolean = false
        }
    }
}

// ─── ViewModel ────────────────────────────────────────────────────────────────

class AblStructureViewModel(
    private val psiFile: PsiFile,
    editor: Editor?
) : StructureViewModelBase(psiFile, editor, AblFileStructureElement(psiFile)),
    StructureViewModel.ElementInfoProvider {

    override fun isAlwaysShowsPlus(element: StructureViewTreeElement): Boolean = false
    override fun isAlwaysLeaf(element: StructureViewTreeElement): Boolean = false
}

// ─── Élément racine (fichier) ─────────────────────────────────────────────────

class AblFileStructureElement(
    private val psiFile: PsiFile
) : StructureViewTreeElement {

    override fun getValue(): Any = psiFile
    override fun navigate(requestFocus: Boolean) = (psiFile as? com.intellij.psi.NavigatablePsiElement)?.navigate(requestFocus) ?: Unit
    override fun canNavigate(): Boolean = true
    override fun canNavigateToSource(): Boolean = true

    override fun getPresentation(): ItemPresentation = object : ItemPresentation {
        override fun getPresentableText(): String = psiFile.name
        override fun getIcon(unused: Boolean): Icon = AblIcons.FILE
        override fun getLocationString(): String? = null
    }

    override fun getChildren(): Array<TreeElement> {
        val uri     = psiFile.virtualFile?.url ?: return emptyArray()
        val service = psiFile.project.service<AblProjectAnalysisService>()

        // Forcer l'analyse si pas encore faite
        val content = psiFile.text
        service.analyzeFile(content, uri)
        // Lance l'analyse sémantique en background pour la prochaine ouverture
        service.analyzeSemanticAsync(content, uri)

        val symbols = service.symbolIndex.getSymbolsForFile(uri)

        // Construire l'arbre : les symboles de haut niveau (non-membres) sont les racines
        // Les méthodes/propriétés qualifiées (ClassName:member) sont des enfants
        val topLevel = symbols.filter { !it.name.contains(':') }
        return topLevel.map { symbol ->
            val children = symbols.filter {
                it.name.startsWith("${symbol.name}:") && it.name.count { c -> c == ':' } == 1
            }
            AblSymbolStructureElement(symbol, children, psiFile)
        }.toTypedArray()
    }
}

// ─── Élément symbole ──────────────────────────────────────────────────────────

class AblSymbolStructureElement(
    private val symbol: AblSymbol,
    private val children: List<AblSymbol>,
    private val psiFile: PsiFile
) : StructureViewTreeElement {

    override fun getValue(): Any = symbol

    override fun navigate(requestFocus: Boolean) {
        val range = symbol.definitionRange ?: return
        val doc   = PsiDocumentManager.getInstance(psiFile.project).getDocument(psiFile) ?: return
        val line  = range.startLine.coerceIn(0, doc.lineCount - 1)
        val offset = (doc.getLineStartOffset(line) + range.startCol).coerceAtMost(doc.textLength)
        val element = psiFile.findElementAt(offset) ?: return
        (element as? com.intellij.psi.NavigatablePsiElement)?.navigate(requestFocus)
    }

    override fun canNavigate(): Boolean = symbol.definitionRange != null
    override fun canNavigateToSource(): Boolean = canNavigate()

    override fun getPresentation(): ItemPresentation = object : ItemPresentation {
        override fun getPresentableText(): String {
            val shortName = symbol.name.substringAfterLast(':')
            return when (symbol.kind) {
                AblSymbol.Kind.PROCEDURE  -> "PROCEDURE $shortName"
                AblSymbol.Kind.FUNCTION   -> {
                    val ret = symbol.dataType?.removePrefix("FUNCTION RETURNS ")?.trim() ?: "VOID"
                    "FUNCTION $shortName RETURNS $ret"
                }
                AblSymbol.Kind.METHOD     -> {
                    val ret = symbol.dataType?.removePrefix("METHOD RETURNS ")?.trim() ?: "VOID"
                    "METHOD $shortName RETURNS $ret"
                }
                AblSymbol.Kind.CLASS      -> "${symbol.dataType ?: "CLASS"} $shortName"
                AblSymbol.Kind.VARIABLE   -> "$shortName : ${symbol.dataType ?: "?"}"
                AblSymbol.Kind.PARAMETER  -> "PARAM $shortName : ${symbol.dataType ?: "?"}"
                AblSymbol.Kind.FIELD      -> {
                    val type = symbol.dataType?.removePrefix("PROPERTY ")?.trim() ?: "?"
                    "PROPERTY $shortName : $type"
                }
                AblSymbol.Kind.TEMP_TABLE -> "TEMP-TABLE $shortName"
                AblSymbol.Kind.BUFFER     -> "$shortName (${symbol.dataType ?: "BUFFER"})"
                AblSymbol.Kind.DATASET    -> "DATASET $shortName"
                AblSymbol.Kind.QUERY      -> "QUERY $shortName"
                AblSymbol.Kind.EVENT      -> "EVENT $shortName"
                else                      -> shortName
            }
        }

        override fun getIcon(unused: Boolean): Icon = iconFor(symbol.kind)
        override fun getLocationString(): String? = null
    }

    override fun getChildren(): Array<TreeElement> =
        children.map { AblSymbolStructureElement(it, emptyList(), psiFile) }.toTypedArray()
}

// ─── Icônes par kind ──────────────────────────────────────────────────────────

private fun iconFor(kind: AblSymbol.Kind): Icon = when (kind) {
    AblSymbol.Kind.PROCEDURE  -> AllIcons.Nodes.Method
    AblSymbol.Kind.FUNCTION   -> AllIcons.Nodes.Function
    AblSymbol.Kind.CLASS      -> AllIcons.Nodes.Class
    AblSymbol.Kind.METHOD     -> AllIcons.Nodes.Method
    AblSymbol.Kind.VARIABLE   -> AllIcons.Nodes.Variable
    AblSymbol.Kind.PARAMETER  -> AllIcons.Nodes.Parameter
    AblSymbol.Kind.FIELD      -> AllIcons.Nodes.Field
    AblSymbol.Kind.TEMP_TABLE -> AllIcons.Nodes.DataTables
    AblSymbol.Kind.BUFFER     -> AllIcons.Nodes.DataTables
    AblSymbol.Kind.DATASET    -> AllIcons.Nodes.DataSchema
    AblSymbol.Kind.QUERY      -> AllIcons.Nodes.DataSchema
    AblSymbol.Kind.EVENT      -> AllIcons.Nodes.Method
    else                      -> AblIcons.FILE
}
