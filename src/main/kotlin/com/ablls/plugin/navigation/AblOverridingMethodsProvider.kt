package com.ablls.plugin.navigation

import com.ablls.plugin.core.AblProjectAnalysisService
import com.ablls.plugin.core.AblSymbol
import com.ablls.plugin.language.AblLanguage
import com.ablls.plugin.parser.AblTokenTypes
import com.intellij.codeInsight.daemon.LineMarkerInfo
import com.intellij.codeInsight.daemon.LineMarkerProvider
import com.intellij.icons.AllIcons
import com.intellij.openapi.components.service
import com.intellij.openapi.editor.markup.GutterIconRenderer
import com.intellij.psi.PsiElement

/**
 * Navigate to Overriding Methods — icône dans la gouttière.
 *
 * Sur les méthodes d'une classe ABL (METHOD PUBLIC ...) qui sont
 * OVERRIDE, affiche une icône de flèche vers le bas indiquant qu'on peut
 * naviguer vers l'implémentation dans une sous-classe.
 *
 * Détection : cherche d'autres classes dans l'index qui définissent
 * une méthode avec le même nom (qualifiée par `::`).
 */
class AblOverridingMethodsProvider : LineMarkerProvider {

    override fun getLineMarkerInfo(element: PsiElement): LineMarkerInfo<*>? {
        if (element.language != AblLanguage) return null
        if (element.node?.elementType != AblTokenTypes.KEYWORD) return null

        val text = element.text.trim().uppercase()
        if (text != "METHOD" && text != "OVERRIDE") return null

        // Trouver le nom de la méthode (token IDENTIFIER qui suit)
        val file = element.containingFile ?: return null
        val offset = element.textRange.startOffset
        val sourceText = file.text
        val afterKeyword = sourceText.substring(offset).substringAfter(text)
            .trim()
        // Extraire le nom de la méthode : le dernier identifiant avant "("
        val methodNameMatch = Regex("""(\w+)\s*\(""").find(afterKeyword) ?: return null
        val methodName = methodNameMatch.groupValues[1]

        val project = element.project
        val service = project.service<AblProjectAnalysisService>()
        val uri     = file.virtualFile?.url ?: return null

        // Chercher des classes qui ont une méthode avec ce nom dans l'index
        val overrides = service.symbolIndex.allSymbols()
            .filter { sym ->
                sym.kind == AblSymbol.Kind.METHOD &&
                sym.name.substringAfterLast(':').equals(methodName, ignoreCase = true) &&
                sym.uri != uri
            }

        if (overrides.isEmpty()) return null

        return LineMarkerInfo(
            element,
            element.textRange,
            AllIcons.Gutter.OverridenMethod,
            { "Has ${overrides.size} override(s) in sub-classes" },
            { _, _ ->
                // Naviguer vers le premier override
                val first = overrides.first()
                val vf = com.intellij.openapi.vfs.VirtualFileManager.getInstance()
                    .findFileByUrl(first.uri ?: return@LineMarkerInfo) ?: return@LineMarkerInfo
                val line = (first.definitionRange?.startLine ?: 0).coerceAtLeast(0)
                com.intellij.openapi.fileEditor.OpenFileDescriptor(project, vf, line, 0).navigate(true)
            },
            GutterIconRenderer.Alignment.LEFT
        ) { "Has overrides" }
    }
}
