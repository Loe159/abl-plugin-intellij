package com.ablls.plugin.parser

import com.intellij.psi.tree.IElementType
import com.ablls.plugin.language.AblLanguage
import org.prorefactor.core.ABLNodeType

// ─── IElementType de base ─────────────────────────────────────────────────────

class AblTokenType(debugName: String) : IElementType(debugName, AblLanguage) {
    override fun toString(): String = "AblTokenType.$debugName"
}

class AblElementType(debugName: String) : IElementType(debugName, AblLanguage)

// ─── Catégories de tokens pour la coloration syntaxique ──────────────────────
// Ces constantes sont utilisées par AblSyntaxHighlighter pour mapper
// chaque token CABL (ABLNodeType) vers une couleur dans l'éditeur.

object AblTokenTypes {

    // ── Mots-clés ────────────────────────────────────────────────────────────
    @JvmField val KEYWORD        = AblTokenType("KEYWORD")

    // ── Mots-clés de flux (IF THEN ELSE DO END REPEAT FOR etc.) ─────────────
    @JvmField val KEYWORD_FLOW   = AblTokenType("KEYWORD_FLOW")

    // ── Mots-clés de définition (DEFINE VARIABLE CLASS METHOD etc.) ──────────
    @JvmField val KEYWORD_DEF    = AblTokenType("KEYWORD_DEF")

    // ── Mots-clés de DB (FIND FOR EACH WHERE EXCLUSIVE-LOCK etc.) ────────────
    @JvmField val KEYWORD_DB     = AblTokenType("KEYWORD_DB")

    // ── Modificateurs d'accès (PUBLIC PRIVATE PROTECTED STATIC etc.) ─────────
    @JvmField val KEYWORD_MOD    = AblTokenType("KEYWORD_MOD")

    // ── Types primitifs (CHARACTER INTEGER DECIMAL LOGICAL DATE etc.) ────────
    @JvmField val KEYWORD_TYPE   = AblTokenType("KEYWORD_TYPE")

    // ── Littéraux ─────────────────────────────────────────────────────────────
    @JvmField val STRING         = AblTokenType("STRING")
    @JvmField val NUMBER         = AblTokenType("NUMBER")
    @JvmField val LOGICAL_LITERAL = AblTokenType("LOGICAL_LITERAL")  // TRUE/FALSE/YES/NO

    // ── Commentaires ──────────────────────────────────────────────────────────
    @JvmField val BLOCK_COMMENT  = AblTokenType("BLOCK_COMMENT")
    @JvmField val LINE_COMMENT   = AblTokenType("LINE_COMMENT")

    // ── Préprocesseur ─────────────────────────────────────────────────────────
    @JvmField val PREPROCESSOR   = AblTokenType("PREPROCESSOR")   // &DEFINE &IF {include}

    // ── Opérateurs ────────────────────────────────────────────────────────────
    @JvmField val OPERATOR       = AblTokenType("OPERATOR")

    // ── Ponctuations ──────────────────────────────────────────────────────────
    @JvmField val DOT            = AblTokenType("DOT")
    @JvmField val COLON          = AblTokenType("COLON")
    @JvmField val COMMA          = AblTokenType("COMMA")
    @JvmField val LPAREN         = AblTokenType("LPAREN")
    @JvmField val RPAREN         = AblTokenType("RPAREN")

    // ── Identifiants ──────────────────────────────────────────────────────────
    @JvmField val IDENTIFIER     = AblTokenType("IDENTIFIER")

    // ── Annotation (@SerializeName etc.) ──────────────────────────────────────
    @JvmField val ANNOTATION     = AblTokenType("ANNOTATION")

    // ── Inconnu / erreur ──────────────────────────────────────────────────────
    @JvmField val BAD_CHARACTER  = AblTokenType("BAD_CHARACTER")
    @JvmField val WHITE_SPACE    = AblTokenType("WHITE_SPACE")

    // ─── Mapping ABLNodeType → IElementType ──────────────────────────────────

    private val FLOW_NODES = setOf(
        ABLNodeType.IF, ABLNodeType.THEN, ABLNodeType.ELSE,
        ABLNodeType.DO, ABLNodeType.END,
        ABLNodeType.REPEAT, ABLNodeType.FOR, ABLNodeType.EACH, ABLNodeType.FIRST, ABLNodeType.LAST,
        ABLNodeType.CASE, ABLNodeType.WHEN, ABLNodeType.OTHERWISE,
        ABLNodeType.RETURN, ABLNodeType.LEAVE, ABLNodeType.NEXT, ABLNodeType.UNDO,
        ABLNodeType.CATCH, ABLNodeType.FINALLY, ABLNodeType.THROW,
        ABLNodeType.BY, ABLNodeType.WHILE, ABLNodeType.TO, ABLNodeType.FROM,
        ABLNodeType.BREAK
    )

    private val DEF_NODES = setOf(
        ABLNodeType.DEFINE, ABLNodeType.VARIABLE,
        ABLNodeType.PARAMETER,
        ABLNodeType.TEMPTABLE,
        ABLNodeType.PROCEDURE, ABLNodeType.FUNCTION,
        ABLNodeType.CLASS, ABLNodeType.INTERFACE, ABLNodeType.ENUM,
        ABLNodeType.METHOD, ABLNodeType.PROPERTY, ABLNodeType.EVENT,
        ABLNodeType.CONSTRUCTOR, ABLNodeType.DESTRUCTOR,
        ABLNodeType.DATASET, ABLNodeType.QUERY, ABLNodeType.BUFFER,
        ABLNodeType.USING, ABLNodeType.FIELD, ABLNodeType.INDEX,
        ABLNodeType.INHERITS, ABLNodeType.IMPLEMENTS
    )

    private val TYPE_NODES = setOf(
        ABLNodeType.CHARACTER, ABLNodeType.INTEGER, ABLNodeType.INT64,
        ABLNodeType.DECIMAL, ABLNodeType.LOGICAL,
        ABLNodeType.DATE, ABLNodeType.DATETIME, ABLNodeType.DATETIMETZ,
        ABLNodeType.HANDLE, ABLNodeType.LONGCHAR, ABLNodeType.MEMPTR,
        ABLNodeType.RAW, ABLNodeType.ROWID, ABLNodeType.RECID,
        ABLNodeType.VOID, ABLNodeType.OBJECT
    )

    private val MOD_NODES = setOf(
        ABLNodeType.PUBLIC, ABLNodeType.PRIVATE, ABLNodeType.PROTECTED,
        ABLNodeType.STATIC, ABLNodeType.ABSTRACT, ABLNodeType.OVERRIDE, ABLNodeType.FINAL,
        ABLNodeType.NEW, ABLNodeType.EXTENT,
        ABLNodeType.NOUNDO,
        ABLNodeType.INPUT, ABLNodeType.OUTPUT, ABLNodeType.INPUTOUTPUT
    )

    private val DB_NODES = setOf(
        ABLNodeType.FIND, ABLNodeType.CREATE, ABLNodeType.DELETE,
        ABLNodeType.WHERE, ABLNodeType.AND, ABLNodeType.OR, ABLNodeType.NOT,
        ABLNodeType.EXCLUSIVELOCK, ABLNodeType.SHARELOCK, ABLNodeType.NOLOCK,
        ABLNodeType.AVAILABLE, ABLNodeType.TRANSACTION,
        ABLNodeType.OPEN, ABLNodeType.CLOSE, ABLNodeType.GET,
        ABLNodeType.TABLE, ABLNodeType.OF, ABLNodeType.USEINDEX,
        ABLNodeType.PRESELECT
    )

    private val LITERAL_NODES = setOf(
        ABLNodeType.TRUE, ABLNodeType.FALSE, ABLNodeType.YES, ABLNodeType.NO
    )

    fun mapAblNodeType(nodeType: ABLNodeType): IElementType = when {
        nodeType in FLOW_NODES    -> KEYWORD_FLOW
        nodeType in DEF_NODES     -> KEYWORD_DEF
        nodeType in TYPE_NODES    -> KEYWORD_TYPE
        nodeType in MOD_NODES     -> KEYWORD_MOD
        nodeType in DB_NODES      -> KEYWORD_DB
        nodeType in LITERAL_NODES -> LOGICAL_LITERAL
        nodeType.isKeyword        -> KEYWORD
        else                      -> IDENTIFIER
    }
}
