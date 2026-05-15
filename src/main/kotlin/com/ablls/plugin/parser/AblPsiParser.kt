package com.ablls.plugin.parser

import com.ablls.plugin.language.AblLanguage
import com.intellij.extapi.psi.ASTWrapperPsiElement
import com.intellij.extapi.psi.PsiFileBase
import com.intellij.lang.ASTNode
import com.intellij.lang.LightPsiParser
import com.intellij.lang.PsiBuilder
import com.intellij.lang.PsiParser
import com.intellij.openapi.fileTypes.FileType
import com.intellij.psi.FileViewProvider
import com.intellij.psi.PsiElement
import com.intellij.psi.tree.IElementType
import com.ablls.plugin.language.AblFileType

// ─── Fichier PSI racine ───────────────────────────────────────────────────────

class AblFile(viewProvider: FileViewProvider) : PsiFileBase(viewProvider, AblLanguage) {
    override fun getFileType(): FileType = AblFileType.INSTANCE
    override fun toString(): String = "ABL File"
}

// ─── Parser PSI structuré ─────────────────────────────────────────────────────

/**
 * Parser PSI structuré pour ABL.
 *
 * Construit un arbre hiérarchique en encapsulant les blocs ABL dans des nœuds
 * composites typés ([AblTokenTypes.PROCEDURE_BLOCK], [AblTokenTypes.DO_BLOCK], …).
 *
 * Algorithme single-pass, stack-based :
 *   - Détecte les openers de blocs (PROCEDURE/FUNCTION/CLASS/METHOD/DO/REPEAT/…)
 *     en vérifiant qu'un `:` apparaît avant le prochain `.` ([hasBlockColon]).
 *   - Crée un [PsiBuilder.Marker] au début de chaque bloc, empilé dans [blockStack].
 *   - Sur END [qualifier] [.] : dépile et ferme le marker le plus récent.
 *   - Robuste aux erreurs : les markers non fermés sont fermés à la fin.
 *
 * Résultat — exemple pour `PROCEDURE foo: DO: END. END PROCEDURE.` :
 *   AblFile
 *     PROCEDURE_BLOCK
 *       KEYWORD_DEF  "PROCEDURE"
 *       IDENTIFIER   "foo"
 *       COLON        ":"
 *       DO_BLOCK
 *         KEYWORD_FLOW "DO"
 *         COLON        ":"
 *         KEYWORD_FLOW "END"
 *         DOT          "."
 *       KEYWORD_FLOW "END"
 *       KEYWORD_DEF  "PROCEDURE"
 *       DOT          "."
 */
class AblPsiParser : PsiParser, LightPsiParser {

    override fun parse(root: IElementType, builder: PsiBuilder): ASTNode {
        parseLight(root, builder)
        return builder.treeBuilt
    }

    override fun parseLight(root: IElementType, builder: PsiBuilder) {
        val rootMarker = builder.mark()
        val blockStack = ArrayDeque<Pair<PsiBuilder.Marker, IElementType>>()

        while (!builder.eof()) {
            val tokenText = builder.tokenText?.trim()?.uppercase() ?: ""

            when {
                tokenText == "END" -> {
                    // Consume END, optional qualifier, optional period — inside the current block
                    builder.advanceLexer()

                    val qualText = builder.tokenText?.trim()?.uppercase() ?: ""
                    if (qualText in END_QUALIFIERS) builder.advanceLexer()

                    if (builder.tokenType == AblTokenTypes.DOT) builder.advanceLexer()

                    // Close the innermost open block (if any)
                    if (blockStack.isNotEmpty()) {
                        val (marker, type) = blockStack.removeLast()
                        marker.done(type)
                    }
                }

                else -> {
                    val blockType = OPENER_MAP[tokenText]
                    if (blockType != null && hasBlockColon(builder)) {
                        // Open a new block — marker wraps from this keyword to the matching END.
                        val marker = builder.mark()
                        builder.advanceLexer()
                        blockStack.addLast(marker to blockType)
                    } else {
                        builder.advanceLexer()
                    }
                }
            }
        }

        // Error recovery: close any unclosed blocks
        while (blockStack.isNotEmpty()) {
            val (marker, type) = blockStack.removeLast()
            marker.done(type)
        }

        rootMarker.done(root)
    }

    /**
     * Looks ahead (by IElementType, without consuming) to check whether a `:` appears
     * before the first `.` at parenthesis depth 0 within the next [MAX_LOOKAHEAD] tokens.
     *
     * This correctly identifies block-opening statements (PROCEDURE foo:, DO:, etc.)
     * vs statements that happen to start with the same keyword (DISPLAY x FOR EACH t.).
     */
    private fun hasBlockColon(builder: PsiBuilder): Boolean {
        var depth = 0
        for (i in 1..MAX_LOOKAHEAD) {
            when (builder.rawLookup(i) ?: return false) {
                AblTokenTypes.LPAREN  -> depth++
                AblTokenTypes.RPAREN  -> if (depth > 0) depth--
                AblTokenTypes.COLON   -> if (depth == 0) return true
                AblTokenTypes.DOT     -> return false
            }
        }
        return false
    }

    companion object {
        private const val MAX_LOOKAHEAD = 80

        /** Maps block-opener keyword texts (uppercase) to their composite element type. */
        private val OPENER_MAP: Map<String, IElementType> = mapOf(
            "PROCEDURE"   to AblTokenTypes.PROCEDURE_BLOCK,
            "FUNCTION"    to AblTokenTypes.FUNCTION_BLOCK,
            "CLASS"       to AblTokenTypes.CLASS_BLOCK,
            "INTERFACE"   to AblTokenTypes.INTERFACE_BLOCK,
            "METHOD"      to AblTokenTypes.METHOD_BLOCK,
            "CONSTRUCTOR" to AblTokenTypes.CONSTRUCTOR_BLOCK,
            "DESTRUCTOR"  to AblTokenTypes.DESTRUCTOR_BLOCK,
            "DO"          to AblTokenTypes.DO_BLOCK,
            "REPEAT"      to AblTokenTypes.REPEAT_BLOCK,
            "FOR"         to AblTokenTypes.FOR_BLOCK,
            "CATCH"       to AblTokenTypes.CATCH_BLOCK,
            "FINALLY"     to AblTokenTypes.FINALLY_BLOCK,
            "CASE"        to AblTokenTypes.CASE_BLOCK,
        )

        /** Qualifier keywords that can follow END (consumed as part of the END clause). */
        private val END_QUALIFIERS: Set<String> = setOf(
            "PROCEDURE", "FUNCTION", "CLASS", "INTERFACE",
            "METHOD", "CONSTRUCTOR", "DESTRUCTOR",
            "CATCH", "FINALLY", "CASE"
        )
    }
}

// ─── Factory d'éléments PSI ───────────────────────────────────────────────────

object AblElementFactory {
    fun createElement(node: ASTNode): PsiElement = ASTWrapperPsiElement(node)
}
