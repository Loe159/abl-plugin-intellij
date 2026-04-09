package com.ablls.plugin.duplication

import org.antlr.v4.runtime.Token
import org.antlr.v4.runtime.TokenStream

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

    fun normalize(tokens: TokenStream): List<NormalToken> {
        val result = mutableListOf<NormalToken>()
        val size   = tokens.size()
        for (i in 0 until size) {
            val t = tokens.get(i)
            if (t.channel != Token.DEFAULT_CHANNEL) continue
            if (t.type == Token.EOF) break

            val normalized = when {
                isStringLiteral(t)  -> "<STR>"
                isNumericLiteral(t) -> "<NUM>"
                else                -> t.text?.uppercase() ?: continue
            }
            result += NormalToken(normalized, t.type, t.line, i)
        }
        return result
    }

    private fun isStringLiteral(t: Token): Boolean {
        val text = t.text ?: return false
        return text.startsWith("\"") || text.startsWith("'")
    }

    private fun isNumericLiteral(t: Token): Boolean {
        val text = t.text ?: return false
        return text.matches(Regex("-?\\d+(\\.\\d+)?"))
    }
}
