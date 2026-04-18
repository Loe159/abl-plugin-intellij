package com.ablls.plugin.completion

import com.ablls.plugin.language.AblLanguage
import com.intellij.codeInsight.editorActions.TypedHandlerDelegate
import com.intellij.openapi.command.WriteCommandAction
import com.intellij.openapi.editor.Editor
import com.intellij.openapi.project.Project
import com.intellij.psi.PsiFile
import com.intellij.application.options.CodeStyle

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

        // Match "END" as a word: trimmed must start with END and have no identifier char after it
        val trimmedUpper = trimmed.uppercase()
        if (!trimmedUpper.startsWith("END")) return Result.CONTINUE
        if (trimmed.length > 3) {
            val afterEnd = trimmed[3]
            if (afterEnd.isLetterOrDigit() || afterEnd == '-' || afterEnd == '_') return Result.CONTINUE
        }

        // Also guard against the next character in the document forming an identifier (e.g. END-POINT)
        if (offset < document.textLength) {
            val nextChar = document.charsSequence[offset]
            if (nextChar.isLetterOrDigit() || nextChar == '-' || nextChar == '_') return Result.CONTINUE
        }

        val leadingWhitespace = lineText.length - trimmed.length
        if (leadingWhitespace == 0) return Result.CONTINUE

        val indentOptions = CodeStyle.getSettings(file).getIndentOptions(file.fileType)
        val indentUnit = if (indentOptions.USE_TAB_CHARACTER) "\t"
                         else " ".repeat(indentOptions.INDENT_SIZE)
        if (!lineText.startsWith(indentUnit)) return Result.CONTINUE

        val newIndent = lineText.substring(0, maxOf(0, leadingWhitespace - indentUnit.length))

        WriteCommandAction.runWriteCommandAction(project) {
            document.replaceString(lineStart, lineStart + leadingWhitespace, newIndent)
            editor.caretModel.moveToOffset(lineStart + newIndent.length + trimmed.length)
        }

        return Result.CONTINUE
    }
}
