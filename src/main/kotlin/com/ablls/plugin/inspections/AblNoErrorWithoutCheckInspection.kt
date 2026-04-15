package com.ablls.plugin.inspections

import com.ablls.plugin.core.AblProjectAnalysisService
import com.ablls.plugin.language.AblLanguage
import com.intellij.codeInspection.*
import com.intellij.openapi.components.service
import com.intellij.psi.PsiDocumentManager
import com.intellij.psi.PsiElementVisitor
import com.intellij.psi.PsiFile

/**
 * Inspection : FIND / CAN-FIND / RUN avec NO-ERROR sans vérification
 * de ERROR-STATUS:ERROR ou RETURN-VALUE immédiatement après.
 *
 * Pattern dangereux :
 *   FIND Customer WHERE CustNum = 1 NO-ERROR.
 *   // ici on ne vérifie pas si la ligne a été trouvée ou si une erreur s'est produite
 *
 * Pattern correct :
 *   FIND Customer WHERE CustNum = 1 NO-ERROR.
 *   IF NOT AVAILABLE Customer THEN ...
 *   IF ERROR-STATUS:ERROR THEN ...
 *
 * Stratégie : scan du TokenStream — pour chaque NO-ERROR, regarder
 * les 40 tokens suivants pour trouver ERROR-STATUS, AVAILABLE, ou RETURN-VALUE.
 */
class AblNoErrorWithoutCheckInspection : LocalInspectionTool() {

    override fun getDisplayName()      = "NO-ERROR without subsequent error check"
    override fun getShortName()        = "AblNoErrorWithoutCheck"
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
                    val text = t.text?.uppercase() ?: continue
                    if (text != "NO-ERROR") continue
                    if (t.line <= 0) continue

                    // Vérifier que les tokens précédents contiennent FIND, RUN ou CAN-FIND
                    val precedingTexts = (maxOf(0, i - 30) until i).map {
                        tokens.get(it).text?.uppercase() ?: ""
                    }
                    val hasTrigger = precedingTexts.any { it in TRIGGER_KEYWORDS }
                    if (!hasTrigger) continue

                    // Regarder les tokens suivants pour une vérification d'erreur
                    val lookAhead = (i + 1 until minOf(size, i + 40)).map {
                        tokens.get(it).text?.uppercase() ?: ""
                    }
                    val hasCheck = lookAhead.any { it in CHECK_KEYWORDS }
                    if (hasCheck) continue

                    val range = AblInspectionHelper.toRange(doc, t.line, t.charPositionInLine, "NO-ERROR".length)
                    holder.registerProblem(file, "NO-ERROR used without subsequent ERROR-STATUS:ERROR, AVAILABLE or RETURN-VALUE check — errors will be silently ignored", ProblemHighlightType.WARNING, range)
                }
            }
        }

    companion object {
        private val TRIGGER_KEYWORDS = setOf("FIND", "RUN", "CAN-FIND", "INPUT", "OUTPUT")
        private val CHECK_KEYWORDS   = setOf("ERROR-STATUS", "AVAILABLE", "RETURN-VALUE",
                                              "NOT", "IF", "AVAIL")
    }
}
