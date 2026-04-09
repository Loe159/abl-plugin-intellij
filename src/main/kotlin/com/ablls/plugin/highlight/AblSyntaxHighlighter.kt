package com.ablls.plugin.highlight

import com.ablls.plugin.parser.AblLexerAdapter
import com.ablls.plugin.parser.AblTokenTypes
import com.intellij.lexer.Lexer
import com.intellij.openapi.editor.DefaultLanguageHighlighterColors as Default
import com.intellij.openapi.editor.colors.TextAttributesKey
import com.intellij.openapi.editor.colors.TextAttributesKey.createTextAttributesKey
import com.intellij.openapi.fileTypes.SyntaxHighlighterBase
import com.intellij.psi.tree.IElementType

/**
 * Coloration syntaxique ABL.
 *
 * Chaque [TextAttributesKey] correspond à une "catégorie" configurable
 * dans Settings → Editor → Color Scheme → ABL.
 *
 * L'utilisateur peut personnaliser les couleurs dans l'IDE.
 */
class AblSyntaxHighlighter : SyntaxHighlighterBase() {

    companion object {

        // ── Clés de couleurs (héritent des couleurs par défaut de l'IDE) ──────

        @JvmField val KEYWORD = createTextAttributesKey(
            "ABL_KEYWORD", Default.KEYWORD
        )
        @JvmField val KEYWORD_FLOW = createTextAttributesKey(
            "ABL_KEYWORD_FLOW", Default.KEYWORD
        )
        @JvmField val KEYWORD_DEF = createTextAttributesKey(
            "ABL_KEYWORD_DEF", Default.FUNCTION_DECLARATION
        )
        @JvmField val KEYWORD_DB = createTextAttributesKey(
            "ABL_KEYWORD_DB", Default.CONSTANT
        )
        @JvmField val KEYWORD_MOD = createTextAttributesKey(
            "ABL_KEYWORD_MOD", Default.METADATA
        )
        @JvmField val KEYWORD_TYPE = createTextAttributesKey(
            "ABL_KEYWORD_TYPE", Default.CLASS_NAME
        )
        @JvmField val STRING = createTextAttributesKey(
            "ABL_STRING", Default.STRING
        )
        @JvmField val NUMBER = createTextAttributesKey(
            "ABL_NUMBER", Default.NUMBER
        )
        @JvmField val LOGICAL_LITERAL = createTextAttributesKey(
            "ABL_LOGICAL_LITERAL", Default.KEYWORD
        )
        @JvmField val BLOCK_COMMENT = createTextAttributesKey(
            "ABL_BLOCK_COMMENT", Default.BLOCK_COMMENT
        )
        @JvmField val LINE_COMMENT = createTextAttributesKey(
            "ABL_LINE_COMMENT", Default.LINE_COMMENT
        )
        @JvmField val PREPROCESSOR = createTextAttributesKey(
            "ABL_PREPROCESSOR", Default.METADATA
        )
        @JvmField val OPERATOR = createTextAttributesKey(
            "ABL_OPERATOR", Default.OPERATION_SIGN
        )
        @JvmField val DOT = createTextAttributesKey(
            "ABL_DOT", Default.DOT
        )
        @JvmField val COLON = createTextAttributesKey(
            "ABL_COLON", Default.DOT
        )
        @JvmField val COMMA = createTextAttributesKey(
            "ABL_COMMA", Default.COMMA
        )
        @JvmField val PARENTHESES = createTextAttributesKey(
            "ABL_PARENTHESES", Default.PARENTHESES
        )
        @JvmField val IDENTIFIER = createTextAttributesKey(
            "ABL_IDENTIFIER", Default.IDENTIFIER
        )
        @JvmField val ANNOTATION = createTextAttributesKey(
            "ABL_ANNOTATION", Default.METADATA
        )
        @JvmField val BAD_CHARACTER = createTextAttributesKey(
            "ABL_BAD_CHARACTER", Default.INVALID_STRING_ESCAPE
        )

        // ── Tableaux de lookup token → couleur ───────────────────────────────

        private val KEYWORD_KEYS         = arrayOf(KEYWORD)
        private val KEYWORD_FLOW_KEYS    = arrayOf(KEYWORD_FLOW)
        private val KEYWORD_DEF_KEYS     = arrayOf(KEYWORD_DEF)
        private val KEYWORD_DB_KEYS      = arrayOf(KEYWORD_DB)
        private val KEYWORD_MOD_KEYS     = arrayOf(KEYWORD_MOD)
        private val KEYWORD_TYPE_KEYS    = arrayOf(KEYWORD_TYPE)
        private val STRING_KEYS          = arrayOf(STRING)
        private val NUMBER_KEYS          = arrayOf(NUMBER)
        private val LOGICAL_KEYS         = arrayOf(LOGICAL_LITERAL)
        private val BLOCK_COMMENT_KEYS   = arrayOf(BLOCK_COMMENT)
        private val LINE_COMMENT_KEYS    = arrayOf(LINE_COMMENT)
        private val PREPROCESSOR_KEYS    = arrayOf(PREPROCESSOR)
        private val OPERATOR_KEYS        = arrayOf(OPERATOR)
        private val DOT_KEYS             = arrayOf(DOT)
        private val COLON_KEYS           = arrayOf(COLON)
        private val COMMA_KEYS           = arrayOf(COMMA)
        private val PAREN_KEYS           = arrayOf(PARENTHESES)
        private val IDENTIFIER_KEYS      = arrayOf(IDENTIFIER)
        private val ANNOTATION_KEYS      = arrayOf(ANNOTATION)
        private val BAD_CHAR_KEYS        = arrayOf(BAD_CHARACTER)
        private val EMPTY                = emptyArray<TextAttributesKey>()
    }

    override fun getHighlightingLexer(): Lexer = AblLexerAdapter()

    override fun getTokenHighlights(tokenType: IElementType): Array<TextAttributesKey> =
        when (tokenType) {
            AblTokenTypes.KEYWORD        -> KEYWORD_KEYS
            AblTokenTypes.KEYWORD_FLOW   -> KEYWORD_FLOW_KEYS
            AblTokenTypes.KEYWORD_DEF    -> KEYWORD_DEF_KEYS
            AblTokenTypes.KEYWORD_DB     -> KEYWORD_DB_KEYS
            AblTokenTypes.KEYWORD_MOD    -> KEYWORD_MOD_KEYS
            AblTokenTypes.KEYWORD_TYPE   -> KEYWORD_TYPE_KEYS
            AblTokenTypes.STRING         -> STRING_KEYS
            AblTokenTypes.NUMBER         -> NUMBER_KEYS
            AblTokenTypes.LOGICAL_LITERAL -> LOGICAL_KEYS
            AblTokenTypes.BLOCK_COMMENT  -> BLOCK_COMMENT_KEYS
            AblTokenTypes.LINE_COMMENT   -> LINE_COMMENT_KEYS
            AblTokenTypes.PREPROCESSOR   -> PREPROCESSOR_KEYS
            AblTokenTypes.OPERATOR       -> OPERATOR_KEYS
            AblTokenTypes.DOT            -> DOT_KEYS
            AblTokenTypes.COLON          -> COLON_KEYS
            AblTokenTypes.COMMA          -> COMMA_KEYS
            AblTokenTypes.LPAREN,
            AblTokenTypes.RPAREN         -> PAREN_KEYS
            AblTokenTypes.IDENTIFIER     -> IDENTIFIER_KEYS
            AblTokenTypes.ANNOTATION     -> ANNOTATION_KEYS
            AblTokenTypes.BAD_CHARACTER  -> BAD_CHAR_KEYS
            AblTokenTypes.WHITE_SPACE    -> EMPTY
            else                         -> EMPTY
        }
}
