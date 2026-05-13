package com.ablls.plugin.coverage

import com.intellij.openapi.components.Service
import com.intellij.openapi.editor.Editor
import com.intellij.openapi.editor.markup.HighlighterLayer
import com.intellij.openapi.editor.markup.HighlighterTargetArea
import com.intellij.openapi.editor.markup.TextAttributes
import com.intellij.openapi.fileChooser.FileChooserDescriptorFactory
import com.intellij.openapi.fileEditor.FileEditorManager
import com.intellij.openapi.fileEditor.FileEditorManagerListener
import com.intellij.openapi.fileEditor.TextEditor
import com.intellij.openapi.project.Project
import com.intellij.openapi.ui.DialogWrapper
import com.intellij.openapi.ui.TextFieldWithBrowseButton
import com.intellij.openapi.vfs.VirtualFile
import java.awt.Color
import java.io.File
import javax.swing.JComponent
import javax.swing.JLabel
import javax.swing.JPanel

/**
 * Service projet qui stocke et applique la couverture de code ABL
 * à partir d'un fichier profiler .prof.
 *
 * Utilise des RangeHighlighters (vert/rouge) sur l'éditeur actif
 * au lieu de l'API CoverageEngine (trop couplée à la version IntelliJ SDK).
 */
@Service(Service.Level.PROJECT)
class AblCoverageService(private val project: Project) {

    /** chemin source → lignes couvertes (1-based) */
    private var coverageData: Map<String, Set<Int>> = emptyMap()

    private val COVERED_COLOR   = Color(0x90, 0xEE, 0x90, 80)   // vert transparent
    private val UNCOVERED_COLOR = Color(0xFF, 0x99, 0x99, 80)    // rouge transparent

    fun loadProfFile(profFile: File) {
        coverageData = AblProfilerParser.parse(profFile)
        // Appliquer sur tous les éditeurs ouverts
        FileEditorManager.getInstance(project).allEditors.forEach { editor ->
            val vFile = (editor as? TextEditor)?.file ?: return@forEach
            applyToEditor(editor.editor, vFile)
        }
    }

    fun applyToEditor(editor: Editor, file: VirtualFile) {
        if (coverageData.isEmpty()) return
        val path = file.path
        // Chercher par chemin complet ou nom de fichier
        val covered = coverageData[path]
            ?: coverageData.entries.firstOrNull { (k, _) ->
                path.endsWith(k.replace('\\', '/'))
            }?.value
            ?: return

        val markup   = editor.markupModel
        val doc      = editor.document
        val lineCount = doc.lineCount

        for (lineIdx in 0 until lineCount) {
            val lineNum  = lineIdx + 1   // 1-based
            val start    = doc.getLineStartOffset(lineIdx)
            val end      = doc.getLineEndOffset(lineIdx)
            if (start >= end) continue

            val color = if (lineNum in covered) COVERED_COLOR else UNCOVERED_COLOR
            val attrs = TextAttributes().apply { backgroundColor = color }
            markup.addRangeHighlighter(
                start, end,
                HighlighterLayer.ADDITIONAL_SYNTAX,
                attrs,
                HighlighterTargetArea.LINES_IN_RANGE
            )
        }
    }

    fun clearCoverage() {
        coverageData = emptyMap()
    }

    fun hasCoverage(): Boolean = coverageData.isNotEmpty()

    /**
     * Retourne true/false si la ligne [lineNum] (1-based) est couverte,
     * ou null si aucune donnée n'est disponible pour ce fichier.
     */
    fun isLineCovered(filePath: String, lineNum: Int): Boolean? {
        if (coverageData.isEmpty()) return null
        val covered = coverageData[filePath]
            ?: coverageData.entries.firstOrNull { (k, _) ->
                filePath.endsWith(k.replace('\\', '/'))
            }?.value
            ?: return null
        return lineNum in covered
    }
}
