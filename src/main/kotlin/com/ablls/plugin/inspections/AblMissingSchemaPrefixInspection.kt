package com.ablls.plugin.inspections

import com.ablls.plugin.core.AblProjectAnalysisService
import com.ablls.plugin.language.AblLanguage
import com.ablls.plugin.project.OpenEdgeProjectService
import com.intellij.codeInspection.*
import com.intellij.openapi.components.service
import com.intellij.psi.PsiDocumentManager
import com.intellij.psi.PsiElementVisitor
import com.intellij.psi.PsiFile
import org.antlr.v4.runtime.Token
import org.prorefactor.core.ABLNodeType

/**
 * Inspection : référence à une table sans préfixe de base de données (dbname.Table)
 * dans un environnement multi-bases.
 *
 * Activée uniquement si le projet déclare plusieurs connexions de base de données
 * dans openedge-project.json (databases.size > 1), car le préfixe est ambigu seulement
 * dans ce contexte.
 *
 * Stratégie : cherche les patterns FOR EACH/FIND/CAN-FIND suivis d'un nom de table
 * qui ne contient pas de '.'.
 * Cette heuristique est volontairement conservatrice pour éviter les faux positifs.
 */
class AblMissingSchemaPrefixInspection : LocalInspectionTool() {

    override fun getDisplayName()      = "Table reference without database prefix (multi-db)"
    override fun getShortName()        = "AblMissingSchemaPrefix"
    override fun getGroupDisplayName() = "ABL Security"

    override fun buildVisitor(holder: ProblemsHolder, isOnTheFly: Boolean): PsiElementVisitor =
        object : PsiElementVisitor() {
            override fun visitFile(file: PsiFile) {
                if (file.language != AblLanguage) return

                // Seulement pertinent en multi-base
                val projectService = file.project.service<OpenEdgeProjectService>()
                if (projectService.config.databases.size <= 1) return

                val uri     = file.virtualFile?.url ?: return
                val service = file.project.service<AblProjectAnalysisService>()
                val result  = service.analyzeFile(file.text, uri)
                val tokens  = result.tokens ?: return
                val doc     = PsiDocumentManager.getInstance(file.project).getDocument(file) ?: return
                val dbNames = projectService.config.databases.map { it.logicalName.uppercase() }.toSet()

                val size = tokens.size()
                var i = 0
                while (i < size) {
                    val t = tokens.get(i)
                    if (t.channel != Token.DEFAULT_CHANNEL) { i++; continue }
                    val text = t.text?.uppercase() ?: ""

                    if (ABLNodeType.getLiteral(text.lowercase()) !in TABLE_CONTEXT_TYPES) { i++; continue }

                    // Sauter les tokens non-default jusqu'au prochain mot
                    var j = i + 1
                    while (j < size && tokens.get(j).channel != Token.DEFAULT_CHANNEL) j++
                    if (j >= size) break

                    // Ignorer EACH, FIRST, LAST, BUFFER, CURRENT
                    val next = tokens.get(j).text?.uppercase() ?: ""
                    if (ABLNodeType.getLiteral(next.lowercase()) in FOR_QUALIFIER_TYPES) {
                        j++
                        while (j < size && tokens.get(j).channel != Token.DEFAULT_CHANNEL) j++
                    }
                    if (j >= size) break

                    val nameTok  = tokens.get(j)
                    val name     = nameTok.text ?: ""

                    // Vérifier si le prochain token est '.' (présence du préfixe)
                    val hasPrefix = name.contains('.')
                    if (!hasPrefix && name.isNotBlank() && name.first().isLetter()) {
                        // Vérifier si le nom qui suit est un '.' (db.table)
                        var k = j + 1
                        while (k < size && tokens.get(k).channel != Token.DEFAULT_CHANNEL) k++
                        val afterName = if (k < size) tokens.get(k).text else ""
                        if (afterName != ".") {
                            val range = AblInspectionHelper.toRange(doc, nameTok.line, nameTok.charPositionInLine, name.length)
                            val dbHint = if (dbNames.size <= 3) " (${dbNames.joinToString(", ")})" else ""
                            holder.registerProblem(file, "Table '$name' referenced without database prefix in multi-db environment$dbHint — use 'dbname.$name'", ProblemHighlightType.WARNING, range)
                        }
                    }
                    i = j + 1
                }
            }
        }

    companion object {
        // Mots-clés introduisant une référence de table — source de vérité : ABLNodeType
        private val TABLE_CONTEXT_TYPES: Set<ABLNodeType> = java.util.EnumSet.of(
            ABLNodeType.FIND, ABLNodeType.FOR, ABLNodeType.CANFIND,
            ABLNodeType.OPEN, ABLNodeType.PRESELECT
        )
        // Qualificateurs après FOR/FIND ignorés (pointent vers le token de table suivant)
        private val FOR_QUALIFIER_TYPES: Set<ABLNodeType> = java.util.EnumSet.of(
            ABLNodeType.EACH, ABLNodeType.FIRST, ABLNodeType.LAST,
            ABLNodeType.BUFFER, ABLNodeType.CURRENT
        )
    }
}
