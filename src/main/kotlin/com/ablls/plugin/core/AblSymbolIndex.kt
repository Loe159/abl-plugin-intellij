package com.ablls.plugin.core

import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.CopyOnWriteArrayList

/**
 * Index global des symboles ABL pour tout le workspace.
 *
 * Thread-safe. Alimenté par [AblProjectAnalysisService] à chaque analyse de fichier.
 * Utilisé par la complétion, hover, go to definition.
 */
class AblSymbolIndex {

    /** URI → symboles définis dans ce fichier */
    private val byFile = ConcurrentHashMap<String, List<AblSymbol>>()

    /** nom (lowercase) → tous les symboles portant ce nom */
    private val byName = ConcurrentHashMap<String, CopyOnWriteArrayList<AblSymbol>>()

    // ─── Mise à jour ──────────────────────────────────────────────────────────

    fun updateFile(uri: String, symbols: List<AblSymbol>) {
        val old = byFile.put(uri, symbols) ?: emptyList()
        // Retirer les anciens symboles
        old.forEach { s ->
            byName[s.name.lowercase()]?.remove(s)
        }
        // Ajouter les nouveaux
        symbols.forEach { s ->
            byName.getOrPut(s.name.lowercase()) { CopyOnWriteArrayList() }.add(s)
        }
    }

    fun removeFile(uri: String) {
        val removed = byFile.remove(uri) ?: return
        removed.forEach { s ->
            byName[s.name.lowercase()]?.remove(s)
        }
    }

    fun clear() {
        byFile.clear()
        byName.clear()
    }

    // ─── Recherche ────────────────────────────────────────────────────────────

    /** Tous les symboles dont le nom commence par [prefix]. Fichier courant en premier. */
    fun findByPrefix(prefix: String, currentUri: String): List<AblSymbol> {
        val lp = prefix.lowercase()
        val result = mutableListOf<AblSymbol>()
        // Locaux d'abord
        byFile[currentUri]?.filter { it.name.lowercase().startsWith(lp) }?.forEach { result.add(it) }
        // Globaux
        byName.entries
            .filter { it.key.startsWith(lp) }
            .flatMap { it.value }
            .filter { it.uri != currentUri }
            .forEach { result.add(it) }
        return result
    }

    /** Tous les symboles portant exactement ce nom (case-insensitive). Fichier courant en premier. */
    fun findByName(name: String, currentUri: String): List<AblSymbol> {
        if (name.isBlank()) return emptyList()
        val all = byName[name.lowercase()] ?: return emptyList()
        return all.sortedWith(compareBy { if (it.uri == currentUri) 0 else 1 })
    }

    /** Symboles définis dans un fichier. */
    fun getSymbolsForFile(uri: String): List<AblSymbol> =
        byFile[uri] ?: emptyList()

    /** Nombre total de symboles indexés. */
    val symbolCount: Int get() = byFile.values.sumOf { it.size }
}
