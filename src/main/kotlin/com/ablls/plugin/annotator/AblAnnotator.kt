package com.ablls.plugin.annotator

import com.ablls.plugin.core.AblParseResult
import com.ablls.plugin.core.AblProjectAnalysisService
import com.ablls.plugin.core.SyntaxError
import com.ablls.plugin.language.AblLanguage
import com.intellij.lang.annotation.AnnotationHolder
import com.intellij.lang.annotation.ExternalAnnotator
import com.intellij.lang.annotation.HighlightSeverity
import com.intellij.openapi.components.service
import com.intellij.openapi.editor.Editor
import com.intellij.openapi.util.TextRange
import com.intellij.psi.PsiDocumentManager
import com.intellij.psi.PsiFile

/**
 * Annotateur externe ABL — signale les erreurs syntaxiques CABL dans l'éditeur.
 *
 * Flux IntelliJ :
 *   1. [collectInformation] — sur l'EDT, collecte le contenu + URI
 *   2. [doAnnotate]         — thread de fond, parse avec CABL, retourne les erreurs
 *   3. [apply]              — sur l'EDT, crée les annotations (squiggles rouges)
 */
class AblAnnotator : ExternalAnnotator<AblAnnotator.Input, List<SyntaxError>>() {

    data class Input(val content: String, val uri: String, val project: com.intellij.openapi.project.Project)

    override fun collectInformation(file: PsiFile, editor: Editor, hasErrors: Boolean): Input? {
        if (file.language != AblLanguage) return null
        val uri = file.virtualFile?.url ?: return null
        return Input(file.text, uri, file.project)
    }

    override fun doAnnotate(input: Input?): List<SyntaxError>? {
        if (input == null) return null
        val service = input.project.service<AblProjectAnalysisService>()
        val result = service.analyzeFile(input.content, input.uri)
        return result.syntaxErrors
    }

    override fun apply(file: PsiFile, errors: List<SyntaxError>?, holder: AnnotationHolder) {
        if (errors.isNullOrEmpty()) return

        val document = PsiDocumentManager.getInstance(file.project)
            .getDocument(file) ?: return
        val docLength = document.textLength

        // Limiter à 20 erreurs max pour éviter les cascades d'erreurs CABL
        // (une seule inclusion manquante peut générer des dizaines d'erreurs dérivées)
        val errorsToShow = errors.take(20)
        val hasMore = errors.size > 20

        for (error in errorsToShow) {
            val line = error.line.coerceIn(0, document.lineCount - 1)
            val lineStart  = document.getLineStartOffset(line)
            val lineEnd    = document.getLineEndOffset(line)
            val colStart   = (lineStart + error.column).coerceAtMost(lineEnd)
            val colEnd     = (colStart + error.length.coerceAtLeast(1)).coerceAtMost(lineEnd)
            val range      = TextRange(colStart, colEnd.coerceAtMost(docLength))

            holder.newAnnotation(HighlightSeverity.ERROR, error.message)
                .range(range)
                .create()
        }

        // Annotation de synthèse si des erreurs ont été tronquées
        if (hasMore) {
            val firstLineEnd = document.getLineEndOffset(0)
            val range = TextRange(0, firstLineEnd.coerceAtMost(docLength).coerceAtLeast(0))
            holder.newAnnotation(
                HighlightSeverity.WARNING,
                "${errors.size} erreurs syntaxiques (${errors.size - 20} masquées) — vérifiez le PROPATH dans openedge-project.json"
            ).range(range).create()
        }
    }
}
