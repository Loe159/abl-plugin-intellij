package com.ablls.plugin.parser

import com.ablls.plugin.language.AblFileType
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
import org.prorefactor.core.ABLNodeType

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
    override fun parse(
        root: IElementType,
        builder: PsiBuilder,
    ): ASTNode {
        parseLight(root, builder)
        return builder.treeBuilt
    }

    override fun parseLight(
        root: IElementType,
        builder: PsiBuilder,
    ) {
        val rootMarker = builder.mark()
        val blockStack = ArrayDeque<Pair<PsiBuilder.Marker, IElementType>>()

        while (!builder.eof()) {
            val tokenText = builder.tokenText?.trim()?.uppercase() ?: ""

            // Resolve the current token text to an ABLNodeType so abbreviations are handled
            // (e.g. "PROC" → ABLNodeType.PROCEDURE) — mirrors AblFoldingBuilder's strategy.
            val ablType = ABLNodeType.getLiteral(tokenText.lowercase())

            when {
                ablType == ABLNodeType.END -> {
                    // Consume END, optional qualifier, optional period — inside the current block
                    builder.advanceLexer()

                    // Use ABLNodeType to recognise abbreviated qualifiers (END PROC. etc.)
                    val qualRaw = builder.tokenText?.trim()?.lowercase() ?: ""
                    val qualType = ABLNodeType.getLiteral(qualRaw)
                    if (qualType != null && qualType in END_QUALIFIER_TYPES) builder.advanceLexer()

                    if (builder.tokenType == AblTokenTypes.DOT) builder.advanceLexer()

                    // Close the innermost open block (if any)
                    if (blockStack.isNotEmpty()) {
                        val (marker, type) = blockStack.removeLast()
                        marker.done(type)
                    }
                }

                else -> {
                    val blockType = ablType?.let { OPENER_NODE_TYPES[it] }
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
                AblTokenTypes.LPAREN -> depth++
                AblTokenTypes.RPAREN -> if (depth > 0) depth--
                AblTokenTypes.COLON -> if (depth == 0) return true
                AblTokenTypes.DOT -> return false
            }
        }
        return false
    }

    companion object {
        private const val MAX_LOOKAHEAD = 80

        /**
         * Maps [ABLNodeType] block-opener keywords to their composite PSI element type.
         * Using ABLNodeType (not raw strings) means abbreviations are handled automatically
         * via ABLNodeType.getLiteral() in the parse loop (e.g. "PROC" → PROCEDURE_BLOCK).
         */
        private val OPENER_NODE_TYPES: Map<ABLNodeType, IElementType> =
            mapOf(
                ABLNodeType.PROCEDURE to AblTokenTypes.PROCEDURE_BLOCK,
                ABLNodeType.FUNCTION to AblTokenTypes.FUNCTION_BLOCK,
                ABLNodeType.CLASS to AblTokenTypes.CLASS_BLOCK,
                ABLNodeType.INTERFACE to AblTokenTypes.INTERFACE_BLOCK,
                ABLNodeType.METHOD to AblTokenTypes.METHOD_BLOCK,
                ABLNodeType.CONSTRUCTOR to AblTokenTypes.CONSTRUCTOR_BLOCK,
                ABLNodeType.DESTRUCTOR to AblTokenTypes.DESTRUCTOR_BLOCK,
                ABLNodeType.DO to AblTokenTypes.DO_BLOCK,
                ABLNodeType.REPEAT to AblTokenTypes.REPEAT_BLOCK,
                ABLNodeType.FOR to AblTokenTypes.FOR_BLOCK,
                ABLNodeType.CATCH to AblTokenTypes.CATCH_BLOCK,
                ABLNodeType.FINALLY to AblTokenTypes.FINALLY_BLOCK,
                ABLNodeType.CASE to AblTokenTypes.CASE_BLOCK,
            )

        /**
         * ABLNodeType qualifier keywords that can follow END (END PROCEDURE, END CLASS…).
         * Using ABLNodeType mirrors AblFoldingBuilder.END_QUALIFIER_TYPES and handles
         * abbreviated forms (END PROC. etc.) via ABLNodeType.getLiteral().
         */
        private val END_QUALIFIER_TYPES: Set<ABLNodeType> =
            java.util.EnumSet.of(
                ABLNodeType.PROCEDURE, ABLNodeType.FUNCTION, ABLNodeType.CLASS, ABLNodeType.INTERFACE,
                ABLNodeType.METHOD, ABLNodeType.CONSTRUCTOR, ABLNodeType.DESTRUCTOR,
                ABLNodeType.CATCH, ABLNodeType.FINALLY, ABLNodeType.CASE,
            )
    }
}

// ─── Factory d'éléments PSI ───────────────────────────────────────────────────

object AblElementFactory {
    fun createElement(node: ASTNode): PsiElement = ASTWrapperPsiElement(node)
}
