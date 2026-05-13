package com.ablls.plugin.inspections

import com.ablls.plugin.core.AblProjectAnalysisService
import com.ablls.plugin.language.AblLanguage
import com.intellij.codeInspection.*
import com.intellij.openapi.components.service
import com.intellij.psi.PsiDocumentManager
import com.intellij.psi.PsiElementVisitor
import com.intellij.psi.PsiFile
import org.prorefactor.core.ABLNodeType
import org.prorefactor.core.JPNode

/**
 * Inspection : convention de nommage des variables ABL.
 *
 * Signale les variables DEFINE VARIABLE dont le nom ne respecte pas les
 * préfixes conventionnels ABL (Hungarian notation) :
 *   l / b    → LOGICAL (booléen)
 *   i        → INTEGER
 *   c        → CHARACTER
 *   d        → DECIMAL / DATE
 *   dt       → DATETIME / DATETIME-TZ
 *   h        → HANDLE
 *   o        → objet (classe)
 *   tt       → TEMP-TABLE (pour les buffers)
 *
 * Les paramètres et les variables commençant par `_` (convention privée)
 * sont toujours ignorés. Les variables d'itération simples (i, j, k…) également.
 *
 * Niveau : WEAK_WARNING (information uniquement, car les conventions varient).
 */
class AblNamingConventionInspection : LocalInspectionTool() {

    override fun getDisplayName()      = "Variable name does not follow ABL naming conventions"
    override fun getShortName()        = "AblNamingConvention"
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

                for (defNode in topNode.queryStateHead(ABLNodeType.DEFINE)) {
                    if (defNode.hasProparseDirective("NOANALYSIS")) continue

                    // Chercher le nœud VARIABLE (ou VAR) dans le statement DEFINE
                    val varNode  = defNode.query(ABLNodeType.VARIABLE).firstOrNull() ?: continue
                    val nameNode = findNameAfterVariable(varNode) ?: continue
                    val name     = nameNode.text?.takeIf { it.isNotBlank() } ?: continue

                    // Ignorer les conventions spéciales
                    if (name.startsWith("_")) continue
                    if (name.length == 1) continue  // variables mono-lettre (i, j, k…)
                    if (name.startsWith("g_") || name.startsWith("gi") || name.startsWith("gc") ||
                        name.startsWith("gl") || name.startsWith("gd") || name.startsWith("gh")) continue  // globales

                    // Détecter le type de données (rechercher le nœud AS TYPE)
                    val dataType = extractDataType(defNode)?.uppercase() ?: continue

                    val expectedPrefix = EXPECTED_PREFIXES[dataType] ?: continue  // type non conventionné
                    val hasGoodPrefix  = expectedPrefix.any { name.startsWith(it, ignoreCase = true) }

                    if (!hasGoodPrefix) {
                        val suggestedPrefix = expectedPrefix.first()
                        val range = AblInspectionHelper.toRange(doc, nameNode.line, nameNode.column, name.length)
                        holder.registerProblem(
                            file,
                            "Variable '$name' of type $dataType should start with '$suggestedPrefix' (convention: ${expectedPrefix.joinToString("/") { "'$it'" }})",
                            ProblemHighlightType.WEAK_WARNING,
                            range
                        )
                    }
                }
            }
        }

    companion object {
        // Type ABL → liste de préfixes acceptés (premier = préfixe recommandé)
        private val EXPECTED_PREFIXES: Map<String, List<String>> = mapOf(
            "INTEGER"      to listOf("i", "n"),
            "INT64"        to listOf("i", "n"),
            "CHARACTER"    to listOf("c", "s"),
            "LONGCHAR"     to listOf("lc", "c"),
            "LOGICAL"      to listOf("l", "b"),
            "DECIMAL"      to listOf("d", "f"),
            "DATE"         to listOf("d", "dt"),
            "DATETIME"     to listOf("dt"),
            "DATETIME-TZ"  to listOf("dt", "dtz"),
            "HANDLE"       to listOf("h"),
            "RAW"          to listOf("r"),
            "RECID"        to listOf("r"),
            "ROWID"        to listOf("ri"),
        )

        private fun findNameAfterVariable(varNode: JPNode): JPNode? {
            // Le nom de la variable est le premier enfant du nœud VARIABLE
            return varNode.firstChild
        }

        private fun extractDataType(defNode: JPNode): String? {
            // Chercher le nœud AS puis le token de type
            var node = defNode.firstChild
            var foundAs = false
            while (node != null) {
                if (!foundAs && node.nodeType == ABLNodeType.AS) {
                    foundAs = true
                } else if (foundAs) {
                    val txt = node.text?.uppercase() ?: ""
                    if (txt.isNotBlank() && txt != ".") return txt
                }
                node = node.nextSibling
            }
            return null
        }
    }
}
