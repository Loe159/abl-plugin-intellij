package com.ablls.plugin.parser

import com.intellij.lexer.LexerBase
import com.intellij.psi.tree.IElementType
import org.prorefactor.core.ABLNodeType

// N'utilise pas ABLLexer directement — conçu pour le pipeline complet, pas le streaming IntelliJ.
class AblLexerAdapter : LexerBase() {

    // ─── État courant ─────────────────────────────────────────────────────────

    private var buffer:      CharSequence = ""
    private var startOffset: Int          = 0
    private var endOffset:   Int          = 0

    private var tokenList:  List<Triple<IElementType?, Int, Int>> = emptyList()
    private var tokenIndex: Int = 0

    // ─── IntelliJ Lexer API ───────────────────────────────────────────────────

    override fun start(buffer: CharSequence, startOffset: Int, endOffset: Int, initialState: Int) {
        this.buffer      = buffer
        this.startOffset = startOffset
        this.endOffset   = endOffset
        this.tokenList   = buildTokenList(buffer, startOffset, endOffset)
        this.tokenIndex  = -1
        advance()
    }

    override fun advance() { tokenIndex++ }

    override fun getTokenType():  IElementType? = tokenList.getOrNull(tokenIndex)?.first
    override fun getTokenStart(): Int = tokenList.getOrNull(tokenIndex)?.second ?: endOffset
    override fun getTokenEnd():   Int = tokenList.getOrNull(tokenIndex)?.third  ?: endOffset
    override fun getState():      Int = 0

    override fun getBufferSequence(): CharSequence = buffer
    override fun getBufferEnd():      Int          = endOffset

    // ─── Construction de la liste de tokens ──────────────────────────────────

    private fun buildTokenList(
        buffer: CharSequence,
        startOffset: Int,
        endOffset: Int
    ): List<Triple<IElementType?, Int, Int>> {
        if (startOffset >= endOffset) return emptyList()

        val result = mutableListOf<Triple<IElementType?, Int, Int>>()
        var pos = startOffset

        while (pos < endOffset) {
            val (type, end) = matchAt(buffer, pos, endOffset)
            result.add(Triple(type, pos, end))
            pos = end
        }

        return result
    }

    // ─── Scanner de tokens ────────────────────────────────────────────────────

    private fun matchAt(buf: CharSequence, pos: Int, end: Int): Pair<IElementType, Int> {
        val c = buf[pos]

        // ── Commentaire bloc /* ... */ ────────────────────────────────────────
        if (c == '/' && pos + 1 < end && buf[pos + 1] == '*') {
            var i = pos + 2
            while (i < end - 1) {
                if (buf[i] == '*' && buf[i + 1] == '/') return AblTokenTypes.BLOCK_COMMENT to i + 2
                i++
            }
            return AblTokenTypes.BLOCK_COMMENT to end   // commentaire non fermé → jusqu'à la fin
        }

        // ── Commentaire ligne // ──────────────────────────────────────────────
        if (c == '/' && pos + 1 < end && buf[pos + 1] == '/') {
            var i = pos + 2
            while (i < end && buf[i] != '\n') i++
            return AblTokenTypes.LINE_COMMENT to i
        }

        // ── Chaîne double-guillemets "..." ────────────────────────────────────
        if (c == '"') {
            var i = pos + 1
            while (i < end) {
                val ch = buf[i]
                if (ch == '~' && i + 1 < end) { i += 2; continue }   // ~" escape ABL
                if (ch == '"') return AblTokenTypes.STRING to i + 1
                i++
            }
            return AblTokenTypes.STRING to end
        }

        // ── Chaîne simple-guillemets '...' ────────────────────────────────────
        if (c == '\'') {
            var i = pos + 1
            while (i < end && buf[i] != '\'') i++
            return AblTokenTypes.STRING to minOf(i + 1, end)
        }

        // ── Préprocesseur &DEFINE &IF ... ─────────────────────────────────────
        if (c == '&') {
            var i = pos + 1
            while (i < end && (buf[i].isLetterOrDigit() || buf[i] == '_' || buf[i] == '-')) i++
            return AblTokenTypes.PREPROCESSOR to i
        }

        // ── Include {fichier.i} ────────────────────────────────────────────────
        if (c == '{') {
            var i = pos + 1
            while (i < end && buf[i] != '}') i++
            return AblTokenTypes.PREPROCESSOR to minOf(i + 1, end)
        }

        // ── Annotation @Nom ────────────────────────────────────────────────────
        if (c == '@') {
            var i = pos + 1
            while (i < end && (buf[i].isLetterOrDigit() || buf[i] == '_' || buf[i] == '.')) i++
            return AblTokenTypes.ANNOTATION to i
        }

        // ── Nombre ────────────────────────────────────────────────────────────
        if (c.isDigit()) {
            var i = pos + 1
            while (i < end && (buf[i].isDigit() || buf[i] == '.')) i++
            return AblTokenTypes.NUMBER to i
        }

        // ── Identifiant ou mot-clé ────────────────────────────────────────────
        // ABL autorise les tirets dans les identifiants (NO-UNDO, EXCLUSIVE-LOCK…)
        if (c.isLetter() || c == '_') {
            var i = pos + 1
            while (i < end && (buf[i].isLetterOrDigit() || buf[i] == '_' || buf[i] == '-')) i++
            val word = buf.subSequence(pos, i).toString().uppercase()
            return classifyWord(word) to i
        }

        // ── Valeur inconnue ABL : ? ────────────────────────────────────────────
        if (c == '?') return AblTokenTypes.LOGICAL_LITERAL to pos + 1

        // ── Espaces blancs ────────────────────────────────────────────────────
        if (c.isWhitespace()) {
            var i = pos + 1
            while (i < end && buf[i].isWhitespace()) i++
            return AblTokenTypes.WHITE_SPACE to i
        }

        // ── Ponctuations ──────────────────────────────────────────────────────
        if (c == '.') return AblTokenTypes.DOT      to pos + 1
        if (c == ':') return AblTokenTypes.COLON    to pos + 1
        if (c == ',') return AblTokenTypes.COMMA    to pos + 1
        if (c == '(') return AblTokenTypes.LPAREN   to pos + 1
        if (c == ')') return AblTokenTypes.RPAREN   to pos + 1
        if (c == '[') return AblTokenTypes.LBRACKET to pos + 1
        if (c == ']') return AblTokenTypes.RBRACKET to pos + 1

        // ── Opérateur ou caractère inconnu ────────────────────────────────────
        return AblTokenTypes.OPERATOR to pos + 1
    }

    private fun classifyWord(word: String): IElementType =
        ABLNodeType.getLiteral(word.lowercase())
            ?.let { AblTokenTypes.mapAblNodeType(it) }
            ?: AblTokenTypes.IDENTIFIER
}
