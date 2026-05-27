package com.ablls.plugin.parser

import com.intellij.openapi.command.WriteCommandAction
import com.intellij.psi.PsiDocumentManager
import com.intellij.psi.PsiElement
import com.intellij.psi.PsiNamedElement
import com.intellij.psi.impl.source.tree.LeafPsiElement
import com.intellij.psi.tree.IElementType

/**
 * Élément PSI nommé pour les identifiants ABL.
 *
 * Instancié par [AblAstFactory] à la place du [LeafPsiElement] générique pour
 * les tokens de type [AblTokenTypes.IDENTIFIER].
 *
 * En implémentant [PsiNamedElement] :
 *   - IntelliJ affiche le **RenameDialog natif** (Shift+F6) avec preview des usages.
 *   - [setName] applique le renommage dans le document courant ; les autres fichiers
 *     sont traités par le mécanisme de find-usages + PsiReference (voir
 *     [AblReferenceContributor] / [AblSymbolReference]).
 *
 * Note : [AblRenameHandler] reste enregistré avec une priorité plus haute (il
 * intercepte Shift+F6 en premier). Pour utiliser le RenameDialog natif, désactiver
 * [AblRenameHandler] dans plugin.xml.
 */
class AblNamedLeafElement(type: IElementType, text: CharSequence) :
    LeafPsiElement(type, text), PsiNamedElement {
    override fun getName(): String = this.text

    override fun setName(name: String): PsiElement {
        val doc =
            PsiDocumentManager.getInstance(project).getDocument(containingFile)
                ?: return this
        WriteCommandAction.runWriteCommandAction(project) {
            doc.replaceString(textRange.startOffset, textRange.endOffset, name)
            PsiDocumentManager.getInstance(project).commitDocument(doc)
        }
        return containingFile.findElementAt(textRange.startOffset) ?: this
    }
}
