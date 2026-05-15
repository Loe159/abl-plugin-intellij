package com.ablls.plugin.highlight

import com.ablls.plugin.core.AblProjectAnalysisService
import com.ablls.plugin.language.AblLanguage
import com.ablls.plugin.parser.AblTokenTypes
import com.intellij.codeInsight.daemon.LineMarkerInfo
import com.intellij.codeInsight.daemon.LineMarkerProvider
import com.intellij.icons.AllIcons
import com.intellij.openapi.components.service
import com.intellij.openapi.editor.markup.GutterIconRenderer
import com.intellij.psi.PsiElement
import com.intellij.psi.PsiFile
import org.antlr.v4.runtime.Token

/**
 * Gutter icons pour les méthodes de test ABLUnit.
 *
 * Détecte les méthodes annotées @Test, @Before, @After dans un fichier ABL
 * (classes héritant d'OpenEdge.ABLUnit.Runner.TestRunner) et affiche
 * une icône Run verte dans la gouttière pour chacune.
 */
class AblTestRunLineMarkerProvider : LineMarkerProvider {

    override fun getLineMarkerInfo(element: PsiElement): LineMarkerInfo<*>? {
        if (element.firstChild != null) return null  // leaf elements only
        if (element.language != AblLanguage) return null
        if (element.node?.elementType != AblTokenTypes.IDENTIFIER) return null

        val text = element.text ?: return null
        if (!text.equals("METHOD", ignoreCase = true)) return null

        // Vérifier qu'il y a un @Test, @Before ou @After sur la ligne précédente
        val file = element.containingFile ?: return null
        val offset = element.textRange.startOffset
        if (offset == 0) return null

        val docText = file.text
        val lineStart = docText.lastIndexOf('\n', offset - 1) + 1
        val prevLineStart = docText.lastIndexOf('\n', lineStart - 2) + 1
        val prevLine = docText.substring(prevLineStart, lineStart).trim()

        val annotation = TEST_ANNOTATIONS.firstOrNull { prevLine.equals(it, ignoreCase = true) }
            ?: return null

        val icon = when {
            annotation.equals("@Test", ignoreCase = true) -> AllIcons.RunConfigurations.TestState.Run
            annotation.equals("@Before", ignoreCase = true) ||
            annotation.equals("@After", ignoreCase = true)  -> AllIcons.RunConfigurations.TestState.Yellow2
            else -> AllIcons.RunConfigurations.TestState.Run
        }

        return LineMarkerInfo(
            element,
            element.textRange,
            icon,
            { "ABLUnit ${annotation.removePrefix("@")} method" },
            null,
            GutterIconRenderer.Alignment.RIGHT
        ) { "ABLUnit ${annotation.removePrefix("@")} method" }
    }

    companion object {
        private val TEST_ANNOTATIONS = listOf("@Test", "@Before", "@After", "@BeforeClass", "@AfterClass")
    }
}
