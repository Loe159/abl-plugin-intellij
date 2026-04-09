package com.ablls.plugin.core

import org.antlr.v4.runtime.CommonTokenStream
import org.prorefactor.proparse.antlr4.Proparse

/**
 * Résultat du parsing syntaxique d'un fichier ABL.
 *
 * Produit par [AblParserFacade.parse].
 * Contient l'arbre ANTLR4 (Proparse), le flux de tokens et les erreurs.
 */
class AblParseResult(
    val tree: Proparse.ProgramContext?,
    val tokens: CommonTokenStream?,
    val syntaxErrors: List<SyntaxError>,
    val uri: String
) {
    val hasTree: Boolean get() = tree != null
    val hasSyntaxErrors: Boolean get() = syntaxErrors.isNotEmpty()

    companion object {
        fun empty(uri: String) = AblParseResult(null, null, emptyList(), uri)
    }
}
