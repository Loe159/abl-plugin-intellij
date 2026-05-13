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
 * Inspection : complexité cyclomatique de McCabe élevée.
 *
 * Mesure le nombre de chemins indépendants dans chaque procédure/fonction :
 *   CC = 1 + #branches
 * où les branches sont : IF, ELSE, WHEN, FOR, REPEAT, DO WHILE,
 * CATCH, AND (dans une condition), OR (dans une condition).
 *
 * Seuil : CC > [MAX_CC] → WEAK_WARNING.
 * Différent de la complexité cognitive (AblCognitiveComplexityInspection)
 * qui mesure la lisibilité subjective plutôt que le nombre de chemins.
 */
class AblCyclomaticComplexityInspection : LocalInspectionTool() {

    override fun getDisplayName()      = "High cyclomatic complexity (McCabe, CC > $MAX_CC)"
    override fun getShortName()        = "AblCyclomaticComplexity"
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

                    val cc = computeCyclomaticComplexity(node)
                    if (cc > MAX_CC) {
                        val kind = if (node.nodeType == ABLNodeType.FUNCTION) "Function" else "Procedure"
                        val range = AblInspectionHelper.toRange(doc, node.line, node.column, kind.length)
                        holder.registerProblem(
                            file,
                            "$kind has cyclomatic complexity $cc (threshold: $MAX_CC) — consider breaking it into smaller units",
                            ProblemHighlightType.WEAK_WARNING,
                            range
                        )
                    }
                }
            }
        }

    companion object {
        const val MAX_CC = 10

        // Types de nœuds qui incrémentent la complexité cyclomatique
        private val BRANCH_TYPES: Set<ABLNodeType> = java.util.EnumSet.of(
            ABLNodeType.IF,
            ABLNodeType.ELSE,
            ABLNodeType.WHEN,     // CASE WHEN
            ABLNodeType.FOR,
            ABLNodeType.REPEAT,
            ABLNodeType.CATCH,
            ABLNodeType.AND,
            ABLNodeType.OR
        )

        fun computeCyclomaticComplexity(routineNode: JPNode): Int {
            var cc = 1  // base
            var child = routineNode.firstChild
            while (child != null) {
                cc += countBranchesInSubtree(child)
                child = child.nextSibling
            }
            return cc
        }

        private fun countBranchesInSubtree(node: JPNode): Int {
            var count = if (node.nodeType in BRANCH_TYPES) 1 else 0
            var child = node.firstChild
            while (child != null) {
                count += countBranchesInSubtree(child)
                child = child.nextSibling
            }
            return count
        }
    }
}
