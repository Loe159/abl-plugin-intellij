package com.ablls.plugin.hints

import com.ablls.plugin.core.AblProjectAnalysisService
import com.ablls.plugin.language.AblLanguage
import com.ablls.plugin.parser.AblTokenTypes
import com.intellij.codeInsight.hints.*
import com.intellij.codeInsight.hints.presentation.PresentationFactory
import com.intellij.openapi.components.service
import com.intellij.openapi.editor.Editor
import com.intellij.psi.PsiElement
import com.intellij.psi.PsiFile
import javax.swing.JComponent
import javax.swing.JPanel

/**
 * Inlay hints de type pour ABL.
 *
 * Affiche `: TYPE` après chaque identifiant dont le type est résolu
 * par le scope sémantique (TreeParserSymbolScope).
 *
 * Cas exclus pour éviter la redondance :
 *  - L'identifiant qui suit immédiatement les mots-clés VARIABLE / PARAMETER
 *    (déclaration — le type est déjà visible via `AS TYPE`)
 */
@Suppress("UnstableApiUsage")
class AblTypeInlayHintsProvider : InlayHintsProvider<NoSettings> {

    override val key: SettingsKey<NoSettings> = SettingsKey("abl.type.hints")
    override val name: String                  = "Variable type hints"
    override val previewText: String           = "DEFINE VARIABLE cName AS CHARACTER NO-UNDO.\ncName = \"Alice\"."

    override fun createSettings(): NoSettings = NoSettings()

    override fun createConfigurable(settings: NoSettings): ImmediateConfigurable =
        object : ImmediateConfigurable {
            override fun createComponent(listener: ChangeListener): JComponent = JPanel()
        }

    override fun getCollectorFor(
        file: PsiFile,
        editor: Editor,
        settings: NoSettings,
        sink: InlayHintsSink
    ): InlayHintsCollector? {
        if (file.language != AblLanguage) return null
        val uri = file.virtualFile?.url ?: return null
        val scope = file.project.service<AblProjectAnalysisService>()
            .getSemanticResult(uri)?.rootScope ?: return null

        // Construire une map nom→type depuis le scope sémantique
        val typeMap = mutableMapOf<String, String>()
        try {
            for (v in scope.variables) {
                val type = v.dataType?.toString()?.takeIf { it.isNotBlank() && it != "UNKNOWN" } ?: continue
                typeMap[v.name.uppercase()] = type
            }
            for (child in scope.childScopes) {
                for (v in child.variables) {
                    val type = v.dataType?.toString()?.takeIf { it.isNotBlank() && it != "UNKNOWN" } ?: continue
                    typeMap[v.name.uppercase()] = type
                }
            }
        } catch (_: Exception) {}

        if (typeMap.isEmpty()) return null
        return AblTypeHintsCollector(editor, typeMap)
    }
}

// ─── Collecteur ───────────────────────────────────────────────────────────────

@Suppress("UnstableApiUsage")
private class AblTypeHintsCollector(
    editor: Editor,
    private val typeMap: Map<String, String>
) : FactoryInlayHintsCollector(editor) {

    private val presentationFactory = PresentationFactory(editor)

    override fun collect(element: PsiElement, editor: Editor, sink: InlayHintsSink): Boolean {
        if (element.node?.elementType != AblTokenTypes.IDENTIFIER) return true

        val name = element.text.trim()
        val type = typeMap[name.uppercase()] ?: return true

        // Ne pas annoter la ligne de déclaration (après VARIABLE / PARAMETER)
        if (isDefinitionSite(element)) return true

        val presentation = presentationFactory.roundWithBackgroundAndSmallInset(
            presentationFactory.smallText(": $type")
        )
        sink.addInlineElement(
            element.textRange.endOffset,
            /* relatesToPrecedingText = */ true,
            presentation,
            /* placeAfterIfSame = */ false
        )
        return true
    }

    /**
     * Retourne true si le token est le nom d'un symbole dans sa déclaration
     * (précédé par VARIABLE, PARAMETER, PROCEDURE, FUNCTION, METHOD, CLASS…).
     */
    private fun isDefinitionSite(element: PsiElement): Boolean {
        var prev = element.prevSibling
        while (prev != null) {
            val text = prev.text?.trim()
            if (text.isNullOrBlank()) { prev = prev.prevSibling; continue }
            return text.uppercase() in DEFINITION_KEYWORDS
        }
        return false
    }

    companion object {
        private val DEFINITION_KEYWORDS = setOf(
            "VARIABLE", "PARAMETER", "PROCEDURE", "FUNCTION", "METHOD",
            "CLASS", "INTERFACE", "ENUM", "TEMP-TABLE", "DATASET",
            "QUERY", "BUFFER", "STREAM", "PROPERTY", "EVENT", "CONSTRUCTOR", "DESTRUCTOR"
        )
    }
}
