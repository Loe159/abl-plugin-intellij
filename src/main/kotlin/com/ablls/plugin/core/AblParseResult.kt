package com.ablls.plugin.core

import org.antlr.v4.runtime.CommonTokenStream
import org.prorefactor.core.JPNode
import org.prorefactor.proparse.antlr4.Proparse

/**
 * Résultat du parsing syntaxique d'un fichier ABL.
 *
 * Produit par [AblParserFacade.parse].
 * Contient l'arbre ANTLR4 (Proparse), le flux de tokens, les erreurs,
 * et le JPNode tree RSSW pour la traversal structurelle (inspections).
 */
class AblParseResult(
    val tree: Proparse.ProgramContext?,
    val tokens: CommonTokenStream?,
    val syntaxErrors: List<SyntaxError>,
    val uri: String,
    val topNode: JPNode? = null,
    val preprocessorMessages: List<String> = emptyList()
) {
    val hasTree: Boolean get() = tree != null
    val hasSyntaxErrors: Boolean get() = syntaxErrors.isNotEmpty()

    companion object {
        fun empty(uri: String) = AblParseResult(null, null, emptyList(), uri)
    }
}
