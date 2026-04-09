package com.ablls.plugin.inspections

import com.intellij.openapi.editor.Document
import com.intellij.openapi.util.TextRange

/**
 * Utilitaires partagés par toutes les inspections ABL basées sur proparse.
 */
object AblInspectionHelper {

    /**
     * Convertit une position proparse (1-based line, 0-based col) en [TextRange] IntelliJ (0-based).
     * @param len  longueur du token à surligner (minimum 1)
     */
    fun toRange(doc: Document, line: Int, col: Int, len: Int): TextRange {
        val l         = (line - 1).coerceIn(0, doc.lineCount - 1)
        val lineStart = doc.getLineStartOffset(l)
        val lineEnd   = doc.getLineEndOffset(l)
        val start     = (lineStart + col).coerceIn(lineStart, lineEnd)
        val end       = (start + len.coerceAtLeast(1)).coerceAtMost(doc.textLength)
        return TextRange(start, end)
    }
}
