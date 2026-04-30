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
 * Inspection : opérateurs de comparaison style Fortran (EQ, NE, GT, LT, GE, LE)
 * au lieu des opérateurs modernes (=, <>, >, <, >=, <=).
 *
 * Les opérateurs Fortran sont dépréciés depuis OpenEdge 10.2B.
 *
 * Stratégie : parcours du JPNode tree via query().
 * Les 6 opérateurs Fortran ont chacun leur propre ABLNodeType KEYWORD,
 * distincts des opérateurs SYMBOL modernes (EQUAL, GTHAN symbol ≠ EQ/GE/LE keyword).
 * query() ne remonte donc jamais les opérateurs modernes.
 *
 * Note ABLNodeType : GT → GTHAN, LT → LTHAN (noms issus de la grammaire proparse).
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
                val topNode = result.topNode ?: return
                val doc     = PsiDocumentManager.getInstance(file.project).getDocument(file) ?: return

                for (node in topNode.query(ABLNodeType.EQ, ABLNodeType.NE,
                                           ABLNodeType.GTHAN, ABLNodeType.LTHAN,
                                           ABLNodeType.GE, ABLNodeType.LE)) {
                    val old    = FORTRAN_TEXT[node.nodeType] ?: continue
                    val modern = MODERN_MAP[node.nodeType]   ?: continue
                    val range  = AblInspectionHelper.toRange(doc, node.line, node.column, old.length)
                    holder.registerProblem(
                        file,
                        "Deprecated Fortran-style operator '$old' — use '$modern' instead",
                        ProblemHighlightType.WARNING,
                        range,
                        ReplaceFortranOperatorFix(old, modern, range.startOffset, range.endOffset)
                    )
                }
            }
        }

    companion object {
        // Texte canonique (minuscules) de chaque opérateur Fortran — source : ABLNodeType
        private val FORTRAN_TEXT = mapOf(
            ABLNodeType.EQ    to "eq",
            ABLNodeType.NE    to "ne",
            ABLNodeType.GTHAN to "gt",
            ABLNodeType.LTHAN to "lt",
            ABLNodeType.GE    to "ge",
            ABLNodeType.LE    to "le"
        )
        private val MODERN_MAP = mapOf(
            ABLNodeType.EQ    to "=",
            ABLNodeType.NE    to "<>",
            ABLNodeType.GTHAN to ">",
            ABLNodeType.LTHAN to "<",
            ABLNodeType.GE    to ">=",
            ABLNodeType.LE    to "<="
        )
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
