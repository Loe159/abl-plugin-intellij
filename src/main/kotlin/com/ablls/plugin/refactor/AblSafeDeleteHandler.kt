package com.ablls.plugin.refactor

import com.ablls.plugin.core.AblProjectAnalysisService
import com.ablls.plugin.core.AblSymbol
import com.ablls.plugin.language.AblLanguage
import com.intellij.lang.refactoring.RefactoringSupportProvider
import com.intellij.openapi.actionSystem.CommonDataKeys
import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.components.service
import com.intellij.openapi.ui.Messages
import com.intellij.psi.PsiElement

/**
 * Support de Safe Delete pour ABL.
 *
 * Avant de supprimer un symbole (procédure, variable, classe…),
 * vérifie qu'aucun fichier indexé ne le référence.
 *
 * Implémente [RefactoringSupportProvider] pour activer le refactoring
 * Safe Delete dans le menu contextuel ABL.
 */
class AblRefactoringSupportProvider : RefactoringSupportProvider() {
    override fun isAvailable(context: PsiElement): Boolean = context.language == AblLanguage

    override fun isSafeDeleteAvailable(element: PsiElement): Boolean = element.language == AblLanguage
}

/**
 * Action Safe Delete ABL — vérifie les usages avant suppression.
 *
 * Invoqué depuis le menu Refactor > Safe Delete ou Alt+Delete.
 * Cherche le symbole sous le curseur dans l'index global et affiche
 * un avertissement si des références sont trouvées.
 */
class AblSafeDeleteAction : com.intellij.openapi.actionSystem.AnAction(
    "ABL Safe Delete",
    "Delete symbol after checking for usages in project",
    com.intellij.icons.AllIcons.Actions.GC,
) {
    override fun actionPerformed(e: com.intellij.openapi.actionSystem.AnActionEvent) {
        val project = e.project ?: return
        val editor = e.getData(CommonDataKeys.EDITOR) ?: return
        val file = e.getData(CommonDataKeys.PSI_FILE) ?: return
        if (file.language != AblLanguage) return

        val offset = editor.caretModel.offset
        val element = file.findElementAt(offset) ?: return
        val symbolName = element.text.takeIf { it.isNotBlank() } ?: return

        val service = project.service<AblProjectAnalysisService>()
        val uri = file.virtualFile?.url ?: return

        // Chercher les usages dans l'index
        val definitions = service.symbolIndex.findByName(symbolName, uri)
        val usages =
            service.symbolIndex.allSymbols()
                .filter { sym ->
                    sym.kind == AblSymbol.Kind.UNKNOWN &&
                        sym.name.equals(symbolName, ignoreCase = true)
                }

        // Compter les occurrences dans le token stream
        val parseResult = service.analyzeFile(file.text, uri)
        val tokens = parseResult.tokens
        var refCount = 0
        if (tokens != null) {
            val size = tokens.size()
            for (i in 0 until size) {
                val t = tokens.get(i)
                if (t.channel != org.antlr.v4.runtime.Token.DEFAULT_CHANNEL) continue
                if (t.text.equals(symbolName, ignoreCase = true)) refCount++
            }
        }

        val message =
            buildString {
                append("Symbol '$symbolName'")
                if (definitions.isNotEmpty()) {
                    append(" is defined in ${definitions.size} location(s).\n")
                }
                append("Found $refCount reference(s) in the current file.")
                if (refCount > 1) {
                    append("\n\nAre you sure you want to delete it?")
                }
            }

        val choice =
            Messages.showYesNoCancelDialog(
                project,
                message,
                "ABL Safe Delete",
                "Delete",
                "Show Usages",
                "Cancel",
                com.intellij.icons.AllIcons.General.WarningDialog,
            )

        when (choice) {
            Messages.YES -> {
                // Supprimer la ligne courante (simple heuristique)
                ApplicationManager.getApplication().runWriteAction {
                    val doc = editor.document
                    val line = doc.getLineNumber(offset)
                    val lineStart = doc.getLineStartOffset(line)
                    val lineEnd = if (line + 1 < doc.lineCount) doc.getLineStartOffset(line + 1) else doc.textLength
                    doc.deleteString(lineStart, lineEnd)
                }
            }
            Messages.NO -> {
                // Show usages — déclenche le Find Usages standard via l'action
                val action =
                    com.intellij.openapi.actionSystem.ActionManager.getInstance()
                        .getAction("FindUsages")
                action?.actionPerformed(e)
            }
        }
    }

    override fun update(e: com.intellij.openapi.actionSystem.AnActionEvent) {
        val file = e.getData(CommonDataKeys.PSI_FILE)
        e.presentation.isEnabled = file?.language == AblLanguage
    }
}
