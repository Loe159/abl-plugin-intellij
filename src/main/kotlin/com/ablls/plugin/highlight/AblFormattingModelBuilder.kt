package com.ablls.plugin.highlight

import com.ablls.plugin.language.AblLanguage
import com.ablls.plugin.parser.AblTokenTypes
import com.intellij.formatting.*
import com.intellij.lang.ASTNode
import com.intellij.openapi.util.TextRange
import com.intellij.psi.PsiFile
import com.intellij.psi.formatter.common.AbstractBlock

/**
 * Formatter basique pour ABL.
 *
 * Gère l'indentation des blocs DO/END, PROCEDURE/END, etc.
 * Utilise un modèle de formatage simple basé sur les tokens :
 *   - Les tokens dans un bloc DO/END sont indentés d'un niveau
 *   - Les END correspondent au même niveau que le DO ouvrant
 *
 * Note : Le formatter complet (espaces, casse des mots-clés) nécessiterait
 * un visitor plus sophistiqué. Cette implémentation couvre l'indentation.
 */
class AblFormattingModelBuilder : FormattingModelBuilder {

    override fun createModel(formattingContext: FormattingContext): FormattingModel {
        val settings = formattingContext.codeStyleSettings
        val psiFile  = formattingContext.psiElement.containingFile
        val root     = psiFile.node

        return FormattingModelProvider.createFormattingModelForPsiFile(
            psiFile,
            AblBlock(root, settings),
            settings
        )
    }
}

// ─── Block ABL (nœud de base du formatter) ────────────────────────────────────

private class AblBlock(
    private val node: ASTNode,
    private val settings: com.intellij.psi.codeStyle.CodeStyleSettings
) : AbstractBlock(node, Wrap.createWrap(WrapType.NONE, false), Alignment.createAlignment()) {

    override fun buildChildren(): List<Block> {
        val children = mutableListOf<Block>()
        var child = node.firstChildNode
        while (child != null) {
            if (child.elementType != AblTokenTypes.WHITE_SPACE) {
                children.add(AblBlock(child, settings))
            }
            child = child.treeNext
        }
        return children
    }

    override fun getSpacing(child1: Block?, child2: Block): Spacing? = null

    override fun isLeaf(): Boolean = node.firstChildNode == null

    override fun getIndent(): Indent? {
        val parent = node.treeParent ?: return Indent.getNoneIndent()
        val type   = node.elementType
        val parentType = parent.elementType

        // Les tokens entre DO: et END obtiennent une indentation
        if (parentType == AblTokenTypes.BLOCK_COMMENT || type == AblTokenTypes.BLOCK_COMMENT) {
            return Indent.getNoneIndent()
        }

        return when (type) {
            AblTokenTypes.KEYWORD -> {
                val text = node.text.uppercase()
                when {
                    text == "END" -> Indent.getNoneIndent()
                    else -> Indent.getNormalIndent()
                }
            }
            else -> Indent.getNormalIndent()
        }
    }

    override fun getChildIndent(): Indent? {
        val text = node.text.uppercase().trim()
        return when {
            text.endsWith(":") && !text.startsWith("//") && !text.startsWith("/*") ->
                Indent.getNormalIndent()
            else -> null
        }
    }
}
