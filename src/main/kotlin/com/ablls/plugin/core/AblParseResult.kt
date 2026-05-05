package com.ablls.plugin.core

import org.antlr.v4.runtime.CommonTokenStream
import org.prorefactor.proparse.antlr4.Proparse
import org.prorefactor.proparse.support.IProparseEnvironment
import org.prorefactor.treeparser.ParseUnit

/**
 * Résultat du parsing syntaxique d'un fichier ABL.
 *
 * Produit par [AblParserFacade.parse].
 * Expose l'arbre ANTLR4, le flux de tokens et les erreurs.
 *
 * [parseUnit] est initialisé de façon lazy à la première demande d'analyse sémantique.
 * Il réutilise le même [content] et [session] que le parse initial — zéro re-parse
 * si l'analyse sémantique n'est jamais demandée.
 */
class AblParseResult(
    val tree: Proparse.ProgramContext?,
    val tokens: CommonTokenStream?,
    val syntaxErrors: List<SyntaxError>,
    val uri: String,
    private val content: String = "",
    private val session: IProparseEnvironment? = null
) {
    val hasTree: Boolean get() = tree != null
    val hasSyntaxErrors: Boolean get() = syntaxErrors.isNotEmpty()

    /** ParseUnit prête pour treeParser01() — créée lazily, parse() appelé une seule fois. */
    internal val parseUnit: ParseUnit? by lazy {
        if (content.isEmpty() || session == null) return@lazy null
        runCatching {
            object : ParseUnit(content, uri, session) {}.also { it.parse() }
        }.getOrNull()
    }

    companion object {
        fun empty(uri: String) = AblParseResult(null, null, emptyList(), uri)
    }
}
