package com.ablls.plugin.parser

import com.intellij.lexer.LexerBase
import com.intellij.psi.tree.IElementType

/**
 * Lexer léger pour la coloration syntaxique ABL dans IntelliJ.
 *
 * Stratégie : scanner de caractères avec reconnaissance des patterns ABL.
 * N'utilise PAS ABLLexer (proparse) directement — ce composant est conçu
 * pour le pipeline de parsing complet, pas pour le streaming IntelliJ.
 *
 * Garantit que le stream couvre exactement [startOffset, endOffset]
 * sans offset négatif ni gap, conformément au contrat IntelliJ Lexer.
 */
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
        if (c == '.') return AblTokenTypes.DOT    to pos + 1
        if (c == ':') return AblTokenTypes.COLON  to pos + 1
        if (c == ',') return AblTokenTypes.COMMA  to pos + 1
        if (c == '(') return AblTokenTypes.LPAREN to pos + 1
        if (c == ')') return AblTokenTypes.RPAREN to pos + 1

        // ── Opérateur ou caractère inconnu ────────────────────────────────────
        return AblTokenTypes.OPERATOR to pos + 1
    }

    // ─── Classification des mots-clés ─────────────────────────────────────────

    private fun classifyWord(word: String): IElementType = when (word) {

        // Flux de contrôle
        "IF", "THEN", "ELSE", "DO", "END", "REPEAT",
        "FOR", "EACH", "FIRST", "LAST",
        "CASE", "WHEN", "OTHERWISE",
        "RETURN", "LEAVE", "NEXT", "UNDO",
        "CATCH", "FINALLY", "THROW",
        "BY", "WHILE", "TO", "FROM",
        "BREAK", "CONTINUE"
            -> AblTokenTypes.KEYWORD_FLOW

        // Définitions / structure
        "DEFINE", "DEF", "VARIABLE", "VAR",
        "PARAMETER", "PARAM",
        "TEMP-TABLE", "WORKFILE",
        "PROCEDURE", "PROC", "FUNCTION",
        "CLASS", "INTERFACE", "ENUM",
        "METHOD", "PROPERTY", "EVENT",
        "CONSTRUCTOR", "DESTRUCTOR",
        "DATASET", "QUERY", "BUFFER",
        "USING", "FIELD", "FIELDS", "INDEX",
        "INHERITS", "IMPLEMENTS",
        "NAMESPACE-URI", "NAMESPACE-PREFIX"
            -> AblTokenTypes.KEYWORD_DEF

        // Types primitifs
        "CHARACTER", "CHAR",
        "INTEGER", "INT",
        "INT64",
        "DECIMAL", "DEC",
        "LOGICAL",
        "DATE", "DATETIME", "DATETIME-TZ",
        "HANDLE",
        "LONGCHAR",
        "MEMPTR",
        "RAW",
        "ROWID", "RECID",
        "VOID", "OBJECT",
        "PROGRESS.LANG.OBJECT"
            -> AblTokenTypes.KEYWORD_TYPE

        // Modificateurs d'accès / qualificateurs
        "PUBLIC", "PRIVATE", "PROTECTED", "PACKAGE-PRIVATE",
        "STATIC", "ABSTRACT", "OVERRIDE", "FINAL",
        "NEW", "EXTENT",
        "NO-UNDO",
        "INPUT", "OUTPUT", "INPUT-OUTPUT"
            -> AblTokenTypes.KEYWORD_MOD

        // Accès base de données
        "FIND", "CREATE", "DELETE",
        "WHERE", "AND", "OR", "NOT",
        "EXCLUSIVE-LOCK", "SHARE-LOCK", "NO-LOCK",
        "AVAILABLE", "TRANSACTION",
        "OPEN", "CLOSE", "GET", "NEXT-PROMPT",
        "TABLE", "OF", "USE-INDEX",
        "PRESELECT"
            -> AblTokenTypes.KEYWORD_DB

        // Littéraux booléens / inconnu
        "TRUE", "FALSE", "YES", "NO",
        "YES-NO", "YES-NO-CANCEL",
        "UNKNOWN"
            -> AblTokenTypes.LOGICAL_LITERAL

        // Tout le reste est un mot-clé générique
        else -> AblTokenTypes.KEYWORD
    }
}
