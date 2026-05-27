package com.ablls.plugin.inspections

import com.ablls.plugin.core.AblProjectAnalysisService
import com.ablls.plugin.language.AblLanguage
import com.intellij.codeInspection.LocalInspectionTool
import com.intellij.codeInspection.ProblemHighlightType
import com.intellij.codeInspection.ProblemsHolder
import com.intellij.openapi.components.service
import com.intellij.openapi.editor.Document
import com.intellij.psi.PsiDocumentManager
import com.intellij.psi.PsiElementVisitor
import com.intellij.psi.PsiFile
import org.prorefactor.core.JPNode
import org.prorefactor.treeparser.TreeParserSymbolScope

/**
 * Inspection : convention de nommage des variables ABL.
 *
 * Signale les variables DEFINE VARIABLE dont le nom ne respecte pas les
 * préfixes conventionnels ABL (Hungarian notation) :
 *   l / b    → LOGICAL (booléen)
 *   i        → INTEGER / INT64
 *   c        → CHARACTER / LONGCHAR
 *   d        → DECIMAL / DATE / DATETIME
 *   h        → HANDLE
 *   r / ri   → RAW / RECID / ROWID
 *
 * Les paramètres, les variables commençant par `_`, les variables mono-lettre
 * (i, j, k…) et les globales (g_*, gi*, gc*…) sont ignorés.
 *
 * Utilise TreeParserSymbolScope pour les types résolus et la position exacte du nom.
 *
 * Niveau : WEAK_WARNING (désactivé par défaut — les conventions varient par équipe).
 */
class AblNamingConventionInspection : LocalInspectionTool() {
    override fun getDisplayName() = "Variable name does not follow ABL naming conventions"

    override fun getShortName() = "AblNamingConvention"

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

    @Suppress("CyclomaticComplexMethod")
    private fun checkScope(
        scope: TreeParserSymbolScope,
        holder: ProblemsHolder,
        file: PsiFile,
        doc: Document,
    ) {
        for (variable in runCatching { scope.variables }.getOrNull() ?: emptyList()) {
            val name = variable.name.takeIf { it.isNotBlank() } ?: continue
            if (variable.javaClass.simpleName.contains("Parameter", ignoreCase = true)) continue
            if (name.startsWith("_")) continue
            if (name.length == 1) continue
            if (GLOBAL_PREFIXES.any { name.startsWith(it, ignoreCase = true) }) continue

            val dataType = variable.dataType?.toString()?.uppercase() ?: continue
            val expectedPrefix = EXPECTED_PREFIXES[dataType] ?: continue

            val hasGoodPrefix = expectedPrefix.any { name.startsWith(it, ignoreCase = true) }
            if (hasGoodPrefix) continue

            val defNode: JPNode? = runCatching { variable.getDefineNode() }.getOrNull()
            val defLine = defNode?.token?.line ?: continue
            if (defLine <= 0) continue
            val defCol = defNode.token?.charPositionInLine ?: 0

            val suggestedPrefix = expectedPrefix.first()
            val range = AblInspectionHelper.toRange(doc, defLine, defCol, name.length)
            holder.registerProblem(
                file,
                "Variable '$name' of type $dataType should start with '$suggestedPrefix' " +
                    "(convention: ${expectedPrefix.joinToString("/") { "'$it'" }})",
                ProblemHighlightType.WEAK_WARNING,
                range,
            )
        }

        for (child in runCatching { scope.childScopes }.getOrNull() ?: emptyList()) {
            checkScope(child, holder, file, doc)
        }
    }

    companion object {
        private val EXPECTED_PREFIXES: Map<String, List<String>> =
            mapOf(
                "INTEGER" to listOf("i", "n"),
                "INT64" to listOf("i", "n"),
                "CHARACTER" to listOf("c", "s"),
                "LONGCHAR" to listOf("lc", "c"),
                "LOGICAL" to listOf("l", "b"),
                "DECIMAL" to listOf("d", "f"),
                "DATE" to listOf("d", "dt"),
                "DATETIME" to listOf("dt"),
                "DATETIME-TZ" to listOf("dt", "dtz"),
                "HANDLE" to listOf("h"),
                "RAW" to listOf("r"),
                "RECID" to listOf("r"),
                "ROWID" to listOf("ri"),
            )

        private val GLOBAL_PREFIXES = listOf("g_", "gi", "gc", "gl", "gd", "gh")
    }
}
