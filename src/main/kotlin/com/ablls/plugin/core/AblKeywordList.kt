package com.ablls.plugin.core

import org.prorefactor.core.ABLNodeType

/**
 * Liste exhaustive des mots-clés ABL pour l'autocomplétion.
 *
 * Construite dynamiquement depuis [ABLNodeType] (proparse) — source de vérité officielle RSSW.
 * Inclut les formes complètes ET les formes abrégées (ex. CHAR pour CHARACTER, PROC pour PROCEDURE).
 * Se met à jour automatiquement avec chaque version de proparse.
 */
object AblKeywordList {

    val KEYWORDS: Set<String> by lazy {
        buildSet {
            for (type in ABLNodeType.values()) {
                if (!type.isKeyword()) continue
                val text = type.getText() ?: continue
                if (text.isNotBlank()) add(text.uppercase())
                type.alternate?.let  { alt -> if (alt.isNotBlank()) add(alt.uppercase()) }
                type.alternate2?.let { alt -> if (alt.isNotBlank()) add(alt.uppercase()) }
            }
        }
    }
}
