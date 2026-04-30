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
 * Inspection : FIND sans modificateur de verrou explicite.
 *
 * En ABL, un FIND sans NO-LOCK / SHARE-LOCK / EXCLUSIVE-LOCK prend
 * par défaut SHARE-LOCK, ce qui est presque toujours dangereux en production.
 *
 * Stratégie : parcours du JPNode tree via queryStateHead(FIND).
 * Pour chaque statement FIND, on vérifie qu'un des nœuds fils porte un
 * type NOLOCK / SHARELOCK / EXCLUSIVELOCK.
 */
class AblFindNoLockInspection : LocalInspectionTool() {

    override fun getDisplayName()      = "Missing Lock mode on FIND"
    override fun getShortName()        = "AblFindNoLock"
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

                for (findNode in topNode.queryStateHead(ABLNodeType.FIND)) {
                    val hasLock = findNode.query(ABLNodeType.NOLOCK, ABLNodeType.SHARELOCK, ABLNodeType.EXCLUSIVELOCK).isNotEmpty()
                    if (!hasLock) {
                        val range = AblInspectionHelper.toRange(doc, findNode.line, findNode.column, "FIND".length)
                        holder.registerProblem(
                            file,
                            "Missing lock modifier on FIND (defaults to SHARE-LOCK, which is often dangerous).",
                            ProblemHighlightType.WARNING,
                            range,
                            AddNoLockFix(range.startOffset)
                        )
                    }
                }
            }
        }

    companion object {
        // Source de vérité : ABLNodeType — couvre les abréviations automatiquement
        private val LOCK_TYPES: Set<ABLNodeType> = java.util.EnumSet.of(
            ABLNodeType.NOLOCK, ABLNodeType.SHARELOCK, ABLNodeType.EXCLUSIVELOCK
        )
    }

    private class AddNoLockFix(private val findOffset: Int) : LocalQuickFix {
        override fun getFamilyName() = "Add NO-LOCK"

        override fun applyFix(project: Project, descriptor: ProblemDescriptor) {
            val file = descriptor.psiElement as? PsiFile ?: return
            val doc  = PsiDocumentManager.getInstance(project).getDocument(file) ?: return
            val text = doc.charsSequence
            var i    = findOffset
            while (i < text.length) {
                if (text[i] == '.' && (i + 1 >= text.length || text[i + 1].isWhitespace() || text[i + 1] == '/')) {
                    doc.insertString(i, " NO-LOCK")
                    break
                }
                i++
            }
        }
    }
}
