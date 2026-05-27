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
 * Deux cas gérés :
 *   1. La méthode courante OVERRIDE une méthode parente (flèche ↑ vers superclasse)
 *      → icône "implements" — clic navigue vers la méthode parente
 *   2. La méthode courante EST overridée par des sous-classes (flèche ↓)
 *      → icône "overriding" — clic navigue vers le premier override
 *
 * La détection est scope-aware : utilise les INHERITS stockés dans [AblSymbol.dataType]
 * par [AblSymbolCollector] pour ne marquer que les méthodes réellement liées par héritage.
 */
class AblOverridingMethodsProvider : LineMarkerProvider {
    override fun getLineMarkerInfo(element: PsiElement): LineMarkerInfo<*>? {
        if (element.firstChild != null) return null // leaf elements only
        if (element.language != AblLanguage) return null
        if (element.node?.elementType != AblTokenTypes.KEYWORD) return null

        val text = element.text.trim().uppercase()
        if (text != "METHOD" && text != "OVERRIDE") return null

        val file = element.containingFile ?: return null
        val afterKeyword =
            file.text.substring(element.textRange.startOffset)
                .substringAfter(text).trim()
        val methodNameMatch = Regex("""(\w+)\s*\(""").find(afterKeyword) ?: return null
        val methodName = methodNameMatch.groupValues[1]

        val project = element.project
        val service = project.service<AblProjectAnalysisService>()
        val uri = file.virtualFile?.url ?: return null

        // Trouver la classe courante (la classe dont ce fichier est l'implémentation)
        val currentClassSym =
            service.symbolIndex.getSymbolsForFile(uri)
                .firstOrNull { it.kind == AblSymbol.Kind.CLASS }

        // ── Cas 1 : méthode parente dans la superclasse ───────────────────────
        if (currentClassSym != null) {
            val parentName = extractInherits(currentClassSym.dataType)
            if (parentName != null) {
                val parentMethod =
                    service.symbolIndex.findByName("$parentName:$methodName", "")
                        .firstOrNull { it.kind == AblSymbol.Kind.METHOD }
                        ?: service.symbolIndex.allSymbols().firstOrNull { sym ->
                            sym.kind == AblSymbol.Kind.METHOD &&
                                sym.name.substringAfterLast(':').equals(methodName, ignoreCase = true) &&
                                sym.name.substringBefore(':').equals(parentName, ignoreCase = true)
                        }
                if (parentMethod != null) {
                    return LineMarkerInfo(
                        element,
                        element.textRange,
                        AllIcons.Gutter.ImplementingMethod,
                        { "Overrides ${parentMethod.name} in $parentName" },
                        { _, _ -> navigate(project, parentMethod) },
                        GutterIconRenderer.Alignment.LEFT,
                    ) { "Overrides method in parent class" }
                }
            }
        }

        // ── Cas 2 : sous-classes qui overrident cette méthode ─────────────────
        val currentClassName = currentClassSym?.name ?: return null
        val subclasses =
            service.symbolIndex.allSymbols()
                .filter { sym ->
                    sym.kind == AblSymbol.Kind.CLASS &&
                        extractInherits(sym.dataType).equals(currentClassName, ignoreCase = true)
                }
                .map { it.name.uppercase() }
                .toSet()

        val overrides =
            service.symbolIndex.allSymbols().filter { sym ->
                sym.kind == AblSymbol.Kind.METHOD &&
                    sym.name.substringAfterLast(':').equals(methodName, ignoreCase = true) &&
                    sym.name.substringBefore(':').uppercase() in subclasses
            }
        if (overrides.isEmpty()) return null

        return LineMarkerInfo(
            element,
            element.textRange,
            AllIcons.Gutter.OverridenMethod,
            { "Overridden in ${overrides.size} sub-class(es)" },
            { _, _ -> navigate(project, overrides.first()) },
            GutterIconRenderer.Alignment.LEFT,
        ) { "Method is overridden in sub-classes" }
    }

    private fun navigate(
        project: com.intellij.openapi.project.Project,
        symbol: AblSymbol,
    ) {
        val vf =
            com.intellij.openapi.vfs.VirtualFileManager.getInstance()
                .findFileByUrl(symbol.uri ?: return) ?: return
        val line = (symbol.definitionRange?.startLine ?: 0).coerceAtLeast(0)
        com.intellij.openapi.fileEditor.OpenFileDescriptor(project, vf, line, 0).navigate(true)
    }

    private fun extractInherits(dataType: String?): String? {
        dataType ?: return null
        val idx = dataType.indexOf("INHERITS", ignoreCase = true)
        if (idx < 0) return null
        return dataType.substring(idx + "INHERITS".length)
            .trimStart()
            .takeWhile { it.isLetterOrDigit() || it == '.' || it == '_' || it == '-' }
            .takeIf { it.isNotBlank() }
    }
}
