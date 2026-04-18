package com.ablls.plugin.highlight

import com.ablls.plugin.language.AblLanguage
import com.intellij.codeInsight.editorActions.enter.EnterHandlerDelegate
import com.intellij.codeInsight.editorActions.enter.EnterHandlerDelegate.Result
import com.intellij.openapi.actionSystem.DataContext
import com.intellij.openapi.editor.Editor
import com.intellij.openapi.editor.actionSystem.EditorActionHandler
import com.intellij.openapi.util.Ref
import com.intellij.psi.PsiFile
import com.intellij.application.options.CodeStyle

class AblIndentProcessor : EnterHandlerDelegate {

    override fun preprocessEnter(
        file: PsiFile,
        editor: Editor,
        caretOffset: Ref<Int>,
        caretAdvance: Ref<Int>,
        dataContext: DataContext,
        originalHandler: EditorActionHandler?
    ): Result = Result.Continue

    override fun postProcessEnter(
        file: PsiFile,
        editor: Editor,
        dataContext: DataContext
    ): Result {
        if (file.language != AblLanguage) return Result.Continue

        val document = editor.document
        val offset = editor.caretModel.offset
        val lineNumber = document.getLineNumber(offset)
        if (lineNumber == 0) return Result.Continue

        val prevLineStart = document.getLineStartOffset(lineNumber - 1)
        val prevLineEnd = document.getLineEndOffset(lineNumber - 1)
        val prevLine = document.charsSequence.subSequence(prevLineStart, prevLineEnd).toString()

        // Strip inline comment before checking the line-ending colon
        val prevLineNoComment = prevLine.replace(Regex("//.*$"), "").replace(Regex("/\\*.*?\\*/"), "")
        val prevLineTrimmed = prevLineNoComment.trimEnd()

        // ABL block openers always end with ':' (DO:, FOR EACH...:, PROCEDURE foo:, etc.)
        if (!prevLineTrimmed.endsWith(':')) return Result.Continue

        // Guard against OO member chains like `oObj:SomeMethod():` triggering indent
        val blockOpenerRegex = Regex("""(?i)\b(DO|FOR|REPEAT|PROCEDURE|FUNCTION|METHOD|CLASS|INTERFACE|CASE|CATCH|FINALLY|ON)\b.*:$""")
        if (!blockOpenerRegex.containsMatchIn(prevLineTrimmed)) return Result.Continue

        val indentOptions = CodeStyle.getSettings(file).getIndentOptions(file.fileType)
        val indentUnit = if (indentOptions.USE_TAB_CHARACTER) "\t"
                         else " ".repeat(indentOptions.INDENT_SIZE)

        // Compute absolute target indent from previous line's leading whitespace so
        // this stays correct even when IntelliJ strips trailing whitespace before firing
        val prevLeading = prevLine.takeWhile { it == ' ' || it == '\t' }
        val targetIndent = prevLeading + indentUnit

        val currentLineStart = document.getLineStartOffset(lineNumber)
        val currentLineEnd = document.getLineEndOffset(lineNumber)
        val currentLine = document.charsSequence.subSequence(currentLineStart, currentLineEnd).toString()
        val currentLeading = currentLine.takeWhile { it == ' ' || it == '\t' }

        document.replaceString(currentLineStart, currentLineStart + currentLeading.length, targetIndent)
        editor.caretModel.moveToOffset(currentLineStart + targetIndent.length)

        return Result.Stop
    }
}
