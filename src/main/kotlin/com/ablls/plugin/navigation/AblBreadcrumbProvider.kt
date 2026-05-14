package com.ablls.plugin.navigation

import com.ablls.plugin.language.AblLanguage
import com.intellij.lang.Language
import com.intellij.ui.breadcrumbs.BreadcrumbsProvider
import com.intellij.psi.PsiElement
import javax.swing.Icon
import com.intellij.icons.AllIcons

/**
 * Breadcrumb provider ABL — affiche le chemin contextuel en haut de l'éditeur.
 *
 * Exemple : CLASS Foo > METHOD bar > DO
 *
 * Comme le PSI ABL est plat (tokens feuilles directement sous AblFile),
 * [getParent] reconstruit le chemin en scannant les siblings avant l'élément
 * et en simulant une stack de blocs ouvrants/fermants.
 *
 * Précision : "END PROCEDURE" est correctement traité comme fermeture, pas comme
 * un nouveau bloc PROCEDURE — via tracking du token précédent.
 */
class AblBreadcrumbProvider : BreadcrumbsProvider {

    companion object {
        private val BLOCK_OPENERS = setOf("PROCEDURE", "FUNCTION", "CLASS", "METHOD", "DO", "REPEAT")
        private val NAMED_OPENERS = setOf("PROCEDURE", "FUNCTION", "CLASS", "METHOD")
    }

    override fun getLanguages(): Array<out Language> = arrayOf(AblLanguage)

    override fun getElementInfo(element: PsiElement): String {
        val upper = element.text.trim().uppercase()
        return if (upper in NAMED_OPENERS) {
            val nameTok = nextRealSibling(element)
            val name = nameTok?.text?.trim() ?: ""
            if (name.isNotEmpty() && name[0].isLetter()) "$upper $name" else upper
        } else {
            upper
        }
    }

    override fun getElementIcon(element: PsiElement): Icon? = when (element.text.trim().uppercase()) {
        "PROCEDURE" -> AllIcons.Nodes.Method
        "FUNCTION"  -> AllIcons.Nodes.Function
        "CLASS"     -> AllIcons.Nodes.Class
        "METHOD"    -> AllIcons.Nodes.Method
        else        -> null
    }

    override fun isShownByDefault(): Boolean = true

    override fun acceptElement(element: PsiElement): Boolean {
        if (element.language != AblLanguage) return false
        return element.text.trim().uppercase() in BLOCK_OPENERS
    }

    /**
     * Scan siblings before [element] to find the nearest enclosing block opener.
     *
     * Simulates a block stack: block keywords push, END pops.
     * prevUpper tracking ensures "END PROCEDURE/CLASS/..." qualifiers are not re-pushed.
     */
    override fun getParent(element: PsiElement): PsiElement? {
        val file = element.containingFile ?: return null
        val elementOffset = element.textOffset
        val stack = ArrayDeque<PsiElement>()
        var prevUpper = ""
        var sibling = file.firstChild

        while (sibling != null && sibling.textOffset < elementOffset) {
            val text = sibling.text?.trim() ?: ""
            if (text.isNotEmpty()) {
                val upper = text.uppercase()
                when {
                    upper == "END" -> {
                        if (stack.isNotEmpty()) stack.removeLast()
                        prevUpper = "END"
                    }
                    upper in BLOCK_OPENERS && prevUpper != "END" -> {
                        stack.addLast(sibling)
                        prevUpper = upper
                    }
                    else -> prevUpper = upper
                }
            }
            sibling = sibling.nextSibling
        }

        return stack.lastOrNull()
    }

    private fun nextRealSibling(element: PsiElement): PsiElement? {
        var s = element.nextSibling
        while (s != null && s.text.isBlank()) s = s.nextSibling
        return s
    }
}
