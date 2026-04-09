package com.ablls.plugin.inspections

import com.ablls.plugin.language.AblLanguage
import com.intellij.codeInspection.LocalInspectionTool
import com.intellij.codeInspection.ProblemsHolder
import com.intellij.codeInspection.LocalQuickFix
import com.intellij.codeInspection.ProblemDescriptor
import com.intellij.openapi.project.Project
import com.intellij.psi.PsiElement
import com.intellij.psi.PsiElementVisitor
import com.intellij.psi.PsiFile

/**
 * Inspection signalant l'absence de NO-UNDO sur les variables et temp-tables.
 * En ABL, oublier NO-UNDO sur une variable force l'écriture des changements
 * dans le Before-Image (BI) file, ce qui dégrade drastiquement les performances.
 */
class AblNoUndoInspection : LocalInspectionTool() {

    override fun getDisplayName() = "Missing NO-UNDO modifier"
    override fun getShortName() = "AblMissingNoUndo"
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
                if (text.equals("DEFINE", ignoreCase = true) || text.equals("DEF", ignoreCase = true)) {
                    
                    // Trouver le prochain élément pertinent (ignorer les espaces/commentaires)
                    var next = element.nextSibling
                    while (next != null && next.text.isBlank()) {
                        next = next.nextSibling
                    }

                    if (next != null) {
                        val isVariable = next.text.equals("VARIABLE", ignoreCase = true) || next.text.equals("VAR", ignoreCase = true)
                        val isTempTable = next.text.equals("TEMP-TABLE", ignoreCase = true)

                        if (isVariable || isTempTable) {
                            var current = next.nextSibling
                            var foundNoUndo = false
                            var foundDot = false

                            while (current != null) {
                                val cText = current.text
                                if (cText.equals("NO-UNDO", ignoreCase = true)) {
                                    foundNoUndo = true
                                    break
                                }
                                if (isStatementEnd(current)) {
                                    foundDot = true
                                    break
                                }
                                // Sécurité : si on tombe sur un nouveau DEFINE, on arrête.
                                if (cText.equals("DEFINE", ignoreCase = true)) {
                                    break
                                }
                                current = current.nextSibling
                            }

                            if (!foundNoUndo && foundDot) {
                                val description = if (isVariable) "Missing NO-UNDO modifier on VARIABLE (affects performance)" 
                                                  else "Missing NO-UNDO modifier on TEMP-TABLE (affects performance)"
                                
                                holder.registerProblem(
                                    element, 
                                    description, 
                                    AddNoUndoFix(isVariable)
                                )
                            }
                        }
                    }
                }
            }
        }
    }

    // ─── Quick Fix : Ajouter NO-UNDO automatiquement ─────────────────────────

    private class AddNoUndoFix(private val isVariable: Boolean) : LocalQuickFix {
        override fun getFamilyName() = if (isVariable) "Add NO-UNDO to variable" else "Add NO-UNDO to temp-table"

        private fun isStatementEnd(dot: PsiElement): Boolean {
            if (dot.text != ".") return false
            val next = dot.nextSibling ?: return true
            val text = next.text
            return text.isBlank() || text.startsWith("/")
        }

        override fun applyFix(project: Project, descriptor: ProblemDescriptor) {
            val element = descriptor.psiElement
            var current = element.nextSibling
            
            // Chercher le point de fin
            while (current != null) {
                if (isStatementEnd(current)) {
                    val offset = current.textOffset
                    element.containingFile.viewProvider.document?.insertString(offset, " NO-UNDO")
                    break
                }
                current = current.nextSibling
            }
        }
    }
}
