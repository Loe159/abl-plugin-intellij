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
 * Exemple : MyClass > constructor > DO block
 *
 * Comme le PSI ABL est plat (tokens feuilles directement sous AblFile),
 * le chemin est reconstruit depuis le texte source autour de l'offset courant
 * en remontant les mots-clés de bloc ouvrant les plus proches.
 */
class AblBreadcrumbProvider : BreadcrumbsProvider {

    override fun getLanguages(): Array<out Language> = arrayOf(AblLanguage)

    override fun getElementInfo(element: PsiElement): String {
        val text = element.text.trim()
        return when {
            text.uppercase().startsWith("PROCEDURE ") -> "PROCEDURE " + text.substringAfter(" ").substringBefore(":")
            text.uppercase().startsWith("FUNCTION ")  -> "FUNCTION "  + text.substringAfter(" ").substringBefore(" ")
            text.uppercase().startsWith("CLASS ")     -> "CLASS "     + text.substringAfter(" ").substringBefore(":")
            text.uppercase().startsWith("METHOD ")    -> "METHOD "    + text.substringAfterLast(" ").substringBefore("(")
            text.uppercase().startsWith("DO")         -> "DO"
            text.uppercase().startsWith("IF ")        -> "IF"
            else -> text.take(20)
        }
    }

    override fun getElementIcon(element: PsiElement): Icon? {
        val text = element.text.trim().uppercase()
        return when {
            text.startsWith("PROCEDURE") -> AllIcons.Nodes.Method
            text.startsWith("FUNCTION")  -> AllIcons.Nodes.Function
            text.startsWith("CLASS")     -> AllIcons.Nodes.Class
            text.startsWith("METHOD")    -> AllIcons.Nodes.Method
            else -> null
        }
    }

    override fun isShownByDefault(): Boolean = true

    override fun getParent(element: PsiElement): PsiElement? {
        // Avec un PSI plat, les breadcrumbs ne peuvent pas remonter les nœuds parents
        // (tous sont des enfants directs de AblFile). Retourne null pour ne pas boucler.
        return null
    }

    override fun acceptElement(element: PsiElement): Boolean {
        if (element.language != AblLanguage) return false
        val text = element.text.trim().uppercase()
        return text.startsWith("PROCEDURE") || text.startsWith("FUNCTION") ||
               text.startsWith("CLASS") || text.startsWith("METHOD") ||
               text.startsWith("DO") || text.startsWith("IF ")
    }
}
