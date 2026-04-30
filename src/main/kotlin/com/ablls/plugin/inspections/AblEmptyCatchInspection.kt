package com.ablls.plugin.inspections

import com.ablls.plugin.core.AblProjectAnalysisService
import com.ablls.plugin.language.AblLanguage
import com.intellij.codeInspection.*
import com.intellij.openapi.components.service
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
                            range
                        )
                    }
                }
            }
        }
}
