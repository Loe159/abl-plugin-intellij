package com.ablls.plugin.coverage

import java.io.File

/**
 * Parse les fichiers de profiler OpenEdge (.prof) pour extraire les données
 * de couverture de code.
 *
 * Le format profiler Progress est un fichier texte structuré en sections.
 * Tente d'utiliser eu.rssw.openedge.parsers.profiler si disponible,
 * sinon fallback sur le parsing textuel natif.
 *
 * Retourne : chemin source ABL → ensemble des numéros de lignes couvertes.
 */
object AblProfilerParser {

    fun parse(profFile: File): Map<String, Set<Int>> {
        return try {
            parseViaRssw(profFile)
        } catch (_: Exception) {
            parseTextFormat(profFile)
        }
    }

    /**
     * Tentative d'utilisation de l'API RSSW profiler-parser.
     * Le nom exact de la classe dépend de la version du jar.
     */
    private fun parseViaRssw(file: File): Map<String, Set<Int>> {
        // L'API publique expose ProfilerData ou ProfilerSession
        val profilerClass = try {
            Class.forName("eu.rssw.openedge.parsers.profiler.ProfilerData")
        } catch (_: ClassNotFoundException) {
            Class.forName("eu.rssw.openedge.parsers.profiler.ProfilerSession")
        }

        val instance = profilerClass.getDeclaredMethod("parse", File::class.java)
            .invoke(null, file)

        @Suppress("UNCHECKED_CAST")
        val moduleMethod = profilerClass.getMethod("getModules")
        val modules = moduleMethod.invoke(instance) as? List<*> ?: return emptyMap()

        val result = mutableMapOf<String, MutableSet<Int>>()
        for (module in modules) {
            if (module == null) continue
            val moduleClass  = module.javaClass
            val fileName     = runCatching { moduleClass.getMethod("getFileName").invoke(module) as? String }.getOrNull() ?: continue
            val linesMethod  = runCatching { moduleClass.getMethod("getLineSummary") }.getOrNull() ?: continue
            val lines        = linesMethod.invoke(module) as? List<*> ?: continue
            val covered      = result.getOrPut(fileName) { mutableSetOf() }
            for (lineInfo in lines) {
                if (lineInfo == null) continue
                val lineClass  = lineInfo.javaClass
                val lineNum    = runCatching { lineClass.getMethod("getLineNum").invoke(lineInfo) as? Int }.getOrNull() ?: continue
                val execCount  = runCatching { lineClass.getMethod("getExecutionCount").invoke(lineInfo) as? Int }.getOrNull() ?: 0
                if (execCount > 0) covered.add(lineNum)
            }
        }
        return result
    }

    /**
     * Fallback : parse le format texte Progress profiler.
     * Format simplifié :
     *   MODULE <num> <fileName> <elapsed>
     *   <lineNum> <execCount> <elapsed> [<moduleNum>]
     */
    private fun parseTextFormat(file: File): Map<String, Set<Int>> {
        val result = mutableMapOf<String, MutableSet<Int>>()
        val modules = mutableMapOf<Int, String>()   // moduleNum → fileName
        var currentModule: String? = null

        file.forEachLine { rawLine ->
            val line = rawLine.trim()
            when {
                line.startsWith("MODULE") -> {
                    // MODULE <num> <file> ...
                    val parts = line.split("\\s+".toRegex())
                    if (parts.size >= 3) {
                        val num = parts[1].toIntOrNull() ?: return@forEachLine
                        modules[num] = parts[2]
                        currentModule = parts[2]
                    }
                }
                line.startsWith("TRACING") -> {
                    // TRACING <file>
                    currentModule = line.substringAfter(" ").trim()
                }
                line.matches(Regex("\\d+\\s+\\d+.*")) && currentModule != null -> {
                    val parts    = line.split("\\s+".toRegex())
                    val lineNum  = parts[0].toIntOrNull() ?: return@forEachLine
                    val execCount = parts.getOrNull(1)?.toIntOrNull() ?: 0
                    if (execCount > 0) {
                        result.getOrPut(currentModule!!) { mutableSetOf() }.add(lineNum)
                    }
                }
            }
        }
        return result
    }
}
