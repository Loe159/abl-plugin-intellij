package com.ablls.plugin.inspections

import com.ablls.plugin.core.AblProjectAnalysisService
import com.ablls.plugin.language.AblLanguage
import com.intellij.codeInspection.*
import com.intellij.openapi.components.service
import com.intellij.openapi.project.Project
import com.intellij.psi.PsiDocumentManager
import com.intellij.psi.PsiElement
import com.intellij.psi.PsiElementVisitor
import com.intellij.psi.PsiFile

/**
 * Inspection : opérateurs de comparaison style Fortran (EQ, NE, GT, LT, GE, LE)
 * au lieu des opérateurs modernes (=, <>, >, <, >=, <=).
 *
 * Les opérateurs Fortran sont dépréciés depuis OpenEdge 10.2B et seront supprimés.
 *
 * Stratégie : scan du TokenStream proparse (plus robuste que le visitor ANTLR4).
 */
class AblFortranOperatorsInspection : LocalInspectionTool() {

    override fun getDisplayName()      = "Fortran-style comparison operator"
    override fun getShortName()        = "AblFortranOperators"
    override fun getGroupDisplayName() = "ABL Best Practices"

    override fun buildVisitor(holder: ProblemsHolder, isOnTheFly: Boolean): PsiElementVisitor =
        object : PsiElementVisitor() {
            override fun visitFile(file: PsiFile) {
                if (file.language != AblLanguage) return
                val uri     = file.virtualFile?.url ?: return
                val service = file.project.service<AblProjectAnalysisService>()
                val result  = service.analyzeFile(file.text, uri)
                val tokens  = result.tokens ?: return
                val doc     = PsiDocumentManager.getInstance(file.project).getDocument(file) ?: return

                val size = tokens.size()
                for (i in 0 until size) {
                    val t    = tokens.get(i)
                    val text = t.text?.lowercase() ?: continue
                    if (text !in FORTRAN_OPS) continue
                    if (t.line <= 0) continue

                    val modern = MODERN_MAP[text] ?: continue
                    val range  = AblInspectionHelper.toRange(doc, t.line, t.charPositionInLine, text.length)
                    holder.registerProblem(file, "Deprecated Fortran-style operator '$text' — use '$modern' instead", ProblemHighlightType.WARNING, range,
                        ReplaceFortranOperatorFix(text, modern, range.startOffset, range.endOffset)
                    )
                }
            }
        }

    companion object {
        private val FORTRAN_OPS = setOf("eq", "ne", "gt", "lt", "ge", "le")
        private val MODERN_MAP  = mapOf("eq" to "=", "ne" to "<>", "gt" to ">",
                                        "lt" to "<", "ge" to ">=", "le" to "<=")
    }

    private class ReplaceFortranOperatorFix(
        private val old: String,
        private val modern: String,
        private val startOffset: Int,
        private val endOffset: Int
    ) : LocalQuickFix {
        override fun getFamilyName() = "Replace '$old' with '$modern'"
        override fun applyFix(project: Project, descriptor: ProblemDescriptor) {
            val doc = descriptor.psiElement.containingFile?.viewProvider?.document ?: return
            if (endOffset <= doc.textLength) {
                doc.replaceString(startOffset, endOffset, modern)
            }
        }
    }
}
