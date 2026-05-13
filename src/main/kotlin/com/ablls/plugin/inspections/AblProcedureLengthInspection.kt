package com.ablls.plugin.inspections

import com.ablls.plugin.core.AblProjectAnalysisService
import com.ablls.plugin.language.AblLanguage
import com.intellij.codeInspection.*
import com.intellij.openapi.components.service
import com.intellij.psi.PsiDocumentManager
import com.intellij.psi.PsiElementVisitor
import com.intellij.psi.PsiFile
import org.prorefactor.core.ABLNodeType
import org.prorefactor.core.JPNode

/**
 * Inspection : procédure ou fonction dépassant [MAX_LINES] lignes.
 *
 * Les blocs trop longs sont difficiles à tester, relire et maintenir.
 * La longueur est mesurée du mot-clé PROCEDURE/FUNCTION jusqu'au END correspondant
 * en traversant le sous-arbre JPNode pour trouver la ligne maximale.
 *
 * Seuil par défaut : 150 lignes.
 */
class AblProcedureLengthInspection : LocalInspectionTool() {

    override fun getDisplayName()      = "Overly long procedure or function (> $MAX_LINES lines)"
    override fun getShortName()        = "AblProcedureLength"
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

                val routineNodes = topNode.queryStateHead(ABLNodeType.PROCEDURE, ABLNodeType.FUNCTION)

                for (node in routineNodes) {
                    if (node.hasProparseDirective("NOANALYSIS")) continue

                    val startLine = node.line
                    val endLine   = lastLineOf(node)
                    val length    = endLine - startLine + 1

                    if (length > MAX_LINES) {
                        val kind = if (node.nodeType == ABLNodeType.FUNCTION) "Function" else "Procedure"
                        val range = AblInspectionHelper.toRange(doc, startLine, node.column, kind.length)
                        holder.registerProblem(
                            file,
                            "$kind is $length lines long (threshold: $MAX_LINES) — consider splitting into smaller units",
                            ProblemHighlightType.WEAK_WARNING,
                            range
                        )
                    }
                }
            }
        }

    companion object {
        const val MAX_LINES = 150

        /** Retourne la ligne maximale dans le sous-arbre JPNode (1-based). */
        fun lastLineOf(node: JPNode): Int {
            var last = node.line
            var child = node.firstChild
            while (child != null) {
                val childLast = lastLineOf(child)
                if (childLast > last) last = childLast
                child = child.nextSibling
            }
            return last
        }
    }
}
