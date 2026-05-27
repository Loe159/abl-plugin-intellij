package com.ablls.plugin.inspections

import com.ablls.plugin.core.AblProjectAnalysisService
import com.ablls.plugin.language.AblLanguage
import com.intellij.codeInspection.LocalInspectionTool
import com.intellij.codeInspection.LocalQuickFix
import com.intellij.codeInspection.ProblemDescriptor
import com.intellij.codeInspection.ProblemHighlightType
import com.intellij.codeInspection.ProblemsHolder
import com.intellij.openapi.components.service
import com.intellij.openapi.editor.Document
import com.intellij.openapi.project.Project
import com.intellij.psi.PsiDocumentManager
import com.intellij.psi.PsiElementVisitor
import com.intellij.psi.PsiFile
import org.prorefactor.core.JPNode
import org.prorefactor.treeparser.TreeParserSymbolScope

/**
 * Inspection : variable déclarée INTEGER alors qu'INT64 serait plus adapté.
 *
 * Signale les variables `DEFINE VARIABLE x AS INTEGER` lorsque leur nom
 * suggère qu'elles pourraient contenir de grands nombres :
 *   - Noms contenant "count", "total", "sum", "size", "amount", "bytes", etc.
 *
 * L'overflow d'INTEGER en ABL se produit pour des valeurs > 2 147 483 647.
 * INT64 supporte jusqu'à 9 223 372 036 854 775 807.
 *
 * Utilise le TreeParserSymbolScope (treeParser01) pour obtenir le type résolu
 * et la position exacte du token de nom via variable.getDefineNode().
 *
 * Niveau : WEAK_WARNING (suggestion).
 */
class AblIntegerOverflowInspection : LocalInspectionTool() {
    override fun getDisplayName() = "INTEGER variable may overflow — consider INT64"

    override fun getShortName() = "AblIntegerOverflow"

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
                val doc = PsiDocumentManager.getInstance(file.project).getDocument(file) ?: return

                val semantic =
                    try {
                        service.analyzeFileSemantic(file.text, uri)
                    } catch (_: Exception) {
                        null
                    }
                val scope = semantic?.rootScope ?: return

                checkScope(scope, holder, file, doc)
            }
        }

    private fun checkScope(
        scope: TreeParserSymbolScope,
        holder: ProblemsHolder,
        file: PsiFile,
        doc: Document,
    ) {
        for (variable in runCatching { scope.variables }.getOrNull() ?: emptyList()) {
            val name = variable.name.takeIf { it.isNotBlank() } ?: continue
            if (variable.javaClass.simpleName.contains("Parameter", ignoreCase = true)) continue
            if (!mightOverflow(name)) continue

            val isInteger = variable.dataType?.toString()?.equals("INTEGER", ignoreCase = true) == true
            if (!isInteger) continue

            val defNode: JPNode? = runCatching { variable.getDefineNode() }.getOrNull()
            val defLine = defNode?.token?.line ?: continue
            if (defLine <= 0) continue
            val defCol = defNode.token?.charPositionInLine ?: 0

            val range = AblInspectionHelper.toRange(doc, defLine, defCol, name.length)
            holder.registerProblem(
                file,
                "Variable '$name' is INTEGER — consider INT64 if it may hold values > 2,147,483,647",
                ProblemHighlightType.WEAK_WARNING,
                range,
                ChangeToInt64Fix(defLine, defCol, name.length),
            )
        }

        for (child in runCatching { scope.childScopes }.getOrNull() ?: emptyList()) {
            checkScope(child, holder, file, doc)
        }
    }

    companion object {
        private val OVERFLOW_HINTS =
            setOf(
                "count", "total", "sum", "size", "bytes", "amount", "balance",
                "quantity", "length", "offset", "position", "result", "value",
                "timestamp", "epoch", "millis", "seconds",
            )

        fun mightOverflow(name: String): Boolean {
            val lower = name.lowercase()
            return OVERFLOW_HINTS.any { hint -> lower.contains(hint) }
        }
    }

    private class ChangeToInt64Fix(
        private val line: Int,
        private val col: Int,
        @Suppress("unused") private val nameLen: Int,
    ) : LocalQuickFix {
        override fun getFamilyName() = "Change to INT64"

        override fun applyFix(
            project: Project,
            descriptor: ProblemDescriptor,
        ) {
            val file = descriptor.psiElement as? PsiFile ?: return
            val doc = PsiDocumentManager.getInstance(project).getDocument(file) ?: return
            val text = doc.text
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
