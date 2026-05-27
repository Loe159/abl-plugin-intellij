package com.ablls.plugin.inspections

import com.ablls.plugin.core.AblProjectAnalysisService
import com.ablls.plugin.language.AblLanguage
import com.intellij.codeInspection.LocalInspectionTool
import com.intellij.codeInspection.ProblemHighlightType
import com.intellij.codeInspection.ProblemsHolder
import com.intellij.openapi.components.service
import com.intellij.psi.PsiDocumentManager
import com.intellij.psi.PsiElementVisitor
import com.intellij.psi.PsiFile
import org.antlr.v4.runtime.Token
import org.prorefactor.core.JPNode

/**
 * Inspection : procédure ou fonction interne jamais référencée dans le fichier courant.
 *
 * Analyse le flux de tokens pour compter les occurrences du nom de chaque routine.
 * Si le nom n'apparaît qu'une seule fois (la définition elle-même), la routine est
 * signalée comme potentiellement morte.
 *
 * Limites connues :
 *  - Les appels depuis d'autres fichiers ne sont pas détectés.
 *  - Les appels via RUN VALUE(...) (dynamiques) ne sont pas détectés.
 *  - Les forward declarations comptent comme une occurrence supplémentaire
 *    (donc une procédure forward-declared sans appel n'est pas signalée).
 *
 * Niveau : WEAK_WARNING (information, pas erreur).
 */
class AblDeadCodeInspection : LocalInspectionTool() {
    override fun getDisplayName() = "Internal procedure or function never referenced in file"

    override fun getShortName() = "AblDeadCode"

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
                val parseResult = service.analyzeFile(file.text, uri)
                val tokens = parseResult.tokens ?: return
                val doc = PsiDocumentManager.getInstance(file.project).getDocument(file) ?: return

                // Analyse sémantique pour obtenir les routines avec leur position de définition
                val semantic =
                    try {
                        service.analyzeFileSemantic(file.text, uri)
                    } catch (_: Exception) {
                        null
                    } ?: return
                val scope = semantic.rootScope ?: return

                checkScopeForDeadCode(scope, tokens, holder, file, doc)
            }
        }

    private fun checkScopeForDeadCode(
        scope: org.prorefactor.treeparser.TreeParserSymbolScope,
        tokens: org.antlr.v4.runtime.CommonTokenStream,
        holder: ProblemsHolder,
        file: PsiFile,
        doc: com.intellij.openapi.editor.Document,
    ) {
        for (routine in runCatching { scope.routines }.getOrNull() ?: emptyList()) {
            val name = routine.name.takeIf { it.isNotBlank() } ?: continue
            // Ignorer les méthodes de classe (OO) — leur portée est différente
            if (name.contains("::")) continue

            val defNode: JPNode? = runCatching { routine.getDefineNode() }.getOrNull()
            val defLine = defNode?.token?.line ?: continue

            // Compter les occurrences du nom dans le stream (case-insensitive, default channel)
            val tokenSize = tokens.size()
            var defOccurrences = 0
            var otherOccurrences = 0

            for (ti in 0 until tokenSize) {
                val t = tokens.get(ti)
                if (t.channel != Token.DEFAULT_CHANNEL) continue
                if (!t.text.equals(name, ignoreCase = true)) continue
                if (t.line == defLine) defOccurrences++ else otherOccurrences++
            }

            // Si le nom n'apparaît nulle part ailleurs qu'à la ligne de définition
            if (otherOccurrences == 0 && defOccurrences >= 1) {
                val col = defNode?.token?.charPositionInLine ?: 0
                val range = AblInspectionHelper.toRange(doc, defLine, col, name.length)
                holder.registerProblem(
                    file,
                    "'$name' is defined but never referenced in this file (may be called from external files)",
                    ProblemHighlightType.WEAK_WARNING,
                    range,
                )
            }
        }

        // Récursion dans les scopes enfants
        for (child in runCatching { scope.childScopes }.getOrNull() ?: emptyList()) {
            checkScopeForDeadCode(child, tokens, holder, file, doc)
        }
    }
}
