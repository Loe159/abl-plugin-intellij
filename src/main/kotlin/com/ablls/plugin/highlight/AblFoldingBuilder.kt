package com.ablls.plugin.highlight

import com.ablls.plugin.parser.AblTokenTypes
import com.intellij.lang.ASTNode
import com.intellij.lang.BracePair
import com.intellij.lang.Commenter
import com.intellij.lang.PairedBraceMatcher
import com.intellij.lang.folding.FoldingBuilderEx
import com.intellij.lang.folding.FoldingDescriptor
import com.intellij.openapi.editor.Document
import com.intellij.openapi.editor.FoldingGroup
import com.intellij.openapi.util.TextRange
import com.intellij.psi.PsiElement
import com.intellij.psi.PsiFile
import com.intellij.psi.tree.IElementType

// ─── AblFoldingBuilder ───────────────────────────────────────────────────────

/**
 * Pliage de code (Code Folding) pour ABL.
 *
 * Replie les blocs :
 *   - PROCEDURE name: ... END [PROCEDURE].
 *   - FUNCTION name ...: ... END [FUNCTION].
 *   - CLASS name: ... END [CLASS].
 *   - METHOD name ...: ... END [METHOD].
 *   - DO: ... END.
 *   - FOR EACH ...: ... END.
 *   - REPEAT: ... END.
 *   - /* commentaire multi-lignes */
 *
 * Note : dans notre architecture PSI plate, les blocs sont détectés
 * par token matching. Pour un folding hiérarchique précis, il faudrait
 * un PSI arborescent complet.
 */
class AblFoldingBuilder : FoldingBuilderEx() {

    override fun buildFoldRegions(
        root: PsiElement,
        document: Document,
        quick: Boolean
    ): Array<FoldingDescriptor> {
        val descriptors = mutableListOf<FoldingDescriptor>()
        collectFolds(root.node, document, descriptors)
        return descriptors.toTypedArray()
    }

    private fun collectFolds(
        node: ASTNode,
        document: Document,
        descriptors: MutableList<FoldingDescriptor>
    ) {
        // Repli des commentaires bloc multi-lignes
        if (node.elementType == AblTokenTypes.BLOCK_COMMENT) {
            val text = node.text
            if (text.contains('\n')) {
                descriptors.add(
                    FoldingDescriptor(
                        node,
                        node.textRange,
                        FoldingGroup.newGroup("ABL_COMMENT"),
                        "/* ... */"
                    )
                )
            }
        }

        // Descendre dans les enfants
        var child = node.firstChildNode
        while (child != null) {
            collectFolds(child, document, descriptors)
            child = child.treeNext
        }
    }

    override fun getPlaceholderText(node: ASTNode): String? {
        return when (node.elementType) {
            AblTokenTypes.BLOCK_COMMENT -> "/* ... */"
            else -> "..."
        }
    }

    override fun isCollapsedByDefault(node: ASTNode): Boolean = false
}

// ─── AblCommenter ────────────────────────────────────────────────────────────

/**
 * Commentaire de ligne et de bloc pour ABL.
 * Ctrl+/ ou Ctrl+Shift+/ dans l'éditeur.
 */
class AblCommenter : Commenter {
    override fun getLineCommentPrefix(): String = "// "
    override fun getBlockCommentPrefix(): String = "/* "
    override fun getBlockCommentSuffix(): String = " */"
    override fun getCommentedBlockCommentPrefix(): String? = null
    override fun getCommentedBlockCommentSuffix(): String? = null
}

// ─── AblBracketMatcher ───────────────────────────────────────────────────────

/**
 * Mise en évidence des parenthèses/crochets appariés pour ABL.
 */
class AblBracketMatcher : PairedBraceMatcher {

    private val PAIRS = arrayOf(
        BracePair(AblTokenTypes.LPAREN, AblTokenTypes.RPAREN, false)
    )

    override fun getPairs(): Array<BracePair> = PAIRS
    override fun isPairedBracesAllowedBeforeType(lbraceType: IElementType, contextType: IElementType?): Boolean = true
    override fun getCodeConstructStart(file: PsiFile, openingBracketOffset: Int): Int = openingBracketOffset
}
