package com.ablls.plugin.navigation

import com.ablls.plugin.core.AblProjectAnalysisService
import com.ablls.plugin.language.AblLanguage
import com.ablls.plugin.parser.AblLexerAdapter
import com.ablls.plugin.parser.AblTokenTypes
import com.intellij.lang.cacheBuilder.DefaultWordsScanner
import com.intellij.lang.cacheBuilder.WordsScanner
import com.intellij.lang.findUsages.FindUsagesProvider
import com.intellij.openapi.components.service
import com.intellij.psi.PsiDocumentManager
import com.intellij.psi.PsiElement
import com.intellij.psi.PsiNamedElement
import com.intellij.psi.tree.TokenSet

/**
 * Fournisseur "Find Usages" pour ABL (Alt+F7).
 *
 * IntelliJ trouve les usages via les [com.intellij.psi.PsiReference] ou, à défaut, par
 * recherche textuelle. Ce projet n'implément pas PsiReference — IntelliJ utilise donc
 * le fallback textuel, guidé par [getWordsScanner] pour filtrer correctement les tokens ABL.
 *
 * [getWordsScanner] retourne un [DefaultWordsScanner] basé sur [AblLexerAdapter] : les
 * occurrences dans les commentaires et les chaînes sont exclues de l'index de mots.
 * [getType] utilise le scope sémantique si disponible pour retourner le kind précis.
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

    override fun getWordsScanner(): WordsScanner =
        DefaultWordsScanner(
            AblLexerAdapter(),
            TokenSet.create(AblTokenTypes.IDENTIFIER),
            TokenSet.create(AblTokenTypes.BLOCK_COMMENT, AblTokenTypes.LINE_COMMENT),
            TokenSet.create(AblTokenTypes.STRING),
        )

    override fun getNodeText(
        element: PsiElement,
        useFullName: Boolean,
    ): String = element.text ?: ""

    override fun getDescriptiveName(element: PsiElement): String {
        return (element as? PsiNamedElement)?.name ?: element.text ?: ""
    }

    override fun getType(element: PsiElement): String {
        val word = element.text?.trim() ?: return "symbol"
        if (word.isBlank()) return "symbol"
        val uri = element.containingFile?.virtualFile?.url ?: return "symbol"
        val service = element.project.service<AblProjectAnalysisService>()

        // Tentative sémantique : kind précis via le scope résolu
        val rootScope = service.getSemanticResult(uri)?.rootScope
        if (rootScope != null) {
            val doc =
                PsiDocumentManager.getInstance(element.project)
                    .getDocument(element.containingFile ?: return "symbol")
            if (doc != null) {
                val cursorLine = doc.getLineNumber(element.textOffset) + 1 // proparse 1-based
                for (v in runCatching { rootScope.variables }.getOrNull() ?: emptyList()) {
                    if (v.name.equals(word, ignoreCase = true)) {
                        val defLine = runCatching { v.getDefineNode()?.token?.line ?: 0 }.getOrElse { 0 }
                        if (defLine in 1..cursorLine) {
                            return if (v.javaClass.simpleName == "Parameter") "parameter" else "variable"
                        }
                    }
                }
                for (r in runCatching { rootScope.routines }.getOrNull() ?: emptyList()) {
                    if (r.name.equals(word, ignoreCase = true)) {
                        return runCatching { r.ideSignature }.getOrNull()
                            ?.let { sig -> if (sig.contains("FUNCTION")) "function" else "procedure" }
                            ?: "procedure"
                    }
                }
                for (child in runCatching { rootScope.childScopes }.getOrNull() ?: emptyList()) {
                    for (v in runCatching { child.variables }.getOrNull() ?: emptyList()) {
                        if (v.name.equals(word, ignoreCase = true)) {
                            val defLine = runCatching { v.getDefineNode()?.token?.line ?: 0 }.getOrElse { 0 }
                            if (defLine in 1..cursorLine) {
                                return if (v.javaClass.simpleName == "Parameter") "parameter" else "variable"
                            }
                        }
                    }
                }
            }
        }

        // Fallback : index textuel
        val symbols = service.symbolIndex.findByName(word, uri)
        return if (symbols.isNotEmpty()) symbols.first().kind.name.lowercase() else "symbol"
    }

    override fun getHelpId(psiElement: PsiElement): String? = null
}
