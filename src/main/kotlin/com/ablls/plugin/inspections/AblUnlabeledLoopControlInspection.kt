package com.ablls.plugin.inspections

import com.ablls.plugin.core.AblProjectAnalysisService
import com.ablls.plugin.language.AblLanguage
import com.intellij.codeInspection.LocalInspectionTool
import com.intellij.codeInspection.ProblemHighlightType
import com.intellij.codeInspection.ProblemsHolder
import com.intellij.openapi.components.service
import com.intellij.psi.PsiDocumentManager
import com.intellij.psi.PsiElementVisitor
import com.intellij.psi.PsiFile
import org.prorefactor.core.ABLNodeType
import org.prorefactor.core.JPNode

/**
 * Inspection : LEAVE ou NEXT sans étiquette dans une boucle imbriquée.
 *
 * En ABL, `LEAVE.` et `NEXT.` sans étiquette ciblent la boucle la plus proche.
 * Dans des boucles imbriquées, ce comportement peut être involontaire.
 * L'étiquette explicite (`LEAVE myBlock.`) est toujours préférable pour la clarté.
 *
 * Seuls les LEAVE/NEXT dans une structure avec AU MOINS UNE boucle parente
 * supplémentaire sont signalés (les boucles simples sont OK sans étiquette).
 */
class AblUnlabeledLoopControlInspection : LocalInspectionTool() {
    override fun getDisplayName() = "LEAVE/NEXT without label in nested loop"

    override fun getShortName() = "AblUnlabeledLoopControl"

    override fun getGroupDisplayName() = "ABL Best Practices"

    override fun buildVisitor(
        holder: ProblemsHolder,
        isOnTheFly: Boolean,
    ): PsiElementVisitor =
        object : PsiElementVisitor() {
            override fun visitFile(file: PsiFile) {
                if (file.language != AblLanguage) return
                val uri = file.virtualFile?.url ?: return
                val service = file.project.service<AblProjectAnalysisService>()
                val result = service.analyzeFile(file.text, uri)
                val topNode = result.topNode ?: return
                val doc = PsiDocumentManager.getInstance(file.project).getDocument(file) ?: return

                // Trouver tous les LEAVE et NEXT
                for (node in topNode.query(ABLNodeType.LEAVE, ABLNodeType.NEXT)) {
                    if (node.getStatement().hasProparseDirective("NOANALYSIS")) continue

                    // Vérifier si le LEAVE/NEXT porte une étiquette.
                    // Dans le JPNode tree, le label est le firstChild du nœud LEAVE/NEXT
                    // (ex : LEAVE outerLoop. → LEAVE[ID "outerLoop"]).
                    val firstChild = node.firstChild
                    val hasLabel =
                        firstChild != null &&
                            firstChild.nodeType != ABLNodeType.PERIOD &&
                            firstChild.text?.let { !it.isBlank() && !it.equals(".") } == true

                    if (hasLabel) continue // étiquette présente, pas de problème

                    // Compter les boucles parentes
                    val loopDepth = countParentLoops(node)
                    if (loopDepth < 2) continue // boucle simple, OK sans étiquette

                    val keyword = node.text ?: node.nodeType.name
                    val range = AblInspectionHelper.toRange(doc, node.line, node.column, keyword.length)
                    holder.registerProblem(
                        file,
                        "$keyword without label in nested loop — add a block label to make the target loop explicit",
                        ProblemHighlightType.WARNING,
                        range,
                    )
                }
            }
        }

    companion object {
        private val LOOP_TYPES: Set<ABLNodeType> =
            java.util.EnumSet.of(
                ABLNodeType.DO,
                ABLNodeType.FOR,
                ABLNodeType.REPEAT,
            )

        /** Compte le nombre de nœuds LOOP ancêtres directs dans l'arbre JPNode. */
        private fun countParentLoops(node: JPNode): Int {
            var count = 0
            var current = node.parent
            while (current != null) {
                if (current.nodeType in LOOP_TYPES) count++
                current = current.parent
            }
            return count
        }
    }
}
