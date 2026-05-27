package com.ablls.plugin.highlight

import com.ablls.plugin.parser.AblTokenTypes
import com.intellij.formatting.Alignment
import com.intellij.formatting.Block
import com.intellij.formatting.FormattingContext
import com.intellij.formatting.FormattingModel
import com.intellij.formatting.FormattingModelBuilder
import com.intellij.formatting.FormattingModelProvider
import com.intellij.formatting.Indent
import com.intellij.formatting.Spacing
import com.intellij.formatting.Wrap
import com.intellij.formatting.WrapType
import com.intellij.lang.ASTNode
import com.intellij.psi.codeStyle.CodeStyleSettings
import com.intellij.psi.formatter.common.AbstractBlock

/**
 * Formatter ABL — indentation structurelle en un seul passage.
 *
 * Avec un PSI plat (tous les tokens sont fils directs de AblFile), le formatter
 * ne peut pas utiliser l'arbre PSI pour déterminer la profondeur. À la place,
 * [buildChildren] parcourt les tokens une seule fois, maintient une pile de blocs
 * ouverts, et attribue à chaque token sa profondeur d'indentation.
 *
 * Règles de détection de blocs :
 *   Ouverture : KEYWORD de bloc (PROCEDURE, CLASS, DO, FOR, REPEAT, CATCH, FINALLY,
 *               FUNCTION, METHOD, INTERFACE, CONSTRUCTOR, DESTRUCTOR, CASE) suivi de `:`.
 *   Fermeture : token dont le texte commence par `END` (END, END., END PROCEDURE., etc.)
 *
 * L'algorithme est identique à celui de [AblFoldingBuilder] — mais en O(n) par fichier.
 */
class AblFormattingModelBuilder : FormattingModelBuilder {
    override fun createModel(formattingContext: FormattingContext): FormattingModel {
        val settings = formattingContext.codeStyleSettings
        val psiFile = formattingContext.psiElement.containingFile
        val root = psiFile.node

        return FormattingModelProvider.createFormattingModelForPsiFile(
            psiFile,
            AblRootBlock(root, settings),
            settings,
        )
    }
}

// ─── Bloc racine (fichier) ────────────────────────────────────────────────────

private class AblRootBlock(
    node: ASTNode,
    private val settings: CodeStyleSettings,
) : AbstractBlock(node, Wrap.createWrap(WrapType.NONE, false), Alignment.createAlignment()) {
    override fun buildChildren(): List<Block> {
        val tokens = collectTokens(node)
        val depths = computeDepths(tokens)
        return tokens.indices.map { i -> AblLeafBlock(tokens[i], settings, depths[i]) }
    }

    override fun getSpacing(
        child1: Block?,
        child2: Block,
    ): Spacing? = null

    override fun isLeaf(): Boolean = false

    override fun getIndent(): Indent = Indent.getNoneIndent()

    // ── Collecte des tokens non-whitespace ────────────────────────────────────

    private fun collectTokens(parent: ASTNode): List<ASTNode> {
        val result = mutableListOf<ASTNode>()
        var child = parent.firstChildNode
        while (child != null) {
            if (child.elementType != AblTokenTypes.WHITE_SPACE) result.add(child)
            child = child.treeNext
        }
        return result
    }

    // ── Calcul des profondeurs en un passage ──────────────────────────────────

    /**
     * Attribue une profondeur d'indentation à chaque token.
     *
     * Invariant : depth = nombre de blocs ouverts et non fermés AVANT ce token.
     * END et les fins de bloc ramènent depth à max(0, depth-1).
     */
    private fun computeDepths(tokens: List<ASTNode>): IntArray {
        val depths = IntArray(tokens.size)
        var depth = 0
        var i = 0

        while (i < tokens.size) {
            val text = tokens[i].text.trim().uppercase()

            when {
                // ── Fermeture de bloc ─────────────────────────────────────────
                text == "END" || text.startsWith("END.") || text.startsWith("END ") -> {
                    depth = maxOf(0, depth - 1)
                    depths[i] = depth
                    // Sauter le qualificateur optionnel (END PROCEDURE, END CLASS…)
                    val next = tokens.getOrNull(i + 1)?.text?.trim()?.uppercase()
                    if (next != null && next in END_QUALIFIERS) {
                        i++
                        depths[i] = depth
                    }
                    // Sauter le point terminal si présent
                    val afterQual = tokens.getOrNull(i + 1)?.text?.trim()
                    if (afterQual == ".") {
                        i++
                        depths[i] = depth
                    }
                }

                // ── Ouverture de bloc ─────────────────────────────────────────
                text in BLOCK_STARTERS && hasColonAhead(tokens, i) -> {
                    depths[i] = depth
                    // Absorber tous les tokens jusqu'au ':' inclus au même niveau
                    var j = i + 1
                    var parenDepth = 0
                    while (j < tokens.size) {
                        val t = tokens[j].text.trim()
                        when {
                            t == "(" -> {
                                depths[j] = depth
                                parenDepth++
                            }
                            t == ")" -> {
                                if (parenDepth > 0) parenDepth--
                                depths[j] = depth
                            }
                            t == ":" && parenDepth == 0 -> {
                                depths[j] = depth
                                i = j
                                break
                            }
                            else -> depths[j] = depth
                        }
                        j++
                    }
                    depth++
                }

                // ── Commentaire de bloc multiligne ────────────────────────────
                tokens[i].elementType == AblTokenTypes.BLOCK_COMMENT -> depths[i] = depth

                // ── Token standard ────────────────────────────────────────────
                else -> depths[i] = depth
            }
            i++
        }
        return depths
    }

    /**
     * Retourne true si un `:` apparaît avant le prochain `END` ou `.` (terminateur),
     * en ignorant les `:` dans les parenthèses (expressions OO).
     */
    private fun hasColonAhead(
        tokens: List<ASTNode>,
        startIdx: Int,
    ): Boolean {
        var parenDepth = 0
        val limit = minOf(tokens.size, startIdx + 50)
        for (i in startIdx + 1 until limit) {
            val t = tokens[i].text.trim()
            when {
                t == "(" -> parenDepth++
                t == ")" -> if (parenDepth > 0) parenDepth--
                t == ":" && parenDepth == 0 -> return true
                (t == "END" || t == ".") && parenDepth == 0 -> return false
            }
        }
        return false
    }

    companion object {
        private val BLOCK_STARTERS =
            setOf(
                "PROCEDURE", "FUNCTION", "CLASS", "INTERFACE", "ENUM",
                "METHOD", "CONSTRUCTOR", "DESTRUCTOR",
                "DO", "FOR", "REPEAT",
                "CATCH", "FINALLY", "CASE",
            )
        private val END_QUALIFIERS =
            setOf(
                "PROCEDURE", "FUNCTION", "CLASS", "INTERFACE", "METHOD",
                "CONSTRUCTOR", "DESTRUCTOR", "CATCH", "FINALLY", "CASE",
            )
    }
}

// ─── Bloc feuille (token) ─────────────────────────────────────────────────────

private class AblLeafBlock(
    node: ASTNode,
    private val settings: CodeStyleSettings,
    private val blockDepth: Int,
) : AbstractBlock(node, Wrap.createWrap(WrapType.NONE, false), Alignment.createAlignment()) {
    override fun buildChildren(): List<Block> = emptyList()

    override fun getSpacing(
        child1: Block?,
        child2: Block,
    ): Spacing? = null

    override fun isLeaf(): Boolean = true

    override fun getIndent(): Indent? {
        if (node.elementType == AblTokenTypes.BLOCK_COMMENT) return Indent.getNoneIndent()
        return when (blockDepth) {
            0 -> Indent.getNoneIndent()
            else -> Indent.getNormalIndent()
        }
    }
}
