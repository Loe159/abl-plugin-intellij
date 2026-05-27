package com.ablls.plugin.navigation

import com.ablls.plugin.core.AblProjectAnalysisService
import com.ablls.plugin.core.AblSymbol
import com.intellij.icons.AllIcons
import com.intellij.navigation.ChooseByNameContributor
import com.intellij.navigation.ItemPresentation
import com.intellij.navigation.NavigationItem
import com.intellij.openapi.components.service
import com.intellij.openapi.fileEditor.OpenFileDescriptor
import com.intellij.openapi.project.Project
import com.intellij.openapi.vfs.VirtualFileManager
import javax.swing.Icon

/**
 * Fournisseur "Go to Symbol" (Ctrl+Alt+Shift+N) pour ABL.
 *
 * Expose toutes les procédures, fonctions, classes, méthodes et tables
 * indexées dans [com.ablls.plugin.core.AblSymbolIndex].
 * Les variables et paramètres sont exclus (trop nombreux, scope local).
 */
class AblGotoSymbolContributor : ChooseByNameContributor {
    override fun getNames(
        project: Project,
        includeNonProjectItems: Boolean,
    ): Array<String> =
        project.service<AblProjectAnalysisService>()
            .symbolIndex
            .allSymbols()
            .filter { it.isNavigable() }
            .map { it.name }
            .distinct()
            .toTypedArray()

    override fun getItemsByName(
        name: String,
        pattern: String,
        project: Project,
        includeNonProjectItems: Boolean,
    ): Array<NavigationItem> =
        project.service<AblProjectAnalysisService>()
            .symbolIndex
            .findByName(name, "")
            .filter { it.isNavigable() }
            .map { AblNavigationItem(it, project) }
            .toTypedArray()

    private fun AblSymbol.isNavigable(): Boolean =
        when (kind) {
            AblSymbol.Kind.PROCEDURE,
            AblSymbol.Kind.FUNCTION,
            AblSymbol.Kind.CLASS,
            AblSymbol.Kind.METHOD,
            AblSymbol.Kind.TABLE,
            AblSymbol.Kind.TEMP_TABLE,
            AblSymbol.Kind.EVENT,
            -> true
            else -> false
        }
}

/**
 * Fournisseur "Go to Class" (Ctrl+N) pour ABL — restreint aux CLASS/INTERFACE/ENUM.
 */
class AblGotoClassContributor : ChooseByNameContributor {
    override fun getNames(
        project: Project,
        includeNonProjectItems: Boolean,
    ): Array<String> =
        project.service<AblProjectAnalysisService>()
            .symbolIndex
            .allSymbols()
            .filter { it.kind == AblSymbol.Kind.CLASS }
            .map { it.name }
            .distinct()
            .toTypedArray()

    override fun getItemsByName(
        name: String,
        pattern: String,
        project: Project,
        includeNonProjectItems: Boolean,
    ): Array<NavigationItem> =
        project.service<AblProjectAnalysisService>()
            .symbolIndex
            .findByName(name, "")
            .filter { it.kind == AblSymbol.Kind.CLASS }
            .map { AblNavigationItem(it, project) }
            .toTypedArray()
}

// ─── NavigationItem ───────────────────────────────────────────────────────────

class AblNavigationItem(
    private val symbol: AblSymbol,
    private val project: Project,
) : NavigationItem {
    override fun getName(): String = symbol.name

    override fun getPresentation(): ItemPresentation =
        object : ItemPresentation {
            override fun getPresentableText(): String = symbol.name

            override fun getLocationString(): String? =
                symbol.uri
                    ?.removePrefix("file://")
                    ?.removePrefix("db://")
                    ?.let { path ->
                        // Show only filename + dataType
                        val file = path.substringAfterLast('/')
                        if (symbol.dataType != null) "$file — ${symbol.dataType}" else file
                    }

            override fun getIcon(unused: Boolean): Icon = iconFor(symbol.kind)
        }

    override fun navigate(requestFocus: Boolean) {
        val uri = symbol.uri?.takeIf { !it.startsWith("db://") } ?: return
        val vf = VirtualFileManager.getInstance().findFileByUrl(uri) ?: return
        val line = (symbol.definitionRange?.startLine ?: 0).coerceAtLeast(0)
        val col = (symbol.definitionRange?.startCol ?: 0).coerceAtLeast(0)
        OpenFileDescriptor(project, vf, line, col).navigate(requestFocus)
    }

    override fun canNavigate(): Boolean {
        val uri = symbol.uri ?: return false
        return !uri.startsWith("db://")
    }

    override fun canNavigateToSource(): Boolean = canNavigate()

    private fun iconFor(kind: AblSymbol.Kind): Icon =
        when (kind) {
            AblSymbol.Kind.PROCEDURE -> AllIcons.Nodes.Method
            AblSymbol.Kind.FUNCTION -> AllIcons.Nodes.Function
            AblSymbol.Kind.CLASS -> AllIcons.Nodes.Class
            AblSymbol.Kind.METHOD -> AllIcons.Nodes.Method
            AblSymbol.Kind.TABLE -> AllIcons.Nodes.DataTables
            AblSymbol.Kind.TEMP_TABLE -> AllIcons.Nodes.DataTables
            AblSymbol.Kind.EVENT -> AllIcons.Nodes.Method
            else -> AllIcons.Nodes.Unknown
        }
}
