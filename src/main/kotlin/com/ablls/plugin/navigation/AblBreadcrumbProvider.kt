package com.ablls.plugin.navigation

import com.ablls.plugin.language.AblLanguage
import com.ablls.plugin.parser.AblFile
import com.ablls.plugin.parser.AblTokenTypes
import com.intellij.lang.Language
import com.intellij.psi.PsiElement
import com.intellij.psi.tree.IElementType
import com.intellij.ui.breadcrumbs.BreadcrumbsProvider

/**
 * Breadcrumb navigation for ABL — powered by the structured PSI tree.
 *
 * With composite block nodes (PROCEDURE_BLOCK, DO_BLOCK, …) in the PSI tree,
 * [getParent] is a simple parent-chain walk instead of a text-based sibling scan.
 * [acceptElement] accepts composite block nodes only.
 *
 * Breadcrumb chain example for a cursor inside DO inside PROCEDURE:
 *   PROCEDURE foo > DO
 */
class AblBreadcrumbProvider : BreadcrumbsProvider {
    override fun getLanguages(): Array<Language> = arrayOf(AblLanguage)

    // ─── acceptElement ────────────────────────────────────────────────────────

    override fun acceptElement(element: PsiElement): Boolean = element.node.elementType in AblTokenTypes.BLOCK_TYPES

    // ─── getParent ────────────────────────────────────────────────────────────

    /**
     * Returns the nearest ancestor of [element] that is a block composite node,
     * or null if [element] is at the top level (direct child of AblFile).
     */
    override fun getParent(element: PsiElement): PsiElement? {
        var current = element.parent
        while (current != null) {
            if (current is AblFile) return null
            if (acceptElement(current)) return current
            current = current.parent
        }
        return null
    }

    // ─── getElementInfo ───────────────────────────────────────────────────────

    /**
     * Returns a human-readable label for a breadcrumb element.
     * For named blocks (PROCEDURE/FUNCTION/CLASS/METHOD) includes the identifier name.
     */
    override fun getElementInfo(element: PsiElement): String {
        val type = element.node.elementType
        val keyword = BLOCK_KEYWORDS[type] ?: return element.text.take(30)

        if (type !in AblTokenTypes.NAMED_BLOCK_TYPES) return keyword

        // Name token is the first non-whitespace child after the opening keyword leaf
        val keywordLeaf = element.firstChild ?: return keyword
        var nameCandidate = keywordLeaf.nextSibling
        while (nameCandidate != null && nameCandidate.text.isBlank()) {
            nameCandidate = nameCandidate.nextSibling
        }
        val name =
            nameCandidate?.text?.trim()
                ?.takeIf { it.isNotEmpty() && it[0].isLetter() }
        return if (name != null) "$keyword $name" else keyword
    }

    companion object {
        private val BLOCK_KEYWORDS: Map<IElementType, String> =
            mapOf(
                AblTokenTypes.PROCEDURE_BLOCK to "PROCEDURE",
                AblTokenTypes.FUNCTION_BLOCK to "FUNCTION",
                AblTokenTypes.CLASS_BLOCK to "CLASS",
                AblTokenTypes.INTERFACE_BLOCK to "INTERFACE",
                AblTokenTypes.METHOD_BLOCK to "METHOD",
                AblTokenTypes.CONSTRUCTOR_BLOCK to "CONSTRUCTOR",
                AblTokenTypes.DESTRUCTOR_BLOCK to "DESTRUCTOR",
                AblTokenTypes.DO_BLOCK to "DO",
                AblTokenTypes.REPEAT_BLOCK to "REPEAT",
                AblTokenTypes.FOR_BLOCK to "FOR",
                AblTokenTypes.CATCH_BLOCK to "CATCH",
                AblTokenTypes.FINALLY_BLOCK to "FINALLY",
                AblTokenTypes.CASE_BLOCK to "CASE",
            )
    }
}
