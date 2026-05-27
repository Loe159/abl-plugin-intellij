package com.ablls.plugin.inspections

import com.ablls.plugin.core.AblProjectAnalysisService
import com.ablls.plugin.language.AblLanguage
import com.intellij.codeInspection.LocalInspectionTool
import com.intellij.codeInspection.LocalQuickFix
import com.intellij.codeInspection.ProblemDescriptor
import com.intellij.codeInspection.ProblemHighlightType
import com.intellij.codeInspection.ProblemsHolder
import com.intellij.openapi.components.service
import com.intellij.openapi.project.Project
import com.intellij.psi.PsiDocumentManager
import com.intellij.psi.PsiElementVisitor
import com.intellij.psi.PsiFile
import org.prorefactor.core.ABLNodeType

/**
 * Inspection : FIND FIRST / FIND LAST sans NO-ERROR.
 *
 * Un FIND FIRST ou FIND LAST sans NO-ERROR lève une erreur fatale si aucun
 * enregistrement ne correspond. Le code defensif correct est :
 *
 *   FIND FIRST Customer WHERE CustNum = 1 NO-ERROR.
 *   IF AVAILABLE Customer THEN ...
 *
 * Complémentaire à [AblFindNoLockInspection] (qui vérifie le mode de verrou)
 * et à [AblNoErrorWithoutCheckInspection] (qui vérifie que NO-ERROR est suivi
 * d'une vérification d'erreur).
 */
class AblFindFirstNoErrorInspection : LocalInspectionTool() {
    override fun getDisplayName() = "FIND FIRST/LAST without NO-ERROR"

    override fun getShortName() = "AblFindFirstNoError"

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

                for (findNode in topNode.queryStateHead(ABLNodeType.FIND)) {
                    if (findNode.hasProparseDirective("NOANALYSIS")) continue

                    // Uniquement FIND FIRST et FIND LAST (FIND EACH est itératif, sans risque)
                    val hasFirstOrLast = findNode.query(ABLNodeType.FIRST, ABLNodeType.LAST).isNotEmpty()
                    if (!hasFirstOrLast) continue

                    // Si NO-ERROR est présent, AblNoErrorWithoutCheckInspection prend le relais
                    val hasNoError = findNode.query(ABLNodeType.NOERROR).isNotEmpty()
                    if (hasNoError) continue

                    val range = AblInspectionHelper.toRange(doc, findNode.line, findNode.column, "FIND".length)
                    holder.registerProblem(
                        file,
                        "FIND FIRST/LAST without NO-ERROR throws a fatal error when no record is found — add NO-ERROR and check AVAILABLE",
                        ProblemHighlightType.WARNING,
                        range,
                        AddNoErrorFix(range.startOffset),
                    )
                }
            }
        }

    private class AddNoErrorFix(private val findOffset: Int) : LocalQuickFix {
        override fun getFamilyName() = "Add NO-ERROR"

        override fun applyFix(
            project: Project,
            descriptor: ProblemDescriptor,
        ) {
            val file = descriptor.psiElement as? PsiFile ?: return
            val doc = PsiDocumentManager.getInstance(project).getDocument(file) ?: return
            val text = doc.charsSequence
            var i = findOffset
            while (i < text.length) {
                val ch = text[i]
                if (ch == '.' && (i + 1 >= text.length || text[i + 1].isWhitespace() || text[i + 1] == '/')) {
                    doc.insertString(i, " NO-ERROR")
                    break
                }
                i++
            }
        }
    }
}
