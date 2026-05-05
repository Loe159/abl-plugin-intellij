package com.ablls.plugin.core

import org.prorefactor.core.ABLNodeType

object AblProparseKeywords {
    val ALL: Set<String> by lazy {
        ABLNodeType.values()
            .filter { it.isKeyword }
            .mapNotNull { it.text?.uppercase()?.takeIf { t -> t.isNotBlank() } }
            .toSet()
    }
}
