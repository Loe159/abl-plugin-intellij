package com.ablls.plugin.duplication

import org.antlr.v4.runtime.Token
import org.antlr.v4.runtime.TokenStream
import org.prorefactor.core.ABLNodeType

/**
 * Normalise le TokenStream ABL pour la détection de duplicats.
 * - Filtre le hidden channel (commentaires, espaces)
 * - Collapse les littéraux string → "<STR>"
 * - Collapse les littéraux numériques → "<NUM>"
 * - Met tout en majuscules (case-insensitive)
 */
object AblTokenNormalizer {

    data class NormalToken(
        val text: String,
        val type: Int,
        val line: Int,
        val index: Int
    )

    private val QSTRING_TYPE = ABLNodeType.QSTRING.getType()
    private val NUMBER_TYPE  = ABLNodeType.NUMBER.getType()

    fun normalize(tokens: TokenStream): List<NormalToken> {
        val result = mutableListOf<NormalToken>()
        val size   = tokens.size()
        for (i in 0 until size) {
            val t = tokens.get(i)
            if (t.channel != Token.DEFAULT_CHANNEL) continue
            if (t.type == Token.EOF) break

            val normalized = when (t.type) {
                QSTRING_TYPE -> "<STR>"
                NUMBER_TYPE  -> "<NUM>"
                else         -> t.text?.uppercase() ?: continue
            }
            result += NormalToken(normalized, t.type, t.line, i)
        }
        return result
    }
}
