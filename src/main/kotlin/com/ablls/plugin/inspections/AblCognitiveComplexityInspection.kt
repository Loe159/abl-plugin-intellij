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
import org.prorefactor.core.ABLNodeType
import org.prorefactor.proparse.CognitiveComplexityListener

/**
 * Inspection : complexité cognitive élevée (mesure RSSW).
 *
 * Utilise [CognitiveComplexityListener] de proparse (Riverside Software) pour mesurer
 * la complexité cognitive de chaque routine ABL (programme principal, PROCEDURE, FUNCTION).
 *
 * L'algorithme est identique à celui de SonarQube OpenEdge :
 *  - +1 par IF/ELSE, CASE, CATCH, FOR, REPEAT, DO imbriqué
 *  - +N (N = niveau d'imbrication) pour les structures imbriquées
 *  - +1 par rupture de séquence logique (AND/OR/XOR)
 *
 * Suppression : ajouter `/* proparse NOANALYSIS */` avant la PROCEDURE ou FUNCTION.
 */
class AblCognitiveComplexityInspection : LocalInspectionTool() {
    override fun getDisplayName() = "High cognitive complexity (RSSW)"

    override fun getShortName() = "AblCognitiveComplexity"

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
                val result = service.analyzeFileSemantic(file.text, uri)
                val topNode = result.topNode ?: return
                if (!topNode.isIStatementBlock) return
                val doc = PsiDocumentManager.getInstance(file.project).getDocument(file) ?: return

                // Corps principal : code en dehors des PROCEDURE/FUNCTION
                // CognitiveComplexityListener ne récurse pas dans EXTERNAL_BLOCK quand
                // ils ne sont pas le routineBlock → pas de double-comptage
                val mainBlock = topNode.asIStatementBlock()
                checkComplexity(mainBlock, "Main program", holder, file, doc)

                // Chaque PROCEDURE et FUNCTION nommée
                for (routineNode in topNode.queryStateHead(ABLNodeType.PROCEDURE, ABLNodeType.FUNCTION)) {
                    if (routineNode.hasProparseDirective("NOANALYSIS")) continue
                    if (!routineNode.isIStatementBlock) continue
                    val nameNode = routineNode.directChildren.firstOrNull { it.nodeType == ABLNodeType.ID }
                    val label = "'${nameNode?.text ?: routineNode.text}'"
                    checkComplexity(routineNode.asIStatementBlock(), label, holder, file, doc)
                }
            }
        }

    private fun checkComplexity(
        block: org.prorefactor.core.nodetypes.IStatementBlock,
        label: String,
        holder: ProblemsHolder,
        file: PsiFile,
        doc: com.intellij.openapi.editor.Document,
    ) {
        val listener = CognitiveComplexityListener(block)
        listener.walkStatementBlock(block)
        val complexity = listener.complexity
        if (complexity <= THRESHOLD) return

        // Mettre en évidence le mot-clé du bloc (PROCEDURE, FUNCTION, ou début de fichier)
        val node = block.asJPNode()
        val keyword = node.text?.takeIf { it.isNotBlank() } ?: "PROGRAM"
        val range = AblInspectionHelper.toRange(doc, node.line, node.column, keyword.length)

        holder.registerProblem(
            file,
            "$label has cognitive complexity $complexity (threshold: $THRESHOLD) — consider splitting into smaller routines",
            ProblemHighlightType.WEAK_WARNING,
            range,
        )
    }

    companion object {
        /** Seuil par défaut — aligné sur la recommandation SonarQube OpenEdge. */
        const val THRESHOLD = 15
    }
}
