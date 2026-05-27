package com.ablls.plugin.coverage

import com.intellij.openapi.components.Service
import com.intellij.openapi.editor.Editor
import com.intellij.openapi.editor.markup.HighlighterLayer
import com.intellij.openapi.editor.markup.HighlighterTargetArea
import com.intellij.openapi.editor.markup.TextAttributes
import com.intellij.openapi.fileEditor.FileEditorManager
import com.intellij.openapi.fileEditor.TextEditor
import com.intellij.openapi.project.Project
import com.intellij.openapi.vfs.VirtualFile
import java.awt.Color
import java.io.File

/**
 * Service projet qui stocke et applique la couverture de code ABL
 * à partir d'un fichier profiler .prof.
 *
 * Utilise des RangeHighlighters (vert/rouge) sur l'éditeur actif
 * au lieu de l'API CoverageEngine (trop couplée à la version IntelliJ SDK).
 */
@Service(Service.Level.PROJECT)
class AblCoverageService(private val project: Project) {
    /** chemin source → (numéro de ligne 1-based → count d'exécution) */
    private var executionCounts: Map<String, Map<Int, Int>> = emptyMap()

    /** Vue dérivée : chemin source → lignes couvertes (count > 0). Recalculée à chaque load. */
    private var coverageData: Map<String, Set<Int>> = emptyMap()

    private val coveredColor = Color(0x90, 0xEE, 0x90, 80) // vert transparent
    private val uncoveredColor = Color(0xFF, 0x99, 0x99, 80) // rouge transparent

    fun loadProfFile(profFile: File) {
        executionCounts = AblProfilerParser.parseWithCounts(profFile)
        coverageData = executionCounts.mapValues { (_, counts) -> counts.keys }
        // Appliquer sur tous les éditeurs ouverts
        FileEditorManager.getInstance(project).allEditors.forEach { editor ->
            val vFile = (editor as? TextEditor)?.file ?: return@forEach
            applyToEditor(editor.editor, vFile)
        }
    }

    fun applyToEditor(
        editor: Editor,
        file: VirtualFile,
    ) {
        if (coverageData.isEmpty()) return
        val path = file.path
        val covered = resolveCoverageForPath(path) ?: return

        val markup = editor.markupModel
        val doc = editor.document
        val lineCount = doc.lineCount

        for (lineIdx in 0 until lineCount) {
            val lineNum = lineIdx + 1 // 1-based
            val start = doc.getLineStartOffset(lineIdx)
            val end = doc.getLineEndOffset(lineIdx)
            if (start >= end) continue
            val color = if (lineNum in covered) coveredColor else uncoveredColor
            val attrs = TextAttributes().apply { backgroundColor = color }
            markup.addRangeHighlighter(
                start,
                end,
                HighlighterLayer.ADDITIONAL_SYNTAX,
                attrs,
                HighlighterTargetArea.LINES_IN_RANGE,
            )
        }
    }

    fun clearCoverage() {
        executionCounts = emptyMap()
        coverageData = emptyMap()
    }

    fun hasCoverage(): Boolean = coverageData.isNotEmpty()

    /**
     * Count d'exécution (1-based) pour la ligne [lineNum] du fichier [filePath].
     * Retourne 0 si la ligne n'a pas été exécutée, null si aucune donnée.
     */
    fun getExecutionCount(
        filePath: String,
        lineNum: Int,
    ): Int? {
        if (executionCounts.isEmpty()) return null
        val counts = resolveCountsForPath(filePath) ?: return null
        return counts[lineNum] ?: 0
    }

    /**
     * Retourne true/false si la ligne [lineNum] (1-based) est couverte,
     * ou null si aucune donnée n'est disponible pour ce fichier.
     */
    fun isLineCovered(
        filePath: String,
        lineNum: Int,
    ): Boolean? {
        if (coverageData.isEmpty()) return null
        val covered = resolveCoverageForPath(filePath) ?: return null
        return lineNum in covered
    }

    /**
     * Top-N lignes les plus exécutées pour un fichier, triées par count décroissant.
     * Utile pour les hot spots : `topHotLines(path, 20)` → 20 lignes les plus chaudes.
     */
    fun topHotLines(
        filePath: String,
        n: Int,
    ): List<Pair<Int, Int>> {
        val counts = resolveCountsForPath(filePath) ?: return emptyList()
        return counts.entries
            .sortedByDescending { it.value }
            .take(n)
            .map { it.key to it.value }
    }

    // ─── Résolution par chemin partiel ────────────────────────────────────────

    private fun resolveCoverageForPath(path: String): Set<Int>? =
        coverageData[path]
            ?: coverageData.entries.firstOrNull { (k, _) ->
                path.endsWith(k.replace('\\', '/'))
            }?.value

    private fun resolveCountsForPath(path: String): Map<Int, Int>? =
        executionCounts[path]
            ?: executionCounts.entries.firstOrNull { (k, _) ->
                path.endsWith(k.replace('\\', '/'))
            }?.value
}
