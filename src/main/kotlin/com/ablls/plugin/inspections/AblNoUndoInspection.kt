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
 * Inspection : DEFINE VARIABLE / DEFINE TEMP-TABLE sans NO-UNDO.
 *
 * Oublier NO-UNDO force l'écriture des changements dans le Before-Image (BI) file,
 * ce qui dégrade drastiquement les performances.
 *
 * Stratégie : parcours du JPNode tree via queryStateHead(DEFINE).
 * Pour chaque DEFINE, on vérifie le type secondaire (VARIABLE / TEMPTABLE via
 * IStatement.getNodeType2()) et l'absence de nœud fils NOUNDO.
 */
class AblNoUndoInspection : LocalInspectionTool() {

    override fun getDisplayName()      = "Missing NO-UNDO modifier"
    override fun getShortName()        = "AblMissingNoUndo"
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

                for (defineNode in topNode.queryStateHead(ABLNodeType.DEFINE)) {
                    if (defineNode.hasProparseDirective("NOANALYSIS")) continue
                    val nodeType2 = runCatching { defineNode.asIStatement().nodeType2 }.getOrNull()
                        ?: continue
                    val isVariable  = nodeType2 == ABLNodeType.VARIABLE
                    val isTempTable = nodeType2 == ABLNodeType.TEMPTABLE
                    if (!isVariable && !isTempTable) continue

                    if (defineNode.query(ABLNodeType.NOUNDO).isNotEmpty()) continue

                    val msg   = if (isVariable) "Missing NO-UNDO modifier on VARIABLE (affects performance)"
                                else             "Missing NO-UNDO modifier on TEMP-TABLE (affects performance)"
                    val range = AblInspectionHelper.toRange(doc, defineNode.line, defineNode.column, "DEFINE".length)
                    holder.registerProblem(
                        file, msg, ProblemHighlightType.WARNING, range,
                        AddNoUndoFix(range.startOffset, isVariable)
                    )
                }
            }
        }

    private class AddNoUndoFix(
        private val defineOffset: Int,
        private val isVariable: Boolean
    ) : LocalQuickFix {
        override fun getFamilyName() =
            if (isVariable) "Add NO-UNDO to variable" else "Add NO-UNDO to temp-table"

        override fun applyFix(project: Project, descriptor: ProblemDescriptor) {
            val file = descriptor.psiElement as? PsiFile ?: return
            val doc  = PsiDocumentManager.getInstance(project).getDocument(file) ?: return
            val text = doc.charsSequence
            var i    = defineOffset
            while (i < text.length) {
                if (text[i] == '.' && (i + 1 >= text.length || text[i + 1].isWhitespace() || text[i + 1] == '/')) {
                    doc.insertString(i, " NO-UNDO")
                    break
                }
                i++
            }
        }
    }
}
