package com.ablls.plugin.intentions

import com.ablls.plugin.core.AblProjectAnalysisService
import com.ablls.plugin.language.AblLanguage
import com.intellij.codeInsight.intention.IntentionAction
import com.intellij.openapi.components.service
import com.intellij.openapi.editor.Editor
import com.intellij.openapi.project.Project
import com.intellij.openapi.ui.Messages
import com.intellij.psi.PsiFile

/**
 * Intention Action : "Change Signature — Add/Remove Parameter"
 *
 * Quand le curseur est sur le nom d'une PROCEDURE ou FUNCTION,
 * affiche un dialogue pour ajouter ou supprimer un paramètre.
 *
 * Version simplifiée : propose d'ajouter un INPUT PARAMETER à la signature
 * de la procédure courante.
 */
class AblChangeSignatureIntention : IntentionAction {

    override fun getText()            = "Add INPUT PARAMETER to procedure/function"
    override fun getFamilyName()      = "ABL Change Signature"
    override fun startInWriteAction() = true

    override fun isAvailable(project: Project, editor: Editor?, file: PsiFile?): Boolean {
        if (file?.language != AblLanguage) return false
        editor ?: return false

        val offset = editor.caretModel.offset
        val text   = file.text
        // Chercher PROCEDURE ou FUNCTION à gauche du curseur sur la même ligne
        val lineStart = text.lastIndexOf('\n', offset).coerceAtLeast(0)
        val line = text.substring(lineStart, offset)
        return line.contains(Regex("(?i)\\b(PROCEDURE|FUNCTION)\\s+\\w")) ||
               text.substring(maxOf(0, offset - 3), minOf(text.length, offset + 30))
                   .contains(Regex("(?i)PROCEDURE|FUNCTION"))
    }

    override fun invoke(project: Project, editor: Editor?, file: PsiFile?) {
        editor ?: return
        file ?: return
        if (file.language != AblLanguage) return

        val offset = editor.caretModel.offset
        val doc = editor.document
        val text = file.text

        // Trouver la ligne de définition de la procédure
        val lineNum = doc.getLineNumber(offset)
        val lineStart = doc.getLineStartOffset(lineNum)
        val lineEnd   = if (lineNum + 1 < doc.lineCount) doc.getLineStartOffset(lineNum + 1) else text.length
        val line = text.substring(lineStart, lineEnd).trimEnd()

        val paramDef = Messages.showInputDialog(
            project,
            "Enter parameter declaration (e.g. INPUT p_Name AS CHARACTER):",
            "Add Parameter",
            null,
            "INPUT p_NewParam AS CHARACTER",
            null
        )?.trim() ?: return
        if (paramDef.isBlank()) return

        // Trouver la position d'insertion dans la signature
        // Pour PROCEDURE foo: → insérer DEFINE PARAMETER après la ligne de def
        // Pour FUNCTION foo RETURNS INTEGER(...): → insérer dans la parenthèse
        val colonPos = line.indexOf(':')
        if (colonPos < 0) return

        // Insérer la définition du paramètre après la ligne de définition
        val insertPos = lineEnd
        doc.insertString(insertPos, "    DEFINE $paramDef NO-UNDO.\n")
    }
}
