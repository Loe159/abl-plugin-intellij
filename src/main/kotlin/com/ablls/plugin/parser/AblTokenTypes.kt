package com.ablls.plugin.parser

import com.intellij.psi.tree.IElementType
import com.ablls.plugin.language.AblLanguage

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
}
