package com.ablls.plugin.annotator

import com.ablls.plugin.inspections.AblInspectionHelper
import com.ablls.plugin.language.AblLanguage
import com.ablls.plugin.project.OpenEdgeProjectService
import com.intellij.lang.annotation.AnnotationHolder
import com.intellij.lang.annotation.ExternalAnnotator
import com.intellij.lang.annotation.HighlightSeverity
import com.intellij.openapi.components.service
import com.intellij.openapi.editor.Editor
import com.intellij.psi.PsiDocumentManager
import com.intellij.psi.PsiFile
import java.io.File
import java.nio.file.Paths

/**
 * Annotateur externe : lit les fichiers .warnings générés par le compilateur OpenEdge
 * et affiche les avertissements directement dans l'éditeur.
 *
 * Le compilateur Progress produit des fichiers texte dans le répertoire warningsDir
 * (par défaut .build/.warnings/) avec le même nom de base que le fichier source.
 *
 * Format des avertissements :
 *   ** Customer.p: Warning: (8349) ... (line 42, col 5)
 */
class AblCompilerWarningAnnotator : ExternalAnnotator<AblCompilerWarningAnnotator.Input, List<AblCompilerWarningAnnotator.CompilerWarning>>() {

    data class Input(val baseName: String, val warningsDir: String)
    data class CompilerWarning(val message: String, val line: Int, val col: Int)

    override fun collectInformation(file: PsiFile, editor: Editor, hasErrors: Boolean): Input? {
        if (file.language != AblLanguage) return null
        val config      = file.project.service<OpenEdgeProjectService>().config
        val basePath    = file.project.basePath ?: return null
        val warningsDir = Paths.get(basePath).resolve(config.warningsDir).toString()
        val baseName    = file.virtualFile?.nameWithoutExtension ?: return null
        return Input(baseName, warningsDir)
    }

    override fun doAnnotate(input: Input?): List<CompilerWarning> {
        if (input == null) return emptyList()
        val warnFile = File(input.warningsDir, "${input.baseName}.warnings")
        if (!warnFile.exists()) return emptyList()

        val pattern = Regex("""\*\*\s+\S+\s+Warning:\s*\(([^)]+)\).*\(line\s+(\d+)[\s,]+col\s+(\d+)\)""", RegexOption.IGNORE_CASE)
        return warnFile.readLines().mapNotNull { line ->
            val m = pattern.find(line) ?: return@mapNotNull null
            val msgCode  = m.groupValues[1]
            val lineNum  = m.groupValues[2].toIntOrNull() ?: return@mapNotNull null
            val colNum   = m.groupValues[3].toIntOrNull() ?: 0
            CompilerWarning("Compiler warning ($msgCode)", lineNum, colNum)
        }
    }

    override fun apply(file: PsiFile, warnings: List<CompilerWarning>?, holder: AnnotationHolder) {
        if (warnings.isNullOrEmpty()) return
        val doc = PsiDocumentManager.getInstance(file.project).getDocument(file) ?: return
        for (w in warnings) {
            if (w.line <= 0) continue
            val range = AblInspectionHelper.toRange(doc, w.line, w.col, 1)
            holder.newAnnotation(HighlightSeverity.WARNING, w.message)
                .range(range)
                .tooltip("OpenEdge compiler: ${w.message}")
                .create()
        }
    }
}
