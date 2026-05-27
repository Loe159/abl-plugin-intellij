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
 * Intention Action : "Add NO-UNDO to all DEFINE VARIABLE in file"
 *
 * Ajoute NO-UNDO à toutes les déclarations de variables qui n'en disposent pas.
 * Disponible dans l'ampoule jaune (Alt+Entrée) et via le menu Code > Intention Actions.
 *
 * Utilise le flux de tokens pour détecter les patterns DEFINE VARIABLE sans NO-UNDO
 * et insérer le mot-clé avant le `.` de fin de statement.
 */
class AblAddNoUndoToAllIntention : IntentionAction {
    override fun getText() = "Add NO-UNDO to all DEFINE VARIABLE in file"

    override fun getFamilyName() = "ABL NO-UNDO"

    override fun startInWriteAction() = true

    override fun isAvailable(
        project: Project,
        editor: Editor?,
        file: PsiFile?,
    ): Boolean {
        if (file?.language != AblLanguage) return false
        val uri = file.virtualFile?.url ?: return false
        val service = project.service<AblProjectAnalysisService>()
        val tokens = service.analyzeFile(file.text, uri).tokens ?: return false
        return hasVariablesWithoutNoUndo(tokens)
    }

    override fun invoke(
        project: Project,
        editor: Editor?,
        file: PsiFile?,
    ) {
        file ?: return
        editor ?: return
        if (file.language != AblLanguage) return
        val uri = file.virtualFile?.url ?: return
        val service = project.service<AblProjectAnalysisService>()
        val tokens = service.analyzeFile(file.text, uri).tokens ?: return
        val doc = editor.document

        // Collecter toutes les positions où insérer NO-UNDO (en ordre inverse pour ne pas décaler)
        val insertPositions = findInsertPositions(tokens, doc)

        // Appliquer les insertions en ordre décroissant pour ne pas invalider les offsets
        for (pos in insertPositions.sortedDescending()) {
            doc.insertString(pos, " NO-UNDO")
        }
    }

    private fun hasVariablesWithoutNoUndo(tokens: org.antlr.v4.runtime.CommonTokenStream): Boolean {
        val size = tokens.size()
        var i = 0
        while (i < size) {
            val t = tokens.get(i)
            if (t.channel != Token.DEFAULT_CHANNEL) {
                i++
                continue
            }
            if (!t.text.equals("DEFINE", ignoreCase = true) &&
                !t.text.equals("DEF", ignoreCase = true)
            ) {
                i++
                continue
            }

            val (varEndIdx, hasNoUndo) = scanVariableStatement(tokens, i, size)
            if (varEndIdx > i && !hasNoUndo) return true
            i = if (varEndIdx > i) varEndIdx else i + 1
        }
        return false
    }

    private fun findInsertPositions(
        tokens: org.antlr.v4.runtime.CommonTokenStream,
        doc: com.intellij.openapi.editor.Document,
    ): List<Int> {
        val positions = mutableListOf<Int>()
        val size = tokens.size()
        var i = 0
        while (i < size) {
            val t = tokens.get(i)
            if (t.channel != Token.DEFAULT_CHANNEL) {
                i++
                continue
            }
            if (!t.text.equals("DEFINE", ignoreCase = true) &&
                !t.text.equals("DEF", ignoreCase = true)
            ) {
                i++
                continue
            }

            val (dotIdx, hasNoUndo) = scanVariableStatement(tokens, i, size)
            if (dotIdx > i && !hasNoUndo) {
                // Insérer avant le "." final
                val dotToken = tokens.get(dotIdx)
                val line = (dotToken.line - 1).coerceAtLeast(0)
                if (line < doc.lineCount) {
                    val offset = doc.getLineStartOffset(line) + dotToken.charPositionInLine
                    positions.add(offset)
                }
            }
            i = if (dotIdx > i) dotIdx + 1 else i + 1
        }
        return positions
    }

    /**
     * Depuis l'index [defIdx] (token DEFINE), avance jusqu'à la fin du statement VARIABLE.
     * Retourne (dotTokenIndex, hasNoUndo).
     * Retourne (-1, false) si le statement n'est pas DEFINE VARIABLE.
     */
    private fun scanVariableStatement(
        tokens: org.antlr.v4.runtime.CommonTokenStream,
        defIdx: Int,
        size: Int,
    ): Pair<Int, Boolean> {
        // Vérifier que le mot-clé suivant est VARIABLE (ou VAR)
        var j = defIdx + 1
        while (j < size && tokens.get(j).channel != Token.DEFAULT_CHANNEL) j++
        if (j >= size) return Pair(-1, false)
        val keyword = tokens.get(j).text?.uppercase() ?: return Pair(-1, false)
        if (keyword != "VARIABLE" && keyword != "VAR") return Pair(-1, false)

        // Scanner jusqu'au "." terminal du statement (depth 0)
        var hasNoUndo = false
        var depth = 0
        j++
        while (j < size) {
            val t = tokens.get(j)
            if (t.channel == Token.DEFAULT_CHANNEL) {
                val txt = t.text?.uppercase() ?: ""
                when {
                    txt == "(" -> depth++
                    txt == ")" -> depth--
                    txt == "NO-UNDO" && depth == 0 -> hasNoUndo = true
                    txt == "." && depth == 0 -> return Pair(j, hasNoUndo)
                    // Fin prématurée sur un autre statement-level keyword
                    depth == 0 && txt in TOP_LEVEL_KEYWORDS && j > defIdx + 3 ->
                        return Pair(-1, false)
                }
            }
            j++
        }
        return Pair(-1, false)
    }

    companion object {
        private val TOP_LEVEL_KEYWORDS =
            setOf(
                "PROCEDURE", "FUNCTION", "CLASS", "METHOD", "IF", "FOR", "DO", "END",
                "DEFINE", "MESSAGE", "RUN", "RETURN", "ASSIGN", "FIND",
            )
    }
}
