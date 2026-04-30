package com.ablls.plugin.inspections

import com.ablls.plugin.core.AblProjectAnalysisService
import com.ablls.plugin.language.AblLanguage
import com.ablls.plugin.project.OpenEdgeProjectService
import com.intellij.codeInspection.*
import com.intellij.openapi.components.service
import com.intellij.psi.PsiDocumentManager
import com.intellij.psi.PsiElementVisitor
import com.intellij.psi.PsiFile
import org.prorefactor.core.ABLNodeType

/**
 * Inspection : référence à une table sans préfixe de base de données (dbname.Table)
 * dans un environnement multi-bases.
 *
 * Activée uniquement si le projet déclare plusieurs connexions de base de données
 * dans openedge-project.json (databases.size > 1).
 *
 * Stratégie : parcours du JPNode tree via query(RECORD_NAME).
 * Un RECORD_NAME qualifié (sports.Customer) a un nœud NAMEDOT comme fils direct
 * (grammaire : filn → identifier ( NAMEDOT identifier )? ).
 * Sans NAMEDOT fils → la table est référencée sans préfixe de base.
 */
class AblMissingSchemaPrefixInspection : LocalInspectionTool() {

    override fun getDisplayName()      = "Table reference without database prefix (multi-db)"
    override fun getShortName()        = "AblMissingSchemaPrefix"
    override fun getGroupDisplayName() = "ABL Security"

    override fun buildVisitor(holder: ProblemsHolder, isOnTheFly: Boolean): PsiElementVisitor =
        object : PsiElementVisitor() {
            override fun visitFile(file: PsiFile) {
                if (file.language != AblLanguage) return

                val projectService = file.project.service<OpenEdgeProjectService>()
                if (projectService.config.databases.size <= 1) return

                val uri     = file.virtualFile?.url ?: return
                val service = file.project.service<AblProjectAnalysisService>()
                val result  = service.analyzeFile(file.text, uri)
                val topNode = result.topNode ?: return
                val doc     = PsiDocumentManager.getInstance(file.project).getDocument(file) ?: return
                val dbNames = projectService.config.databases.map { it.logicalName.uppercase() }.toSet()

                for (recordNode in topNode.query(ABLNodeType.RECORD_NAME)) {
                    val hasPrefix = recordNode.directChildren.any { it.nodeType == ABLNodeType.NAMEDOT }
                    if (hasPrefix) continue

                    val name = recordNode.text?.takeIf { it.isNotBlank() && it.first().isLetter() } ?: continue
                    val range  = AblInspectionHelper.toRange(doc, recordNode.line, recordNode.column, name.length)
                    val dbHint = if (dbNames.size <= 3) " (${dbNames.joinToString(", ")})" else ""
                    holder.registerProblem(
                        file,
                        "Table '$name' referenced without database prefix in multi-db environment$dbHint — use 'dbname.$name'",
                        ProblemHighlightType.WARNING,
                        range
                    )
                }
            }
        }
}
