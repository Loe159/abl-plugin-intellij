package com.ablls.plugin.duplication

import com.ablls.plugin.core.AblParseResult

/**
 * Détecte les fragments de code dupliqués dans un ensemble de fichiers ABL.
 *
 * Algorithme : fenêtre glissante de [minTokens] tokens normalisés.
 * Un hash est calculé pour chaque fenêtre. Si deux fenêtres ont le même hash
 * et les mêmes tokens normalisés, elles constituent un duplicat.
 */
class AblDuplicationDetector(val minTokens: Int = 50) {

    data class Fragment(
        val uri: String,
        val startLine: Int,
        val endLine: Int,
        val tokenCount: Int
    )

    data class DuplicatePair(val a: Fragment, val b: Fragment)

    fun detect(files: Map<String, AblParseResult>): List<DuplicatePair> {
        // uri → liste de fenêtres (startIndex dans tokens, tokens normalisés)
        val buckets = HashMap<Long, MutableList<Pair<String, List<AblTokenNormalizer.NormalToken>>>>(1024)

        for ((uri, result) in files) {
            val rawTokens = result.tokens ?: continue
            val tokens    = AblTokenNormalizer.normalize(rawTokens)
            if (tokens.size < minTokens) continue

            for (start in 0..tokens.size - minTokens) {
                val window = tokens.subList(start, start + minTokens)
                val hash   = computeHash(window)
                buckets.getOrPut(hash) { mutableListOf() } += uri to window
            }
        }

        val pairs = mutableListOf<DuplicatePair>()
        for ((_, candidates) in buckets) {
            if (candidates.size < 2) continue
            for (i in 0 until candidates.size - 1) {
                val (uriA, wA) = candidates[i]
                val (uriB, wB) = candidates[i + 1]

                // Ignorer les fenêtres qui se chevauchent dans le même fichier
                if (uriA == uriB && wA.first().line == wB.first().line) continue

                // Vérification exacte (évite les collisions de hash)
                if (wA.map { it.text } != wB.map { it.text }) continue

                pairs += DuplicatePair(
                    Fragment(uriA, wA.first().line, wA.last().line, minTokens),
                    Fragment(uriB, wB.first().line, wB.last().line, minTokens)
                )
            }
        }

        return pairs.distinctBy {
            setOf(
                it.a.uri to it.a.startLine,
                it.b.uri to it.b.startLine
            )
        }
    }

    private fun computeHash(tokens: List<AblTokenNormalizer.NormalToken>): Long {
        var hash = 17L
        for (t in tokens) { hash = hash * 31 + t.text.hashCode() }
        return hash
    }
}
