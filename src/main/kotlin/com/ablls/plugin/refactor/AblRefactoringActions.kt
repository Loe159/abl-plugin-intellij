package com.ablls.plugin.refactor

import com.ablls.plugin.intentions.AblChangeSignatureIntention
import com.ablls.plugin.intentions.AblExtractProcedureIntention
import com.ablls.plugin.intentions.AblInlineVariableIntention
import com.ablls.plugin.intentions.AblIntroduceVariableIntention
import com.ablls.plugin.language.AblLanguage
import com.intellij.openapi.actionSystem.AnAction
import com.intellij.openapi.actionSystem.AnActionEvent
import com.intellij.openapi.actionSystem.CommonDataKeys

/**
 * Actions de refactoring ABL exposées dans le menu Refactor (Ctrl+Alt+Shift+T).
 *
 * Chaque action est un wrapper mince autour de l'IntentionAction correspondante.
 * Apparaît dans :
 *   - Menu Refactor → ABL …
 *   - Pop-up contextuel Ctrl+Alt+Shift+T → Refactor This
 *
 * Note : les IntentionActions sous-jacentes sont déjà disponibles via Alt+Enter.
 * Ces actions complètent l'intégration dans l'écosystème Refactor natif.
 */

class AblExtractProcedureAction : AnAction("Extract ABL PROCEDURE") {
    private val intention = AblExtractProcedureIntention()

    override fun actionPerformed(e: AnActionEvent) {
        val project = e.project ?: return
        val editor  = e.getData(CommonDataKeys.EDITOR) ?: return
        val file    = e.getData(CommonDataKeys.PSI_FILE) ?: return
        if (file.language != AblLanguage) return
        if (!intention.startInWriteAction()) {
            intention.invoke(project, editor, file)
        } else {
            com.intellij.openapi.command.WriteCommandAction.runWriteCommandAction(project) {
                intention.invoke(project, editor, file)
            }
        }
    }

    override fun update(e: AnActionEvent) {
        val editor = e.getData(CommonDataKeys.EDITOR)
        val file   = e.getData(CommonDataKeys.PSI_FILE)
        val project = e.project
        e.presentation.isEnabled =
            project != null && editor != null && file?.language == AblLanguage &&
            intention.isAvailable(project, editor, file)
    }
}

class AblIntroduceVariableAction : AnAction("Introduce ABL Variable") {
    private val intention = AblIntroduceVariableIntention()

    override fun actionPerformed(e: AnActionEvent) {
        val project = e.project ?: return
        val editor  = e.getData(CommonDataKeys.EDITOR) ?: return
        val file    = e.getData(CommonDataKeys.PSI_FILE) ?: return
        if (file.language != AblLanguage) return
        com.intellij.openapi.command.WriteCommandAction.runWriteCommandAction(project) {
            intention.invoke(project, editor, file)
        }
    }

    override fun update(e: AnActionEvent) {
        val editor  = e.getData(CommonDataKeys.EDITOR)
        val file    = e.getData(CommonDataKeys.PSI_FILE)
        val project = e.project
        e.presentation.isEnabled =
            project != null && editor != null && file?.language == AblLanguage &&
            intention.isAvailable(project, editor, file)
    }
}

class AblInlineVariableAction : AnAction("Inline ABL Variable") {
    private val intention = AblInlineVariableIntention()

    override fun actionPerformed(e: AnActionEvent) {
        val project = e.project ?: return
        val editor  = e.getData(CommonDataKeys.EDITOR) ?: return
        val file    = e.getData(CommonDataKeys.PSI_FILE) ?: return
        if (file.language != AblLanguage) return
        com.intellij.openapi.command.WriteCommandAction.runWriteCommandAction(project) {
            intention.invoke(project, editor, file)
        }
    }

    override fun update(e: AnActionEvent) {
        val editor  = e.getData(CommonDataKeys.EDITOR)
        val file    = e.getData(CommonDataKeys.PSI_FILE)
        val project = e.project
        e.presentation.isEnabled =
            project != null && editor != null && file?.language == AblLanguage &&
            intention.isAvailable(project, editor, file)
    }
}

class AblChangeSignatureAction : AnAction("Change ABL Signature") {
    private val intention = AblChangeSignatureIntention()

    override fun actionPerformed(e: AnActionEvent) {
        val project = e.project ?: return
        val editor  = e.getData(CommonDataKeys.EDITOR) ?: return
        val file    = e.getData(CommonDataKeys.PSI_FILE) ?: return
        if (file.language != AblLanguage) return
        com.intellij.openapi.command.WriteCommandAction.runWriteCommandAction(project) {
            intention.invoke(project, editor, file)
        }
    }

    override fun update(e: AnActionEvent) {
        val editor  = e.getData(CommonDataKeys.EDITOR)
        val file    = e.getData(CommonDataKeys.PSI_FILE)
        val project = e.project
        e.presentation.isEnabled =
            project != null && editor != null && file?.language == AblLanguage &&
            intention.isAvailable(project, editor, file)
    }
}
