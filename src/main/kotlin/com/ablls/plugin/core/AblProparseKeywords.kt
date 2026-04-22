package com.ablls.plugin.core

import org.prorefactor.core.ABLNodeType

/**
 * All ABL keywords derived from ABLNodeType (proparse / RSSW).
 * Derives the authoritative keyword set from ABLNodeType (proparse / RSSW).
 */
object AblProparseKeywords {
    val ALL: Set<String> by lazy {
        buildSet {
            for (nodeType in ABLNodeType.values()) {
                if (!nodeType.isKeyword) continue
                val text = runCatching { nodeType.text }.getOrNull()?.uppercase() ?: continue
                if (text.isNotBlank()) add(text)
            }
        }
    }
}
