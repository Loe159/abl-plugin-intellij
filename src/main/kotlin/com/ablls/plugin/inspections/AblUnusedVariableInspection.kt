package com.ablls.plugin.inspections

import com.ablls.plugin.core.AblProjectAnalysisService
import com.ablls.plugin.language.AblLanguage
import com.intellij.codeInspection.*
import com.intellij.openapi.components.service
import com.intellij.openapi.editor.Document
import com.intellij.openapi.project.Project
import com.intellij.psi.PsiDocumentManager
import com.intellij.psi.PsiElementVisitor
import com.intellij.psi.PsiFile
import org.antlr.v4.runtime.CommonTokenStream
import org.antlr.v4.runtime.Token
import org.prorefactor.core.JPNode
import org.prorefactor.treeparser.TreeParserSymbolScope

/**
 * Inspection : variable DEFINE VARIABLE définie mais jamais utilisée.
 *
 * Algorithme : pour chaque variable du TreeParserSymbolScope, on compte ses occurrences
 * dans le flux de tokens (case-insensitive, default channel) en dehors de sa ligne de
 * définition. Si le compte est 0, la variable est signalée.
 *
 * Les paramètres de procédure/fonction sont exclus (OUTPUT = valeur retournée au caller).
 * Les variables préfixées par "_" sont ignorées par convention.
 *
 * Fallback textuel si l'analyse sémantique n'est pas disponible.
 */
class AblUnusedVariableInspection : LocalInspectionTool() {

    override fun getDisplayName()      = "Variable defined but never read"
    override fun getShortName()        = "AblUnusedVariable"
    override fun getGroupDisplayName() = "OpenEdge ABL"

    override fun buildVisitor(holder: ProblemsHolder, isOnTheFly: Boolean): PsiElementVisitor =
        object : PsiElementVisitor() {
            override fun visitFile(file: PsiFile) {
                if (file.language != AblLanguage) return
                val uri     = file.virtualFile?.url ?: return
                val service = file.project.service<AblProjectAnalysisService>()
                val doc     = PsiDocumentManager.getInstance(file.project).getDocument(file) ?: return

                val parseResult = service.analyzeFile(file.text, uri)
                val tokens      = parseResult.tokens ?: return

                val semantic = try {
                    service.analyzeFileSemantic(file.text, uri)
                } catch (_: Exception) { null }

                val scope = semantic?.rootScope
                if (scope != null) {
                    checkScope(scope, tokens, holder, file, doc)
                } else {
                    checkFallback(tokens, holder, file, doc)
                }
            }
        }

    // ─── Chemin sémantique ────────────────────────────────────────────────────

    private fun checkScope(
        scope: TreeParserSymbolScope,
        tokens: CommonTokenStream,
        holder: ProblemsHolder,
        file: PsiFile,
        doc: Document
    ) {
        for (variable in runCatching { scope.variables }.getOrNull() ?: emptyList()) {
            val name = variable.name.takeIf { it.isNotBlank() } ?: continue
            if (name.startsWith("_")) continue
            if (isParameter(variable)) continue

            val defNode: JPNode? = runCatching {
                variable.javaClass.getMethod("getDefineNode").invoke(variable) as? JPNode
            }.getOrNull()
            val defLine = defNode?.token?.line ?: continue
            if (defLine <= 0) continue

            var defOccurrences   = 0
            var otherOccurrences = 0
            val size = tokens.size()
            for (i in 0 until size) {
                val t = tokens.get(i)
                if (t.channel != Token.DEFAULT_CHANNEL) continue
                if (!t.text.equals(name, ignoreCase = true)) continue
                if (t.line == defLine) defOccurrences++ else otherOccurrences++
            }

            if (otherOccurrences == 0 && defOccurrences >= 1) {
                val col   = defNode.token?.charPositionInLine ?: 0
                val range = AblInspectionHelper.toRange(doc, defLine, col, name.length)
                holder.registerProblem(
                    file,
                    "Variable '$name' is defined but never read",
                    ProblemHighlightType.WARNING,
                    range,
                    DeleteUnusedVariableFix(defLine)
                )
            }
        }

        for (child in runCatching { scope.childScopes }.getOrNull() ?: emptyList()) {
            checkScope(child, tokens, holder, file, doc)
        }
    }

    /** Retourne true si [variable] est un paramètre (OUTPUT est valeur de retour pour l'appelant). */
    private fun isParameter(variable: Any): Boolean =
        variable.javaClass.simpleName.contains("Parameter", ignoreCase = true)

    // ─── Fallback textuel ─────────────────────────────────────────────────────

    /**
     * Utilisé quand treeParser01() a échoué ou n'a pas encore tourné.
     * Détecte les DEFINE VARIABLE dans le flux de tokens et compte les occurrences.
     */
    private fun checkFallback(
        tokens: CommonTokenStream,
        holder: ProblemsHolder,
        file: PsiFile,
        doc: Document
    ) {
        val size = tokens.size()
        var i = 0
        while (i < size) {
            val t = tokens.get(i)
            if (t.channel != Token.DEFAULT_CHANNEL || !t.text.equals("DEFINE", ignoreCase = true)) {
                i++; continue
            }

            // Chercher VARIABLE après DEFINE (en sautant les tokens hors default channel)
            var j = i + 1
            while (j < size && tokens.get(j).channel != Token.DEFAULT_CHANNEL) j++
            if (j >= size || !tokens.get(j).text.equals("VARIABLE", ignoreCase = true)) { i++; continue }

            // Le token suivant est le nom
            j++
            while (j < size && tokens.get(j).channel != Token.DEFAULT_CHANNEL) j++
            if (j >= size) { i++; continue }

            val nameTok = tokens.get(j)
            val name    = nameTok.text
            if (name == null || name.startsWith("_") || name.uppercase() in ABL_KEYWORDS) { i++; continue }

            // Compter les occurrences hors ligne de définition
            var defOccurrences   = 0
            var otherOccurrences = 0
            for (k in 0 until size) {
                val tk = tokens.get(k)
                if (tk.channel != Token.DEFAULT_CHANNEL) continue
                if (!tk.text.equals(name, ignoreCase = true)) continue
                if (tk.line == nameTok.line) defOccurrences++ else otherOccurrences++
            }

            if (otherOccurrences == 0 && defOccurrences >= 1 && nameTok.line > 0) {
                val range = AblInspectionHelper.toRange(doc, nameTok.line, nameTok.charPositionInLine, name.length)
                holder.registerProblem(
                    file,
                    "Variable '$name' is defined but never read",
                    ProblemHighlightType.WARNING,
                    range,
                    DeleteUnusedVariableFix(nameTok.line)
                )
            }
            i++
        }
    }

    companion object {
        // Filtre les faux positifs du mode fallback (tokens ABL confondus avec des noms)
        private val ABL_KEYWORDS = setOf(
            "AS", "NO-UNDO", "NO", "UNDO", "INTEGER", "CHARACTER", "LOGICAL",
            "DECIMAL", "DATE", "DATETIME", "INT64", "LONGCHAR", "MEMPTR", "RAW",
            "RECID", "ROWID", "HANDLE", "WIDGET-HANDLE", "CLASS", "EXTENT"
        )
    }
}

// ─── Quick Fix : supprimer la ligne de définition ────────────────────────────

private class DeleteUnusedVariableFix(private val defineLine: Int) : LocalQuickFix {
    override fun getFamilyName() = "Delete unused variable"

    override fun applyFix(project: Project, descriptor: ProblemDescriptor) {
        val file = descriptor.psiElement as? PsiFile ?: return
        val doc  = PsiDocumentManager.getInstance(project).getDocument(file) ?: return
        val line = (defineLine - 1).coerceIn(0, doc.lineCount - 1)
        val lineStart = doc.getLineStartOffset(line)
        val lineEnd   = if (line + 1 < doc.lineCount) doc.getLineStartOffset(line + 1)
                        else doc.textLength
        doc.deleteString(lineStart, lineEnd)
    }
}
