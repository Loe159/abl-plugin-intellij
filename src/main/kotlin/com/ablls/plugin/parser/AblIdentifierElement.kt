package com.ablls.plugin.parser

import com.ablls.plugin.core.AblProjectAnalysisService
import com.ablls.plugin.language.AblLanguage
import com.intellij.openapi.components.service
import com.intellij.openapi.vfs.VirtualFileManager
import com.intellij.patterns.PlatformPatterns
import com.intellij.psi.PsiDocumentManager
import com.intellij.psi.PsiElement
import com.intellij.psi.PsiManager
import com.intellij.psi.PsiReference
import com.intellij.psi.PsiReferenceBase
import com.intellij.psi.PsiReferenceContributor
import com.intellij.psi.PsiReferenceProvider
import com.intellij.psi.PsiReferenceRegistrar
import com.intellij.psi.impl.source.tree.LeafPsiElement
import com.intellij.util.ProcessingContext
import org.prorefactor.core.JPNode
import org.prorefactor.treeparser.TreeParserSymbolScope

/**
 * Contributeur de références PSI pour les identifiants ABL.
 *
 * Enregistre [AblSymbolReferenceProvider] sur tous les tokens [AblTokenTypes.IDENTIFIER]
 * sans changer leur classe PSI (pas d'ILeafElementType nécessaire).
 *
 * Effets activés par ce contributor :
 *   - **Find Usages sémantique** (Alt+F7) : IntelliJ appelle [AblSymbolReference.isReferenceTo]
 *     pour filtrer les occurrences textuelles → seules les vraies références au même
 *     symbole sont retenues. Les homonymes dans d'autres scopes sont écartés.
 *   - **Ctrl+B / Go to Declaration** : améliore la résolution quand le scope RSSW
 *     est disponible (cohérence avec AblGotoDeclarationHandler).
 *
 * Note : [com.ablls.plugin.refactor.AblRenameHandler] reste enregistré et garde la
 * priorité pour Shift+F6. La PsiReference est utilisée par le mécanisme de find usages,
 * pas par le handler de rename.
 */
class AblReferenceContributor : PsiReferenceContributor() {
    override fun registerReferenceProviders(registrar: PsiReferenceRegistrar) {
        registrar.registerReferenceProvider(
            PlatformPatterns.psiElement(LeafPsiElement::class.java)
                .withElementType(AblTokenTypes.IDENTIFIER)
                .withLanguage(AblLanguage),
            AblSymbolReferenceProvider(),
            PsiReferenceRegistrar.LOWER_PRIORITY,
        )
    }
}

// ─── Provider ─────────────────────────────────────────────────────────────────

private class AblSymbolReferenceProvider : PsiReferenceProvider() {
    override fun getReferencesByElement(
        element: PsiElement,
        context: ProcessingContext,
    ): Array<PsiReference> {
        val text = element.text?.trim() ?: return PsiReference.EMPTY_ARRAY
        if (text.length < 2) return PsiReference.EMPTY_ARRAY
        return arrayOf(AblSymbolReference(element))
    }

    override fun acceptsTarget(target: PsiElement): Boolean = true
}

// ─── PsiReference sémantique ──────────────────────────────────────────────────

/**
 * Référence PSI d'un identifiant ABL vers sa déclaration.
 *
 * [resolve] utilise le [TreeParserSymbolScope] RSSW (analyse sémantique complète) avec
 * fallback sur l'[com.ablls.plugin.core.AblSymbolIndex] (analyse syntaxique).
 *
 * [isReferenceTo] hérite de [PsiReferenceBase] : `resolve() manager.areElementsEquivalent target`.
 * Cela rend Find Usages sémantique sans changer le lexer ni le PSI tree.
 */
class AblSymbolReference(element: PsiElement) :
    PsiReferenceBase<PsiElement>(element, com.intellij.openapi.util.TextRange(0, element.textLength)) {
    override fun resolve(): PsiElement? {
        val word = myElement.text?.trim() ?: return null
        val file = myElement.containingFile ?: return null
        val uri = file.virtualFile?.url ?: return null
        val project = myElement.project
        val service = project.service<AblProjectAnalysisService>()
        val doc = PsiDocumentManager.getInstance(project).getDocument(file) ?: return null

        // ── Résolution sémantique via TreeParserSymbolScope ───────────────────
        val rootScope = service.getSemanticResult(uri)?.rootScope
        if (rootScope != null) {
            val cursorLine = doc.getLineNumber(myElement.textOffset) + 1 // proparse 1-based
            val defNode = findNearestDefinition(rootScope, word, cursorLine)
            if (defNode?.token != null) {
                val defLine = (defNode.token.line - 1).coerceIn(0, doc.lineCount - 1)
                val defCol = defNode.token.charPositionInLine
                val defOffset = (doc.getLineStartOffset(defLine) + defCol).coerceAtMost(doc.textLength)
                val target = file.findElementAt(defOffset)
                if (target != null && target.text?.equals(word, ignoreCase = true) == true) {
                    return target
                }
            }
        }

        // ── Fallback : index de symboles ──────────────────────────────────────
        val syms = service.symbolIndex.findByName(word, uri)
        if (syms.isEmpty()) return null
        val sym = syms.first()
        val targetUri = sym.uri ?: return null
        val vf = VirtualFileManager.getInstance().findFileByUrl(targetUri) ?: return null
        val targetFile = PsiManager.getInstance(project).findFile(vf) ?: return null
        val targetDoc = PsiDocumentManager.getInstance(project).getDocument(targetFile) ?: return null
        val line = (sym.definitionRange?.startLine ?: 0).coerceIn(0, targetDoc.lineCount - 1)
        val col = sym.definitionRange?.startCol ?: 0
        val offset = (targetDoc.getLineStartOffset(line) + col).coerceAtMost(targetDoc.textLength)
        return targetFile.findElementAt(offset)
    }

    override fun getVariants(): Array<Any> = emptyArray()

    /**
     * Appliqué par IntelliJ sur chaque référence lors d'un rename en masse
     * (natif Shift+F6 via RenameProcessor).
     * Remplace le texte du token par [newElementName] dans son document.
     */
    override fun handleElementRename(newElementName: String): com.intellij.psi.PsiElement {
        val el = myElement
        val doc =
            com.intellij.psi.PsiDocumentManager.getInstance(el.project)
                .getDocument(el.containingFile) ?: return el
        com.intellij.openapi.command.WriteCommandAction.runWriteCommandAction(el.project) {
            doc.replaceString(el.textRange.startOffset, el.textRange.endOffset, newElementName)
            com.intellij.psi.PsiDocumentManager.getInstance(el.project).commitDocument(doc)
        }
        return el.containingFile.findElementAt(el.textRange.startOffset) ?: el
    }

    // ─── Utilitaire scope ─────────────────────────────────────────────────────

    private fun findNearestDefinition(
        scope: TreeParserSymbolScope,
        word: String,
        cursorLine: Int,
    ): JPNode? {
        var best: JPNode? = null
        var bestLine = 0

        fun checkNode(node: JPNode?) {
            val line = node?.token?.line ?: return
            if (line in 1..cursorLine && line > bestLine) {
                best = node
                bestLine = line
            }
        }

        for (v in runCatching { scope.variables }.getOrNull() ?: emptyList()) {
            if (v.name.equals(word, ignoreCase = true)) {
                checkNode(runCatching { v.getDefineNode() }.getOrNull())
            }
        }
        for (r in runCatching { scope.routines }.getOrNull() ?: emptyList()) {
            if (r.name.equals(word, ignoreCase = true)) {
                checkNode(runCatching { r.getDefineNode() }.getOrNull())
            }
        }
        for (child in runCatching { scope.childScopes }.getOrNull() ?: emptyList()) {
            val childBest = findNearestDefinition(child, word, cursorLine)
            val childLine = childBest?.token?.line ?: 0
            if (childLine > bestLine) {
                best = childBest
                bestLine = childLine
            }
        }
        return best
    }
}
