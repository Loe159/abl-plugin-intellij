package com.ablls.plugin.completion

import com.ablls.plugin.language.AblLanguage
import com.intellij.codeInsight.editorActions.TypedHandlerDelegate
import com.intellij.openapi.command.WriteCommandAction
import com.intellij.openapi.editor.Editor
import com.intellij.openapi.project.Project
import com.intellij.psi.PsiFile

class AblAutoEndTypedHandler : TypedHandlerDelegate() {

    override fun charTyped(c: Char, project: Project, editor: Editor, file: PsiFile): Result {
        if (file.language != AblLanguage) return Result.CONTINUE
        // Only trigger when the user has just typed the final 'd'/'D' of "END"
        if (c != 'd' && c != 'D') return Result.CONTINUE

        val document = editor.document
        val offset = editor.caretModel.offset  // position after the 'd' just inserted
        val lineNumber = document.getLineNumber(offset)
        val lineStart = document.getLineStartOffset(lineNumber)

        val lineText = document.charsSequence.subSequence(lineStart, offset).toString()
        val trimmed = lineText.trimStart()

        // Only act when the line is exactly "END" (case-insensitive), nothing else
        if (trimmed.uppercase() != "END") return Result.CONTINUE

        val leadingWhitespace = lineText.length - trimmed.length
        if (leadingWhitespace == 0) return Result.CONTINUE

        // Determine indent unit from context (tab or 4 spaces)
        val indentUnit = if (lineText[0] == '\t') "\t" else "    "
        if (!lineText.startsWith(indentUnit)) return Result.CONTINUE

        val newIndent = lineText.substring(0, leadingWhitespace - indentUnit.length)

        WriteCommandAction.runWriteCommandAction(project) {
            document.replaceString(lineStart, lineStart + leadingWhitespace, newIndent)
            editor.caretModel.moveToOffset(lineStart + newIndent.length + trimmed.length)
        }

        return Result.CONTINUE
    }
}
