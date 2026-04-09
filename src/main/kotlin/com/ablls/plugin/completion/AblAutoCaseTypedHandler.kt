package com.ablls.plugin.completion

import com.ablls.plugin.core.AblKeywordList
import com.ablls.plugin.language.AblLanguage
import com.intellij.codeInsight.editorActions.TypedHandlerDelegate
import com.intellij.openapi.command.WriteCommandAction
import com.intellij.openapi.editor.Editor
import com.intellij.openapi.project.Project
import com.intellij.psi.PsiFile

class AblAutoCaseTypedHandler : TypedHandlerDelegate() {

    override fun charTyped(c: Char, project: Project, editor: Editor, file: PsiFile): Result {
        if (file.language != AblLanguage) return Result.CONTINUE

        // On ne déclenche l'auto-casing que si l'utilisateur a tapé un espace ou une tabulation
        if (c != ' ' && c != '\n' && c != '\t') {
            return Result.CONTINUE
        }

        val document = editor.document
        val offset = editor.caretModel.offset

        // Si on est tout au début du document, on ne fait rien
        if (offset < 2) return Result.CONTINUE

        // L'offset est situé APRES le caractère qu'on vient de taper (espace/tab).
        // Donc on va lire à l'envers depuis offset - 2
        var startOffset = offset - 2
        while (startOffset >= 0) {
            val ch = document.charsSequence[startOffset]
            // ABL autorise les lettres, chiffres et tirets dans les mots clés
            if (!ch.isLetterOrDigit() && ch != '-' && ch != '_') {
                startOffset++
                break
            }
            startOffset--
        }

        if (startOffset < 0) startOffset = 0

        val endOffset = offset - 1
        if (startOffset >= endOffset) return Result.CONTINUE

        val wordTyped = document.getText(com.intellij.openapi.util.TextRange(startOffset, endOffset))
        
        // Si le mot est en minuscules/camelCase et correspond à un mot clé ABL
        val upperWord = wordTyped.uppercase()
        if (wordTyped != upperWord && AblKeywordList.KEYWORDS.contains(upperWord)) {
            // Remplacer par la version majuscule
            WriteCommandAction.runWriteCommandAction(project) {
                document.replaceString(startOffset, endOffset, upperWord)
            }
        }

        return Result.CONTINUE
    }
}
