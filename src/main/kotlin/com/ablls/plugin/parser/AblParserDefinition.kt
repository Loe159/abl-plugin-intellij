package com.ablls.plugin.parser

import com.ablls.plugin.language.AblLanguage
import com.intellij.lang.ASTNode
import com.intellij.lang.ParserDefinition
import com.intellij.lang.PsiParser
import com.intellij.lexer.Lexer
import com.intellij.openapi.project.Project
import com.intellij.psi.FileViewProvider
import com.intellij.psi.PsiElement
import com.intellij.psi.PsiFile
import com.intellij.psi.tree.IFileElementType
import com.intellij.psi.tree.TokenSet

/**
 * Point d'entrée IntelliJ pour le parsing PSI du langage ABL.
 *
 * Le PSI (Program Structure Interface) est l'arbre de syntaxe qu'IntelliJ
 * utilise en interne pour tout : coloration, navigation, refactoring, etc.
 *
 * Architecture :
 *   - Le Lexer est notre adaptateur CABL (tokens ANTLR4 → IElementType)
 *   - Le Parser construit un PSI léger (stub tree) pour la navigation
 *   - La coloration syntaxique est gérée séparément par AblSyntaxHighlighter
 */
class AblParserDefinition : ParserDefinition {
    companion object {
        @JvmField
        val FILE = IFileElementType(AblLanguage)

        // Token sets utilisés par IntelliJ pour des comportements automatiques
        // (sélection de mot, smart indent, bracket matching...)
        @JvmField
        val COMMENTS =
            TokenSet.create(
                AblTokenTypes.BLOCK_COMMENT,
                AblTokenTypes.LINE_COMMENT,
            )

        @JvmField
        val STRINGS = TokenSet.create(AblTokenTypes.STRING)

        @JvmField
        val KEYWORDS =
            TokenSet.create(
                AblTokenTypes.KEYWORD,
                AblTokenTypes.KEYWORD_FLOW,
                AblTokenTypes.KEYWORD_DEF,
                AblTokenTypes.KEYWORD_DB,
                AblTokenTypes.KEYWORD_MOD,
                AblTokenTypes.KEYWORD_TYPE,
            )

        @JvmField
        val WHITESPACES = TokenSet.create(AblTokenTypes.WHITE_SPACE)
    }

    override fun createLexer(project: Project?): Lexer = AblLexerAdapter()

    override fun createParser(project: Project?): PsiParser = AblPsiParser()

    override fun getFileNodeType(): IFileElementType = FILE

    override fun getCommentTokens(): TokenSet = COMMENTS

    override fun getStringLiteralElements(): TokenSet = STRINGS

    override fun getWhitespaceTokens(): TokenSet = WHITESPACES

    override fun createElement(node: ASTNode): PsiElement = AblElementFactory.createElement(node)

    override fun createFile(viewProvider: FileViewProvider): PsiFile = AblFile(viewProvider)
}
