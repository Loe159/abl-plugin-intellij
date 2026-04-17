package com.ablls.plugin.core

import com.intellij.openapi.diagnostic.Logger
import com.intellij.openapi.project.Project
import com.intellij.openapi.vfs.VfsUtilCore
import com.intellij.openapi.vfs.VirtualFile
import com.intellij.psi.search.FileTypeIndex
import com.intellij.psi.search.GlobalSearchScope
import com.ablls.plugin.language.AblFileType
import org.prorefactor.core.JPNode
import org.prorefactor.treeparser.symbols.Symbol

data class AblUsage(
    val uri: String,
    val range: AblRange,
    val symbol: AblSymbol
)

/**
 * Collecte les usages d'un symbole ABL donné en parcourant l'arbre sémantique JPNode.
 *
 * Cette classe traverse l'arbre JPNode généré par l'analyse sémantique (treeParser01())
 * et identifie tous les nœuds où JPNode.getSymbol() correspond au symbole cible.
 */
object AblUsagesCollector {

    private val LOG = Logger.getInstance(AblUsagesCollector::class.java)

    /**
     * Collecte tous les usages d'un symbole donné dans un fichier.
     *
     * @param topNode Le nœud JPNode racine de l'arbre sémantique du fichier.
     * @param targetSymbol Le symbole ABL dont on cherche les usages.
     * @param uri L'URI du fichier en cours d'analyse.
     * @return Une liste de [AblUsage] représentant les occurrences du symbole.
     */
    fun collectUsages(topNode: JPNode?, targetSymbol: AblSymbol, uri: String): List<AblUsage> {
        if (topNode == null) return emptyList()

        val usages = mutableListOf<AblUsage>()
        traverseAndCollect(topNode, targetSymbol.name, targetSymbol.kind, uri, usages)
        return usages
    }

    private fun traverseAndCollect(
        node: JPNode,
        targetName: String,
        targetKind: AblSymbol.Kind,
        uri: String,
        usages: MutableList<AblUsage>
    ) {
        val symbol = node.getSymbol()
        if (symbol != null) {
            val symbolName = runCatching { symbol.javaClass.getMethod("getName").invoke(symbol) as? String }.getOrNull()
            val symbolKind = mapProparseSymbolKind(symbol)

            if (symbolName != null && symbolName.equals(targetName, ignoreCase = true) && symbolKind == targetKind) {
                node.token?.let { token ->
                    val range = AblRange(
                        startLine = (token.line - 1).coerceAtLeast(0),
                        startCol = token.charPositionInLine,
                        endLine = (token.line - 1).coerceAtLeast(0),
                        endCol = token.charPositionInLine + token.text.length
                    )
                    usages.add(AblUsage(uri, range, AblSymbol(targetName, targetKind, uri, null, null, null))) // Simplified AblSymbol for usage
                }
            }
        }

        var child = node.firstChild
        while (child != null) {
            traverseAndCollect(child, targetName, targetKind, uri, usages)
            child = child.nextSibling
        }
    }

    /**
     * Mappe une instance de org.prorefactor.treeparser.symbols.Symbol à notre AblSymbol.Kind.
     * Ceci est nécessaire car Proparse utilise une hiérarchie de classes pour les symboles,
     * et non une énumération directe des kinds.
     */
    private fun mapProparseSymbolKind(proparseSymbol: Symbol): AblSymbol.Kind {
        return when (proparseSymbol.javaClass.simpleName) {
            "Variable" -> AblSymbol.Kind.VARIABLE
            "Parameter" -> AblSymbol.Kind.PARAMETER
            "Routine" -> {
                val routineName = (proparseSymbol.javaClass.getMethod("getName").invoke(proparseSymbol) as? String) ?: ""
                if (routineName.contains("::")) AblSymbol.Kind.METHOD else {
                    // This is a simplification; a full implementation would check for FUNCTION/PROCEDURE keywords
                    AblSymbol.Kind.PROCEDURE
                }
            }
            // Ajoutez d'autres mappings au besoin
            else -> AblSymbol.Kind.UNKNOWN
        }
    }

    /**
     * Retourne tous les fichiers ABL dans le projet qui pourraient contenir des usages.
     * Ceci est une version simplifiée et devrait être optimisée pour les grands projets.
     */
    fun getAllAblFilesInProject(project: Project): List<VirtualFile> {
        val scope = GlobalSearchScope.projectScope(project)
        return FileTypeIndex.getFiles(AblFileType.INSTANCE, scope).toList()
    }
}
