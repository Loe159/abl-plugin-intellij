package com.ablls.plugin.intentions

import com.ablls.plugin.language.AblLanguage
import com.intellij.codeInsight.intention.IntentionAction
import com.intellij.openapi.editor.Editor
import com.intellij.openapi.project.Project
import com.intellij.psi.PsiFile

/**
 * Intention Action : "Introduce Variable"
 *
 * Quand l'utilisateur sélectionne une expression dans l'éditeur ABL,
 * cette action :
 *   1. Crée un DEFINE VARIABLE lv_xxx AS CHARACTER NO-UNDO. au début du bloc courant
 *   2. Remplace la sélection par le nom de la variable
 *   3. Ajoute un ASSIGN lv_xxx = <expression> avant l'utilisation
 *
 * Pour simplifier, insère juste avant la ligne courante.
 */
class AblIntroduceVariableIntention : IntentionAction {
    override fun getText() = "Introduce variable for selection"

    override fun getFamilyName() = "ABL Refactor"

    override fun startInWriteAction() = true

    override fun isAvailable(
        project: Project,
        editor: Editor?,
        file: PsiFile?,
    ): Boolean {
        if (file?.language != AblLanguage) return false
        val sel = editor?.selectionModel ?: return false
        if (!sel.hasSelection()) return false
        val selectedText = sel.selectedText ?: return false
        // Doit être une expression simple (pas multi-ligne)
        return selectedText.isNotBlank() && !selectedText.contains('\n')
    }

    override fun invoke(
        project: Project,
        editor: Editor?,
        file: PsiFile?,
    ) {
        editor ?: return
        file ?: return
        if (file.language != AblLanguage) return

        val sel = editor.selectionModel
        if (!sel.hasSelection()) return

        val expression = sel.selectedText?.trim() ?: return
        val doc = editor.document
        val selStart = sel.selectionStart

        val varName = "lv_result"

        // Trouver le début de la ligne courante pour insérer la déclaration
        val currentLine = doc.getLineNumber(selStart)
        val lineStart = doc.getLineStartOffset(currentLine)

        // Détecter l'indentation
        val lineText = doc.text.substring(lineStart, selStart)
        val indent = lineText.takeWhile { it == ' ' || it == '\t' }

        // Insérer la déclaration et l'assignation avant la ligne courante
        val declaration =
            "${indent}DEFINE VARIABLE $varName AS CHARACTER NO-UNDO.\n" +
                "${indent}ASSIGN $varName = $expression.\n"
        doc.insertString(lineStart, declaration)

        // Remplacer l'expression sélectionnée par le nom de variable
        // (les offsets ont été décalés par l'insertion)
        val newSelStart = selStart + declaration.length
        val newSelEnd = newSelStart + expression.length
        doc.replaceString(
            newSelStart,
            newSelEnd + (sel.selectionEnd - sel.selectionStart - expression.length),
            varName,
        )

        sel.removeSelection()
        // Positionner sur le nom de la variable dans la déclaration pour renommage
        editor.caretModel.moveToOffset(lineStart + indent.length + "DEFINE VARIABLE ".length)
    }
}
