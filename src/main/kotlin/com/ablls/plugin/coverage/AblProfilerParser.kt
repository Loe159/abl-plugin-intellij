package com.ablls.plugin.coverage

import java.io.File

/**
 * Parse les fichiers de profiler OpenEdge (.prof) pour extraire la couverture
 * et les counts d'exécution par ligne.
 *
 * Expose deux API :
 *   - [parse]            → fichier → lignes couvertes (Set<Int>)
 *   - [parseWithCounts]  → fichier → ligne → count d'exécution (Map<Int,Int>)
 *
 * Tente d'abord l'API RSSW profiler si disponible, puis fallback textuel.
 */
object AblProfilerParser {

    /** Couverture seule : chemin source → ensemble des numéros de lignes couvertes. */
    fun parse(profFile: File): Map<String, Set<Int>> =
        parseWithCounts(profFile).mapValues { (_, counts) -> counts.keys }

    /**
     * Couverture + counts : chemin source → (numéro de ligne 1-based → count d'exécution).
     * Seules les lignes avec count > 0 sont incluses.
     */
    fun parseWithCounts(profFile: File): Map<String, Map<Int, Int>> {
        return try {
            parseWithCountsViaRssw(profFile)
        } catch (_: Exception) {
            parseWithCountsTextFormat(profFile)
        }
    }

    // ─── Tentative via l'API RSSW ─────────────────────────────────────────────

    private fun parseWithCountsViaRssw(file: File): Map<String, Map<Int, Int>> {
        val profilerClass = try {
            Class.forName("eu.rssw.openedge.parsers.profiler.ProfilerData")
        } catch (_: ClassNotFoundException) {
            Class.forName("eu.rssw.openedge.parsers.profiler.ProfilerSession")
        }

        val instance = profilerClass.getDeclaredMethod("parse", File::class.java).invoke(null, file)
        val modules  = profilerClass.getMethod("getModules").invoke(instance) as? List<*>
            ?: return emptyMap()

        val result = mutableMapOf<String, MutableMap<Int, Int>>()
        for (module in modules) {
            if (module == null) continue
            val moduleClass = module.javaClass
            val fileName    = runCatching {
                moduleClass.getMethod("getFileName").invoke(module) as? String
            }.getOrNull() ?: continue
            val lines = runCatching {
                moduleClass.getMethod("getLineSummary").invoke(module) as? List<*>
            }.getOrNull() ?: continue

            val fileCounts = result.getOrPut(fileName) { mutableMapOf() }
            for (lineInfo in lines) {
                if (lineInfo == null) continue
                val lineClass  = lineInfo.javaClass
                val lineNum    = runCatching {
                    lineClass.getMethod("getLineNum").invoke(lineInfo) as? Int
                }.getOrNull() ?: continue
                val execCount  = runCatching {
                    lineClass.getMethod("getExecutionCount").invoke(lineInfo) as? Int
                }.getOrNull() ?: 0
                if (execCount > 0) fileCounts[lineNum] = execCount
            }
        }
        return result
    }

    // ─── Fallback texte brut ──────────────────────────────────────────────────

    /**
     * Format Progress profiler :
     *   MODULE <num> "<file>" <elapsed>
     *   TRACING "<file>"
     *   <lineNum> <execCount> <elapsed> [<moduleNum>]
     */
    private fun parseWithCountsTextFormat(file: File): Map<String, Map<Int, Int>> {
        val result  = mutableMapOf<String, MutableMap<Int, Int>>()
        val modules = mutableMapOf<Int, String>()
        var current: String? = null

        file.forEachLine { rawLine ->
            val line = rawLine.trim()
            when {
                line.startsWith("MODULE") -> {
                    val parts = line.split("\\s+".toRegex())
                    if (parts.size >= 3) {
                        val num  = parts[1].toIntOrNull() ?: return@forEachLine
                        val name = parts[2].trim('"')
                        modules[num] = name
                        current = name
                    }
                }
                line.startsWith("TRACING") -> {
                    current = line.substringAfter(" ").trim().trim('"')
                }
                line.matches(Regex("\\d+\\s+\\d+.*")) && current != null -> {
                    val parts     = line.split("\\s+".toRegex())
                    val lineNum   = parts[0].toIntOrNull() ?: return@forEachLine
                    val execCount = parts.getOrNull(1)?.toIntOrNull() ?: 0
                    if (execCount > 0) {
                        result.getOrPut(current!!) { mutableMapOf() }[lineNum] = execCount
                    }
                }
            }
        }
        return result
    }
}
