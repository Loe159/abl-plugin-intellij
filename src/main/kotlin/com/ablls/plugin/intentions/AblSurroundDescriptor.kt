package com.ablls.plugin.intentions

import com.ablls.plugin.language.AblLanguage
import com.intellij.lang.surroundWith.SurroundDescriptor
import com.intellij.lang.surroundWith.Surrounder
import com.intellij.openapi.editor.Editor
import com.intellij.openapi.project.Project
import com.intellij.openapi.util.TextRange
import com.intellij.psi.PsiElement
import com.intellij.psi.PsiFile

/**
 * Surrounders ABL disponibles via Ctrl+Alt+T (Code > Surround With).
 *
 * Propose les blocs structurels les plus courants en ABL :
 *  - DO: ... END.
 *  - DO TRANSACTION: ... END.
 *  - DO ON ERROR UNDO, THROW: ... END.
 *  - IF TRUE THEN DO: ... END.
 */
class AblSurroundDescriptor : SurroundDescriptor {
    override fun getElementsToSurround(
        file: PsiFile,
        startOffset: Int,
        endOffset: Int,
    ): Array<PsiElement> {
        if (file.language != AblLanguage) return PsiElement.EMPTY_ARRAY
        if (startOffset >= endOffset) return PsiElement.EMPTY_ARRAY
        // Pour un PSI plat, on retourne simplement l'élément à la position de début de sélection
        val element = file.findElementAt(startOffset) ?: return PsiElement.EMPTY_ARRAY
        return arrayOf(element)
    }

    override fun getSurrounders(): Array<Surrounder> =
        arrayOf(
            AblDoEndSurrounder("DO:", "END."),
            AblDoEndSurrounder("DO TRANSACTION:", "END."),
            AblDoEndSurrounder("DO ON ERROR UNDO, THROW:", "END."),
            AblDoEndSurrounder("DO ON STOP UNDO, RETURN:", "END."),
            AblDoEndSurrounder("IF TRUE THEN DO:", "END."),
        )

    override fun isExclusive() = false
}

// ─── Surrounder générique pour tous les blocs DO/END ─────────────────────────

private class AblDoEndSurrounder(
    private val openKeyword: String,
    private val closeKeyword: String,
) : Surrounder {
    override fun getTemplateDescription(): String = "$openKeyword ... $closeKeyword"

    override fun isApplicable(elements: Array<out PsiElement>): Boolean = elements.isNotEmpty()

    override fun surroundElements(
        project: Project,
        editor: Editor,
        elements: Array<out PsiElement>,
    ): TextRange? {
        val selectionModel = editor.selectionModel
        if (!selectionModel.hasSelection()) return null

        val doc = editor.document
        val selStart = selectionModel.selectionStart
        val selEnd = selectionModel.selectionEnd

        // Indentation de la ligne de début (pour aligner END.)
        val lineStart = doc.getLineStartOffset(doc.getLineNumber(selStart))
        val lineText = doc.text.substring(lineStart, selStart)
        val indent = lineText.takeWhile { it == ' ' || it == '\t' }

        // Construire le nouveau texte
        val selectedText = doc.text.substring(selStart, selEnd)
        // Indenter le contenu d'un niveau
        val indentedContent =
            selectedText
                .lines()
                .joinToString("\n") { line -> if (line.isBlank()) line else "  $line" }
        val newText = "$openKeyword\n$indentedContent\n${indent}$closeKeyword"

        // Remplacer la sélection
        doc.replaceString(selStart, selEnd, newText)
        selectionModel.removeSelection()

        // Positionner le curseur après le bloc inséré
        val newEndOffset = selStart + newText.length
        return TextRange(selStart, newEndOffset)
    }
}
