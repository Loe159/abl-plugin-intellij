package com.ablls.plugin.coverage

import com.ablls.plugin.language.AblLanguage
import com.ablls.plugin.parser.AblTokenTypes
import com.intellij.codeInsight.daemon.LineMarkerInfo
import com.intellij.codeInsight.daemon.LineMarkerProvider
import com.intellij.icons.AllIcons
import com.intellij.openapi.components.service
import com.intellij.openapi.editor.markup.GutterIconRenderer
import com.intellij.psi.PsiElement

/**
 * Gouttière de couverture de code ABL.
 *
 * Affiche une icône verte (✓) sur les lignes couvertes et rouge (✗)
 * sur les lignes non couvertes après chargement d'un fichier .prof.
 *
 * S'active uniquement si des données de couverture sont chargées.
 */
class AblCoverageLineMarkerProvider : LineMarkerProvider {

    override fun getLineMarkerInfo(element: PsiElement): LineMarkerInfo<*>? {
        if (element.firstChild != null) return null  // leaf elements only
        if (element.language != AblLanguage) return null

        // Seulement sur les tokens de début de statement (IDENTIFIER, keywords)
        val type = element.node?.elementType ?: return null
        if (type == AblTokenTypes.WHITE_SPACE ||
            type == AblTokenTypes.LINE_COMMENT ||
            type == AblTokenTypes.BLOCK_COMMENT) return null

        val file    = element.containingFile ?: return null
        val vf      = file.virtualFile ?: return null
        val service = element.project.service<AblCoverageService>()

        if (!service.hasCoverage()) return null

        // Vérifier si c'est le premier token d'une ligne
        val doc = com.intellij.openapi.editor.EditorFactory.getInstance()
            .editors(element.containingFile?.viewProvider?.document ?: return null)
            .findFirst().orElse(null)?.document ?: return null

        val lineNum = doc.getLineNumber(element.textRange.startOffset)
        val lineStart = doc.getLineStartOffset(lineNum)

        // N'afficher que pour le premier élément non-whitespace de chaque ligne
        var prevSib = element.prevSibling
        while (prevSib != null) {
            val prevType = prevSib.node?.elementType
            if (prevType != AblTokenTypes.WHITE_SPACE &&
                prevType != AblTokenTypes.LINE_COMMENT) {
                val prevLine = doc.getLineNumber(prevSib.textRange.startOffset)
                if (prevLine == lineNum) return null  // pas le premier de la ligne
            }
            prevSib = prevSib.prevSibling
        }

        val isCovered = service.isLineCovered(vf.path, lineNum + 1)  // 1-based
            ?: return null  // pas de données pour ce fichier

        val icon = if (isCovered) AllIcons.RunConfigurations.TestState.Green2
                   else AllIcons.RunConfigurations.TestState.Red2
        val tooltip = if (isCovered) "Line covered" else "Line not covered"

        return LineMarkerInfo(
            element,
            element.textRange,
            icon,
            { tooltip },
            null,
            GutterIconRenderer.Alignment.LEFT
        ) { tooltip }
    }
}
