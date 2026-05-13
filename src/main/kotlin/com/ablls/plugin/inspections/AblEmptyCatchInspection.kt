package com.ablls.plugin.inspections

import com.ablls.plugin.core.AblProjectAnalysisService
import com.ablls.plugin.language.AblLanguage
import com.intellij.codeInspection.*
import com.intellij.openapi.components.service
import com.intellij.openapi.project.Project
import com.intellij.psi.PsiDocumentManager
import com.intellij.psi.PsiElementVisitor
import com.intellij.psi.PsiFile
import org.prorefactor.core.ABLNodeType

/**
 * Inspection : bloc CATCH vide ou ne contenant qu'un RETURN.
 *
 * Pattern dangereux :
 *   CATCH e AS Progress.Lang.Error:
 *   END CATCH.
 *
 * Stratégie : parcours du JPNode tree via queryStateHead(CATCH).
 * Pour chaque CATCH, on inspecte le nœud CODE_BLOCK fils et on compte
 * les statements significatifs via queryStateHead().
 * Grammaire : catchStatement → CATCH … blockColon codeBlock catchEnd
 * — CODE_BLOCK est donc un fils direct du nœud CATCH.
 */
class AblEmptyCatchInspection : LocalInspectionTool() {

    override fun getDisplayName()      = "Empty or return-only CATCH block"
    override fun getShortName()        = "AblEmptyCatch"
    override fun getGroupDisplayName() = "ABL Best Practices"

    override fun buildVisitor(holder: ProblemsHolder, isOnTheFly: Boolean): PsiElementVisitor =
        object : PsiElementVisitor() {
            override fun visitFile(file: PsiFile) {
                if (file.language != AblLanguage) return
                val uri     = file.virtualFile?.url ?: return
                val service = file.project.service<AblProjectAnalysisService>()
                val result  = service.analyzeFile(file.text, uri)
                val topNode = result.topNode ?: return
                val doc     = PsiDocumentManager.getInstance(file.project).getDocument(file) ?: return

                for (catchNode in topNode.queryStateHead(ABLNodeType.CATCH)) {
                    if (catchNode.hasProparseDirective("NOANALYSIS")) continue
                    val codeBlock = catchNode.directChildren.find { it.nodeType == ABLNodeType.CODE_BLOCK }
                        ?: continue

                    val stmts = codeBlock.queryStateHead()
                    val isOnlyReturn = stmts.size == 1 && stmts[0].nodeType == ABLNodeType.RETURN
                    if (stmts.isEmpty() || isOnlyReturn) {
                        val range = AblInspectionHelper.toRange(doc, catchNode.line, catchNode.column, "CATCH".length)
                        holder.registerProblem(
                            file,
                            "Empty CATCH block silently swallows exceptions — add error handling or logging",
                            ProblemHighlightType.WARNING,
                            range,
                            AddCatchLoggingFix(catchNode.line),
                            AddCatchRethrowFix(catchNode.line)
                        )
                    }
                }
            }
        }
}

// ─── Quick fixes ──────────────────────────────────────────────────────────────

/** Insère MESSAGE e:GetMessage(1). dans le bloc CATCH vide. */
private class AddCatchLoggingFix(private val catchLine: Int) : LocalQuickFix {
    override fun getFamilyName() = "Add error logging (MESSAGE e:GetMessage(1))"

    override fun applyFix(project: Project, descriptor: ProblemDescriptor) {
        val file  = descriptor.psiElement as? PsiFile ?: return
        val doc   = PsiDocumentManager.getInstance(project).getDocument(file) ?: return
        insertAfterCatchColon(doc, catchLine, "    MESSAGE e:GetMessage(1) VIEW-AS ALERT-BOX.")
    }
}

/** Insère UNDO, THROW e. dans le bloc CATCH vide (re-throw). */
private class AddCatchRethrowFix(private val catchLine: Int) : LocalQuickFix {
    override fun getFamilyName() = "Re-throw error (UNDO, THROW e.)"

    override fun applyFix(project: Project, descriptor: ProblemDescriptor) {
        val file = descriptor.psiElement as? PsiFile ?: return
        val doc  = PsiDocumentManager.getInstance(project).getDocument(file) ?: return
        insertAfterCatchColon(doc, catchLine, "    UNDO, THROW e.")
    }
}

/** Insère [text] sur une nouvelle ligne après la ligne de début du CATCH (la ligne avec le ':'). */
private fun insertAfterCatchColon(
    doc: com.intellij.openapi.editor.Document,
    catchLine: Int,
    text: String
) {
    val line = (catchLine - 1).coerceIn(0, doc.lineCount - 1)
    val lineEnd = if (line + 1 < doc.lineCount) doc.getLineStartOffset(line + 1) else doc.textLength
    doc.insertString(lineEnd, "$text\n")
}
