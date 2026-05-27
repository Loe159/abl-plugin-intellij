package com.ablls.plugin.intentions

import com.ablls.plugin.language.AblLanguage
import com.intellij.codeInsight.intention.IntentionAction
import com.intellij.openapi.editor.Editor
import com.intellij.openapi.project.Project
import com.intellij.psi.PsiFile

/**
 * Intention Action : "Extract selection into PROCEDURE"
 *
 * Quand l'utilisateur a sélectionné plusieurs lignes de code ABL,
 * cette action :
 *   1. Crée une nouvelle PROCEDURE à la fin du fichier avec le code sélectionné
 *   2. Remplace la sélection par un appel RUN procName.
 *   3. Place le curseur sur le nom de la procédure pour le renommer.
 *
 * Disponible uniquement quand il y a une sélection de plus d'une ligne.
 */
class AblExtractProcedureIntention : IntentionAction {
    override fun getText() = "Extract selection into PROCEDURE"

    override fun getFamilyName() = "ABL Extract"

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
        return selectedText.lines().size >= 2
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

        val selectedText = sel.selectedText ?: return
        val doc = editor.document

        val selStart = sel.selectionStart
        val selEnd = sel.selectionEnd

        val procName = "extractedProcedure"

        // Détecter l'indentation de la sélection
        val selStartLine = doc.getLineNumber(selStart)
        val lineText = doc.text.substring(doc.getLineStartOffset(selStartLine), selStart)
        val indent = lineText.takeWhile { it == ' ' || it == '\t' }

        // Indenter le corps de la procédure
        val body =
            selectedText.trimEnd()
                .lines()
                .joinToString("\n") { "    $it" }

        // Construire la procédure
        val procDefinition = "\n\nPROCEDURE $procName:\n$body\nEND PROCEDURE.\n"

        // Appel à insérer
        val callText = "${indent}RUN $procName."

        // 1. Remplacer la sélection par l'appel
        doc.replaceString(selStart, selEnd, callText)

        // 2. Ajouter la procédure à la fin du fichier
        val endOfFile = doc.textLength
        doc.insertString(endOfFile, procDefinition)

        // 3. Positionner le curseur sur le nom de la procédure (pour renommer)
        val procNameOffset =
            endOfFile + "\n\nPROCEDURE ".length + callText.length - callText.length +
                doc.textLength - procDefinition.length + "\n\nPROCEDURE ".length
        editor.caretModel.moveToOffset(selStart + "RUN ".length)
        sel.removeSelection()
    }
}
