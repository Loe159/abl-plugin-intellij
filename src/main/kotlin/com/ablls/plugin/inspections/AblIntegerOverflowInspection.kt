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
 * Inspection : variable déclarée INTEGER alors qu'INT64 serait plus adapté.
 *
 * Signale les variables `DEFINE VARIABLE x AS INTEGER` lorsque leur nom
 * suggère qu'elles pourraient contenir de grands nombres :
 *   - Noms contenant "count", "total", "sum", "size", "amount", "bytes"
 *   - Variables utilisées dans des opérations d'agrégation (heuristique simple)
 *
 * L'overflow d'INTEGER en ABL se produit pour des valeurs > 2 147 483 647.
 * INT64 supporte jusqu'à 9 223 372 036 854 775 807.
 *
 * Niveau : WEAK_WARNING (suggestion).
 */
class AblIntegerOverflowInspection : LocalInspectionTool() {

    override fun getDisplayName()      = "INTEGER variable may overflow — consider INT64"
    override fun getShortName()        = "AblIntegerOverflow"
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

                for (defNode in topNode.queryStateHead(ABLNodeType.DEFINE)) {
                    if (defNode.hasProparseDirective("NOANALYSIS")) continue
                    val varNode = defNode.query(ABLNodeType.VARIABLE).firstOrNull() ?: continue

                    // Trouver le nom et le type depuis les fils
                    var name: String? = null
                    var isInteger = false
                    var nameNode: org.prorefactor.core.JPNode? = null
                    var child = defNode.firstChild
                    var foundAs = false

                    while (child != null) {
                        val txt = child.text?.uppercase() ?: ""
                        when {
                            !foundAs && child.nodeType == ABLNodeType.AS -> foundAs = true
                            foundAs && (txt == "INTEGER" || txt == "INT") -> { isInteger = true; foundAs = false }
                            !isInteger && !foundAs && child.nodeType == ABLNodeType.VARIABLE -> {
                                nameNode = child.firstChild
                                name = nameNode?.text
                            }
                        }
                        child = child.nextSibling
                    }

                    if (!isInteger || name == null || nameNode == null) continue
                    if (!mightOverflow(name)) continue

                    val range = AblInspectionHelper.toRange(doc, nameNode.line, nameNode.column, name.length)
                    holder.registerProblem(
                        file,
                        "Variable '$name' is INTEGER — consider INT64 if it may hold values > 2,147,483,647",
                        ProblemHighlightType.WEAK_WARNING,
                        range,
                        ChangeToInt64Fix(nameNode.line, nameNode.column, name.length)
                    )
                }
            }
        }

    companion object {
        private val OVERFLOW_HINTS = setOf(
            "count", "total", "sum", "size", "bytes", "amount", "balance",
            "quantity", "length", "offset", "position", "result", "value",
            "timestamp", "epoch", "millis", "seconds"
        )

        fun mightOverflow(name: String): Boolean {
            val lower = name.lowercase()
            return OVERFLOW_HINTS.any { hint -> lower.contains(hint) }
        }
    }

    private class ChangeToInt64Fix(
        private val line: Int,
        private val col: Int,
        private val nameLen: Int
    ) : LocalQuickFix {
        override fun getFamilyName() = "Change to INT64"

        override fun applyFix(project: Project, descriptor: ProblemDescriptor) {
            val file = descriptor.psiElement as? PsiFile ?: return
            val doc  = PsiDocumentManager.getInstance(project).getDocument(file) ?: return
            val text = doc.text
            // Chercher "INTEGER" ou "INT " (avec espace) après la déclaration de la variable
            val start = doc.getLineStartOffset((line - 1).coerceAtLeast(0))
            val lineEnd = if (line < doc.lineCount) doc.getLineStartOffset(line) else doc.textLength
            val lineText = text.substring(start, lineEnd)
            val intIdx = lineText.uppercase().indexOf("INTEGER")
            if (intIdx >= 0) {
                doc.replaceString(start + intIdx, start + intIdx + "INTEGER".length, "INT64")
            } else {
                val intShortIdx = lineText.uppercase().indexOf(" INT ")
                if (intShortIdx >= 0) {
                    doc.replaceString(start + intShortIdx + 1, start + intShortIdx + 4, "INT64")
                }
            }
        }
    }
}
