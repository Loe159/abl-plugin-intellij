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
 * Inspection : FIND / RUN avec NO-ERROR sans vérification
 * de ERROR-STATUS:ERROR / AVAILABLE / RETURN-VALUE dans les instructions suivantes.
 *
 * Pattern dangereux :
 *   FIND Customer WHERE CustNum = 1 NO-ERROR.
 *   // aucune vérification d'erreur — silence total
 *
 * Stratégie : liste plate des statements via queryStateHead().
 * Pour chaque statement avec un nœud NOERROR fils et un type dans TRIGGER_TYPES,
 * on examine les 4 statements suivants à la recherche d'un check d'erreur.
 */
class AblNoErrorWithoutCheckInspection : LocalInspectionTool() {

    override fun getDisplayName()      = "NO-ERROR without subsequent error check"
    override fun getShortName()        = "AblNoErrorWithoutCheck"
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

                val stmts = topNode.queryStateHead()
                stmts.forEachIndexed { idx, stmt ->
                    if (stmt.nodeType !in TRIGGER_TYPES) return@forEachIndexed
                    val noErrorNodes = stmt.query(ABLNodeType.NOERROR)
                    if (noErrorNodes.isEmpty()) return@forEachIndexed

                    // Regarder les 4 statements suivants pour une vérification d'erreur
                    val lookAhead = stmts.subList(idx + 1, minOf(stmts.size, idx + 5))
                    val hasCheck  = lookAhead.any { next ->
                        next.nodeType == ABLNodeType.IF ||
                        next.query(ABLNodeType.ERRORSTATUS).isNotEmpty() ||
                        next.query(ABLNodeType.AVAILABLE).isNotEmpty()   ||
                        next.query(ABLNodeType.RETURNVALUE).isNotEmpty()
                    }
                    if (hasCheck) return@forEachIndexed

                    val noErrorNode = noErrorNodes.first()
                    val range = AblInspectionHelper.toRange(doc, noErrorNode.line, noErrorNode.column, "NO-ERROR".length)
                    holder.registerProblem(
                        file,
                        "NO-ERROR used without subsequent ERROR-STATUS:ERROR, AVAILABLE or RETURN-VALUE check — errors will be silently ignored",
                        ProblemHighlightType.WARNING,
                        range
                    )
                }
            }
        }

    companion object {
        // Statements qui peuvent porter NO-ERROR — source de vérité : ABLNodeType
        private val TRIGGER_TYPES: Set<ABLNodeType> = java.util.EnumSet.of(
            ABLNodeType.FIND, ABLNodeType.RUN,
            ABLNodeType.INPUT, ABLNodeType.OUTPUT
        )
    }
}
