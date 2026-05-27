package com.ablls.plugin.intentions

import com.ablls.plugin.core.AblProjectAnalysisService
import com.ablls.plugin.language.AblLanguage
import com.intellij.codeInsight.intention.IntentionAction
import com.intellij.openapi.components.service
import com.intellij.openapi.editor.Editor
import com.intellij.openapi.project.Project
import com.intellij.psi.PsiFile
import org.antlr.v4.runtime.Token

/**
 * Intention Action : "Inline Variable"
 *
 * Quand le curseur est sur le nom d'une variable locale simple
 * (une seule affectation, une seule utilisation), remplace la variable
 * par son expression d'initialisation.
 *
 * Exemples :
 *   DEFINE VARIABLE lv_name AS CHARACTER NO-UNDO.
 *   ASSIGN lv_name = Customer.Name.
 *   MESSAGE lv_name.         → MESSAGE Customer.Name.
 */
class AblInlineVariableIntention : IntentionAction {
    override fun getText() = "Inline variable"

    override fun getFamilyName() = "ABL Refactor"

    override fun startInWriteAction() = true

    override fun isAvailable(
        project: Project,
        editor: Editor?,
        file: PsiFile?,
    ): Boolean {
        if (file?.language != AblLanguage) return false
        editor ?: return false
        val element = file.findElementAt(editor.caretModel.offset) ?: return false
        val name = element.text.takeIf { it.isNotBlank() } ?: return false

        val service = project.service<AblProjectAnalysisService>()
        val uri = file.virtualFile?.url ?: return false
        val tokens = service.analyzeFile(file.text, uri).tokens ?: return false

        val occurrences = countOccurrences(tokens, name)
        return occurrences in 2..3
    }

    @Suppress("ReturnCount")
    override fun invoke(
        project: Project,
        editor: Editor?,
        file: PsiFile?,
    ) {
        editor ?: return
        file ?: return
        if (file.language != AblLanguage) return

        val offset = editor.caretModel.offset
        val element = file.findElementAt(offset) ?: return
        val varName = element.text.trim().takeIf { it.isNotBlank() } ?: return

        val service = project.service<AblProjectAnalysisService>()
        val uri = file.virtualFile?.url ?: return
        val tokens = service.analyzeFile(file.text, uri).tokens ?: return
        val doc = editor.document

        // Trouver l'expression d'assignation (ASSIGN varName = expr.)
        val assignExpr = findAssignExpression(tokens, varName, doc) ?: return
        if (assignExpr.isBlank()) return

        // Trouver le site d'utilisation et remplacer
        val text = doc.text
        val defRegex = Regex("(?i)DEFINE\\s+VARIABLE\\s+$varName\\s+AS[^.]+\\.")
        val assignRegex = Regex("(?i)ASSIGN\\s+$varName\\s*=[^.]+\\.")

        // Remplacer l'utilisation par l'expression (en ordre inverse pour ne pas décaler)
        val usageRange = findUsageRange(text, varName, defRegex, assignRegex) ?: return
        doc.replaceString(usageRange.first, usageRange.second, assignExpr)

        // Supprimer la ligne d'assignation
        val assignLine = findLineOf(text, assignRegex)
        if (assignLine >= 0) {
            val lineStart = doc.getLineStartOffset(assignLine)
            val lineEnd = if (assignLine + 1 < doc.lineCount) doc.getLineStartOffset(assignLine + 1) else doc.textLength
            doc.deleteString(lineStart, lineEnd)
        }

        // Supprimer la ligne de définition
        val defLine = findLineOf(text, defRegex)
        if (defLine >= 0) {
            val ls = doc.getLineStartOffset(defLine)
            val le = if (defLine + 1 < doc.lineCount) doc.getLineStartOffset(defLine + 1) else doc.textLength
            doc.deleteString(ls, le)
        }
    }

    private fun countOccurrences(
        tokens: org.antlr.v4.runtime.CommonTokenStream,
        name: String,
    ): Int {
        var count = 0
        val size = tokens.size()
        for (i in 0 until size) {
            val t = tokens.get(i)
            if (t.channel != Token.DEFAULT_CHANNEL) continue
            if (t.text.equals(name, ignoreCase = true)) count++
        }
        return count
    }

    private fun findAssignExpression(
        tokens: org.antlr.v4.runtime.CommonTokenStream,
        varName: String,
        doc: com.intellij.openapi.editor.Document,
    ): String? {
        val text = doc.text
        val regex = Regex("(?i)ASSIGN\\s+$varName\\s*=\\s*([^.]+)\\.")
        val match = regex.find(text) ?: return null
        return match.groupValues[1].trim()
    }

    private fun findUsageRange(
        text: String,
        varName: String,
        defRegex: Regex,
        assignRegex: Regex,
    ): Pair<Int, Int>? {
        // Trouver la première occurrence qui n'est ni la définition ni l'assignation
        var searchStart = 0
        while (searchStart < text.length) {
            val idx = text.indexOf(varName, searchStart, ignoreCase = true)
            if (idx < 0) break

            // Vérifier que ce n'est pas dans la définition ou l'assignation
            val lineStart = text.lastIndexOf('\n', idx).coerceAtLeast(0)
            val lineEnd = text.indexOf('\n', idx).let { if (it < 0) text.length else it }
            val line = text.substring(lineStart, lineEnd)

            val isDef = line.contains(Regex("(?i)DEFINE\\s+VARIABLE"))
            val isAssign = line.contains(Regex("(?i)ASSIGN\\s+$varName\\s*="))

            if (!isDef && !isAssign) {
                return Pair(idx, idx + varName.length)
            }
            searchStart = idx + varName.length
        }
        return null
    }

    private fun findLineOf(
        text: String,
        regex: Regex,
    ): Int {
        val match = regex.find(text) ?: return -1
        return text.substring(0, match.range.first).count { it == '\n' }
    }
}
