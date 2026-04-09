package com.ablls.plugin.navigation

import com.ablls.plugin.core.AblProjectAnalysisService
import com.ablls.plugin.language.AblLanguage
import com.ablls.plugin.parser.AblTokenTypes
import com.intellij.lang.cacheBuilder.DefaultWordsScanner
import com.intellij.lang.cacheBuilder.WordsScanner
import com.intellij.lang.findUsages.FindUsagesProvider
import com.intellij.openapi.components.service
import com.intellij.psi.PsiElement
import com.intellij.psi.PsiNamedElement

/**
 * Fournisseur "Find Usages" pour ABL (Alt+F7).
 *
 * Stratégie :
 *   1. Chercher le mot sous le curseur dans le texte source de tous les fichiers indexés.
 *   2. Filtrer par contexte syntaxique (éviter faux positifs dans strings / commentaires).
 *
 * Note : une implémentation complète utiliserait les références JPNode via
 * [AblProjectAnalysisService.analyzeFileSemantic] → [AblSemanticResult.topNode]
 * → walk nodes où [JPNode.getSymbol()] correspond au symbole cible.
 * L'implémentation actuelle repose sur la recherche textuelle dans l'index.
 */
class AblFindUsagesProvider : FindUsagesProvider {

    override fun canFindUsagesFor(psiElement: PsiElement): Boolean {
        if (psiElement.containingFile?.language != AblLanguage) return false
        val type = psiElement.node?.elementType
        return type == AblTokenTypes.KEYWORD ||
               type == AblTokenTypes.KEYWORD_DEF ||
               type == AblTokenTypes.KEYWORD_FLOW ||
               type == AblTokenTypes.IDENTIFIER
    }

    override fun getWordsScanner(): WordsScanner? = null

    override fun getNodeText(element: PsiElement, useFullName: Boolean): String =
        element.text ?: ""

    override fun getDescriptiveName(element: PsiElement): String =
        (element as? PsiNamedElement)?.name ?: element.text ?: ""

    override fun getType(element: PsiElement): String {
        val word = element.text?.trim()?.uppercase() ?: return "symbol"
        val uri  = element.containingFile?.virtualFile?.url ?: return "symbol"
        val service = element.project.service<AblProjectAnalysisService>()
        val symbols = service.symbolIndex.findByName(word, uri)
        return if (symbols.isNotEmpty()) symbols.first().kind.name.lowercase() else "symbol"
    }

    override fun getHelpId(psiElement: PsiElement): String? = null
}
