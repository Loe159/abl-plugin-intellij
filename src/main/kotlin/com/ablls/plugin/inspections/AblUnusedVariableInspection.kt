package com.ablls.plugin.inspections

import com.ablls.plugin.core.AblProjectAnalysisService
import com.ablls.plugin.language.AblLanguage
import com.intellij.codeInspection.*
import com.intellij.openapi.components.service
import com.intellij.openapi.project.Project
import com.intellij.psi.PsiDocumentManager
import com.intellij.psi.PsiElementVisitor
import com.intellij.psi.PsiFile
import org.antlr.v4.runtime.Token
import org.prorefactor.treeparser.TreeParserSymbolScope

/**
 * Inspection : variable DEFINE VARIABLE définie mais jamais lue.
 *
 * Utilise l'analyse sémantique complète (ParseUnit.treeParser01) pour obtenir
 * les informations de lecture/écriture depuis le TreeParserSymbolScope.
 * Fallback sur le comptage textuel si la sémantique n'est pas disponible.
 */
class AblUnusedVariableInspection : LocalInspectionTool() {

    override fun getDisplayName()      = "Variable defined but never read"
    override fun getShortName()        = "AblUnusedVariable"
    override fun getGroupDisplayName() = "ABL Best Practices"

    override fun buildVisitor(holder: ProblemsHolder, isOnTheFly: Boolean): PsiElementVisitor =
        object : PsiElementVisitor() {
            override fun visitFile(file: PsiFile) {
                if (file.language != AblLanguage) return
                val uri     = file.virtualFile?.url ?: return
                val service = file.project.service<AblProjectAnalysisService>()
                val doc     = PsiDocumentManager.getInstance(file.project).getDocument(file) ?: return

                // Tenter l'analyse sémantique (bloquant — inspectons sont sur background thread)
                val semantic = try {
                    service.analyzeFileSemantic(file.text, uri)
                } catch (_: Exception) { null }

                val scope = semantic?.rootScope
                if (scope != null) {
                    checkScope(scope, holder, file, doc, service, uri)
                } else {
                    // Fallback : comptage textuel depuis l'arbre syntaxique
                    checkFallback(service, file, holder, doc, uri)
                }
            }
        }

    private fun checkScope(
        scope: TreeParserSymbolScope,
        holder: ProblemsHolder,
        file: PsiFile,
        doc: com.intellij.openapi.editor.Document,
        service: AblProjectAnalysisService,
        uri: String
    ) {
        collectVariablesFromScope(scope).forEach { (name, defLine, defCol) ->
            if (name.startsWith("_")) return@forEach  // convention : variables privées ignorées

            // Utiliser le token stream pour compter les occurrences hors définition
            val parseResult = service.analyzeFile(file.text, uri)
            val tokens = parseResult.tokens ?: return@forEach
            var readCount = 0
            var defIndex  = -1

            val size = tokens.size()
            for (i in 0 until size) {
                val t = tokens.get(i)
                if (t.channel != Token.DEFAULT_CHANNEL) continue
                if (t.text?.equals(name, ignoreCase = true) != true) continue
                if (defIndex == -1 && t.line == defLine) { defIndex = i; continue }
                readCount++
            }

            if (readCount == 0 && defLine > 0) {
                val range = AblInspectionHelper.toRange(doc, defLine, defCol, name.length)
                holder.registerProblem(file, "Variable '$name' is defined but never read", ProblemHighlightType.WARNING, range)
            }
        }
    }

    /**
     * Collecte (name, defineLine, defineCol) depuis le scope et ses enfants.
     */
    private fun collectVariablesFromScope(scope: TreeParserSymbolScope): List<Triple<String, Int, Int>> {
        val result = mutableListOf<Triple<String, Int, Int>>()
        try {
            for (variable in scope.variables) {
                // Ignorer les paramètres (OUTPUT-only est légitime)
                if (variable.javaClass.simpleName == "Parameter") continue
                val defNode = runCatching {
                    variable.javaClass.getMethod("getDefineNode").invoke(variable)
                        as? org.prorefactor.core.JPNode
                }.getOrNull()
                val line = defNode?.token?.line ?: 0
                val col  = defNode?.token?.charPositionInLine ?: 0
                result += Triple(variable.name, line, col)
            }
            for (child in scope.childScopes) {
                result += collectVariablesFromScope(child)
            }
        } catch (_: Exception) {}
        return result
    }

    /** Fallback quand la sémantique n'est pas disponible : simple comptage textuel. */
    private fun checkFallback(
        service: AblProjectAnalysisService,
        file: PsiFile,
        holder: ProblemsHolder,
        doc: com.intellij.openapi.editor.Document,
        uri: String
    ) {
        val parseResult = service.analyzeFile(file.text, uri)
        val tokens = parseResult.tokens ?: return
        val size   = tokens.size()

        // Trouver les DEFINE VARIABLE
        for (i in 0 until size - 2) {
            val t1 = tokens.get(i)
            val t2 = tokens.get(i + 1)
            if (t1.channel != Token.DEFAULT_CHANNEL) continue
            if (!t1.text.equals("DEFINE", ignoreCase = true) && !t1.text.equals("DEF", ignoreCase = true)) continue

            // Sauter les espaces
            var j = i + 1
            while (j < size && tokens.get(j).channel != Token.DEFAULT_CHANNEL) j++
            if (j >= size) continue
            val keyword = tokens.get(j).text?.uppercase() ?: continue
            if (keyword != "VARIABLE" && keyword != "VAR") continue

            // Le prochain token du default channel est le nom
            j++
            while (j < size && tokens.get(j).channel != Token.DEFAULT_CHANNEL) j++
            if (j >= size) continue
            val nameTok = tokens.get(j)
            val name    = nameTok.text ?: continue
            if (name.startsWith("_")) continue

            // Compter les occurrences hors définition
            var count = 0
            for (k in 0 until size) {
                if (k == j) continue
                val tk = tokens.get(k)
                if (tk.channel != Token.DEFAULT_CHANNEL) continue
                if (tk.text?.equals(name, ignoreCase = true) == true) count++
            }
            if (count == 0 && nameTok.line > 0) {
                val range = AblInspectionHelper.toRange(doc, nameTok.line, nameTok.charPositionInLine, name.length)
                holder.registerProblem(file, "Variable '\$name' is defined but never read", ProblemHighlightType.WARNING, range)
            }
        }
    }
}
