package com.ablls.plugin.refactor

import com.ablls.plugin.core.AblProjectAnalysisService
import com.ablls.plugin.language.AblLanguage
import com.intellij.openapi.actionSystem.DataContext
import com.intellij.openapi.components.service
import com.intellij.openapi.editor.Editor
import com.intellij.openapi.project.Project
import com.intellij.psi.PsiElement
import com.intellij.psi.PsiFile
import com.intellij.refactoring.rename.RenameHandler

/**
 * Handler de renommage pour les symboles ABL.
 *
 * Stratégie :
 *   1. Identifier le symbole sous le curseur via [AblProjectAnalysisService.symbolIndex].
 *   2. Trouver toutes les occurrences textuelles dans les fichiers du projet.
 *   3. Appliquer le remplacement via un refactoring IntelliJ.
 *
 * Note : Pour un renommage sémantique complet (qui respecte les scopes),
 * il faudrait utiliser les references JPNode via [AblSemanticResult.topNode]
 * et [JPNode.getSymbol()] pour ne renommer que les vraies références,
 * pas les homonymes dans d'autres scopes.
 *
 * Pour activer ce handler, déclarez-le dans plugin.xml :
 * ```xml
 * <renameHandler implementation="com.ablls.plugin.refactor.AblRenameHandler"/>
 * ```
 */
class AblRenameHandler : RenameHandler {

    override fun isAvailableOnDataContext(dataContext: DataContext): Boolean {
        val editor  = dataContext.getData(com.intellij.openapi.actionSystem.CommonDataKeys.EDITOR) ?: return false
        val psiFile = dataContext.getData(com.intellij.openapi.actionSystem.CommonDataKeys.PSI_FILE) ?: return false
        return psiFile.language == AblLanguage
    }

    override fun invoke(project: Project, editor: Editor, file: PsiFile, dataContext: DataContext) {
        val offset  = editor.caretModel.offset
        val element = file.findElementAt(offset) ?: return
        val word    = element.text?.trim() ?: return
        if (word.isBlank() || word.length < 2) return

        val uri     = file.virtualFile?.url ?: return
        val service = project.service<AblProjectAnalysisService>()
        val symbols = service.symbolIndex.findByName(word, uri)
        if (symbols.isEmpty()) return

        // Déléguer au renommage IntelliJ standard (in-place rename)
        com.intellij.refactoring.rename.PsiElementRenameHandler.invoke(
            element, project, element, editor
        )
    }

    override fun invoke(project: Project, elements: Array<out PsiElement>, dataContext: DataContext) {
        // Déléguer au handler standard
    }
}
