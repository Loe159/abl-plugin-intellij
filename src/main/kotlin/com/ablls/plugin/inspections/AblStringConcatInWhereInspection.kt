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
 * Inspection : concaténation de chaîne (+) dans une clause WHERE.
 *
 * Pattern dangereux :
 *   FOR EACH Customer WHERE Customer.Name = "Mr." + lastName NO-LOCK:
 *
 * La concaténation dans un WHERE force Progress à évaluer côté client
 * au lieu d'utiliser les indexes — impact performance majeur sur grandes tables.
 *
 * Stratégie : parcours du JPNode tree.
 * Pour chaque nœud WHERE, on recherche les nœuds PLUS descendants.
 * WHERE et PLUS sont des ABLNodeTypes précis — pas de faux positifs.
 */
class AblStringConcatInWhereInspection : LocalInspectionTool() {

    override fun getDisplayName()      = "String concatenation in WHERE clause"
    override fun getShortName()        = "AblStringConcatInWhere"
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

                for (whereNode in topNode.query(ABLNodeType.WHERE)) {
                    if (whereNode.getStatement().hasProparseDirective("NOANALYSIS")) continue
                    for (plusNode in whereNode.query(ABLNodeType.PLUS)) {
                        val range = AblInspectionHelper.toRange(doc, plusNode.line, plusNode.column, 1)
                        holder.registerProblem(
                            file,
                            "String concatenation (+) in WHERE clause disables index usage — evaluate expression before the query",
                            ProblemHighlightType.WARNING,
                            range
                        )
                    }
                }
            }
        }
}
