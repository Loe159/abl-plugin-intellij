package com.ablls.plugin.inspections

import com.ablls.plugin.language.AblLanguage
import com.intellij.codeInspection.LocalInspectionTool
import com.intellij.codeInspection.ProblemsHolder
import com.intellij.codeInspection.LocalQuickFix
import com.intellij.codeInspection.ProblemDescriptor
import com.intellij.openapi.project.Project
import com.intellij.psi.PsiElement
import com.intellij.psi.PsiElementVisitor

/**
 * Inspection signalant l'absence de NO-LOCK (ou EXCLUSIVE-LOCK) sur un FIND.
 * En ABL, un FIND sans verrou explicite prend par défaut SHARE-LOCK,
 * ce qui est presque toujours une erreur en production.
 */
class AblFindNoLockInspection : LocalInspectionTool() {

    override fun getDisplayName() = "Missing Lock mode on FIND"
    override fun getShortName() = "AblFindNoLock"
    override fun getGroupDisplayName() = "ABL Best Practices"

    private fun isStatementEnd(dot: PsiElement): Boolean {
        if (dot.text != ".") return false
        val next = dot.nextSibling ?: return true
        val text = next.text
        return text.isBlank() || text.startsWith("/")
    }

    override fun buildVisitor(holder: ProblemsHolder, isOnTheFly: Boolean): PsiElementVisitor {
        return object : PsiElementVisitor() {
            override fun visitElement(element: PsiElement) {
                if (element.language != AblLanguage) return

                val text = element.text
                if (text.equals("FIND", ignoreCase = true)) {
                    
                    var current = element.nextSibling
                    var foundLock = false
                    var foundDot = false

                    while (current != null) {
                        val cText = current.text
                        // Verrous possibles : NO-LOCK, SHARE-LOCK, EXCLUSIVE-LOCK
                        if (cText.equals("NO-LOCK", ignoreCase = true) || 
                            cText.equals("EXCLUSIVE-LOCK", ignoreCase = true) || 
                            cText.equals("SHARE-LOCK", ignoreCase = true)) {
                            foundLock = true
                            break
                        }
                        if (isStatementEnd(current)) {
                            foundDot = true
                            break
                        }
                        // Sécurité : fin du FIND
                        if (cText.equals("IF", ignoreCase = true) || cText.equals("FIND", ignoreCase = true)) {
                            break
                        }
                        current = current.nextSibling
                    }

                    if (!foundLock && foundDot) {
                        holder.registerProblem(
                            element, 
                            "Missing lock modifier on FIND (defaults to SHARE-LOCK, which is often dangerous).", 
                            AddNoLockFix()
                        )
                    }
                }
            }
        }
    }

    private class AddNoLockFix : LocalQuickFix {
        override fun getFamilyName() = "Add NO-LOCK"

        override fun applyFix(project: Project, descriptor: ProblemDescriptor) {
            val element = descriptor.psiElement
            var current = element.nextSibling
            
            fun isStatementEnd(dot: PsiElement): Boolean {
                if (dot.text != ".") return false
                val next = dot.nextSibling ?: return true
                val text = next.text
                return text.isBlank() || text.startsWith("/")
            }

            while (current != null) {
                if (isStatementEnd(current)) {
                    val offset = current.textOffset
                    element.containingFile.viewProvider.document?.insertString(offset, " NO-LOCK")
                    break
                }
                current = current.nextSibling
            }
        }
    }
}
