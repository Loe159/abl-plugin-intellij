package com.ablls.plugin.core

import org.prorefactor.core.JPNode
import org.prorefactor.treeparser.TreeParserSymbolScope


/**
 * Résultat de l'analyse sémantique complète via [ParseUnit.treeParser01].
 *
 * Produit par [AblParserFacade.analyze].
 * Contient le JPNode tree enrichi (symboles attachés), le scope racine et les erreurs.
 *
 * Disponible uniquement après l'analyse sémantique (background) — plus lente
 * que le simple parsing syntaxique mais donne accès à :
 *   - [topNode] : JPNode avec [JPNode.getSymbol] résolu sur chaque nœud référence
 *   - [rootScope] : scope racine → [TreeParserSymbolScope.lookupVariable], lookupRoutine...
 *   - Signatures complètes des routines via [org.prorefactor.treeparser.symbols.Routine.getIDESignature]
 *   - Types résolus des variables via [org.prorefactor.treeparser.symbols.Variable.getDataType]
 */
class AblSemanticResult(
    val topNode: JPNode?,
    val rootScope: TreeParserSymbolScope?,
    val syntaxErrors: List<SyntaxError>,
    val uri: String
) {
    val hasTree: Boolean get() = topNode != null

    companion object {
        fun empty(uri: String) = AblSemanticResult(null, null, emptyList(), uri)
    }
}
