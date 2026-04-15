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
 * Inspection : bloc CATCH vide ou ne contenant qu'un RETURN.
 *
 * Pattern dangereux :
 *   CATCH e AS Progress.Lang.Error:
 *   END CATCH.
 *
 * Stratégie : scan du TokenStream.
 * On cherche CATCH, puis on collecte les tokens jusqu'à "END CATCH" ou "END." en comptant
 * la profondeur des blocs imbriqués.
 * Si aucun statement significatif n'est trouvé entre CATCH..END, on signale.
 */
class AblEmptyCatchInspection : LocalInspectionTool() {

    override fun getDisplayName()      = "Empty or return-only CATCH block"
    override fun getShortName()        = "AblEmptyCatch"
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
                var i = 0
                while (i < size) {
                    val t = tokens.get(i)
                    if (t.channel != Token.DEFAULT_CHANNEL) { i++; continue }
                    val text = t.text?.uppercase() ?: ""

                    if (text != "CATCH") { i++; continue }

                    val catchLine = t.line
                    val catchCol  = t.charPositionInLine

                    // Avancer jusqu'au ':' qui ouvre le bloc
                    var j = i + 1
                    while (j < size && tokens.get(j).text != ":") j++
                    j++ // premier token après ':'

                    // Scanner le corps jusqu'à END CATCH ou END.
                    var depth = 1
                    val bodyTokens = mutableListOf<String>()
                    while (j < size && depth > 0) {
                        val bt = tokens.get(j)
                        if (bt.channel == Token.DEFAULT_CHANNEL) {
                            val btText = bt.text?.uppercase() ?: ""
                            when {
                                btText in BLOCK_OPENERS -> depth++
                                btText == "END" -> {
                                    depth--
                                    if (depth == 0) break
                                }
                                else -> if (depth == 1) bodyTokens += btText
                            }
                        }
                        j++
                    }

                    // Filtrer les tokens non significatifs
                    val significant = bodyTokens.filter { it !in NON_SIGNIFICANT }
                    if (significant.isEmpty() || (significant.size == 1 && significant[0] == "RETURN")) {
                        val range = AblInspectionHelper.toRange(doc, catchLine, catchCol, "CATCH".length)
                        holder.registerProblem(file, "Empty CATCH block silently swallows exceptions — add error handling or logging", ProblemHighlightType.WARNING, range)
                    }
                    i = j + 1
                }
            }
        }

    companion object {
        private val BLOCK_OPENERS    = setOf("DO", "REPEAT", "FOR", "PROCEDURE", "FUNCTION", "CLASS", "METHOD", "IF", "CASE", "FINALLY", "CATCH")
        private val NON_SIGNIFICANT  = setOf(".", ":", "CATCH", "AS", "RETURN")
    }
}
