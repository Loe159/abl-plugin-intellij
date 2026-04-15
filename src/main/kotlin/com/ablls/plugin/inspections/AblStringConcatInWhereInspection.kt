package com.ablls.plugin.inspections

import com.ablls.plugin.core.AblProjectAnalysisService
import com.ablls.plugin.language.AblLanguage
import com.intellij.codeInspection.*
import com.intellij.openapi.components.service
import com.intellij.psi.PsiDocumentManager
import com.intellij.psi.PsiElementVisitor
import com.intellij.psi.PsiFile
import org.antlr.v4.runtime.Token

/**
 * Inspection : concaténation de chaîne (+) dans une clause WHERE.
 *
 * Pattern dangereux :
 *   FOR EACH Customer WHERE Customer.Name = "Mr." + lastName NO-LOCK:
 *
 * La concaténation dans un WHERE force Progress à évaluer côté client
 * au lieu d'utiliser les indexes — impact performance majeur sur grandes tables.
 *
 * Stratégie : scan du TokenStream. On repère les clauses WHERE en cherchant
 * le token WHERE et on scanne jusqu'au token NO-LOCK/OF/BY/END/: pour un '+'.
 */
class AblStringConcatInWhereInspection : LocalInspectionTool() {

    override fun getDisplayName()      = "String concatenation in WHERE clause"
    override fun getShortName()        = "AblStringConcatInWhere"
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
                var inWhere  = false
                var whereEnd = -1

                for (i in 0 until size) {
                    val t    = tokens.get(i)
                    if (t.channel != Token.DEFAULT_CHANNEL) continue
                    val text = t.text?.uppercase() ?: continue

                    if (!inWhere) {
                        if (text == "WHERE") { inWhere = true; whereEnd = -1 }
                        continue
                    }

                    // Tokens terminant la clause WHERE
                    if (text in WHERE_TERMINATORS) { inWhere = false; continue }

                    if (text == "+") {
                        val range = AblInspectionHelper.toRange(doc, t.line, t.charPositionInLine, 1)
                        holder.registerProblem(file, "String concatenation (+) in WHERE clause disables index usage — evaluate expression before the query", ProblemHighlightType.WARNING, range)
                    }
                }
            }
        }

    companion object {
        private val WHERE_TERMINATORS = setOf(
            "NO-LOCK", "SHARE-LOCK", "EXCLUSIVE-LOCK",
            "BY", "BREAK", "OF", "EACH", "FIRST", "LAST",
            "DO", "END", ":", "."
        )
    }
}
