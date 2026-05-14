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
import org.prorefactor.treeparser.TreeParserSymbolScope
import javax.swing.JComponent
import javax.swing.JPanel

/**
 * Inlay hints de type de retour pour les appels de fonctions ABL.
 *
 * Affiche `: DECIMAL` après la parenthèse fermante d'un appel de fonction
 * dont le type de retour est connu du scope sémantique.
 *
 * Exemple :
 *   DEFINE VARIABLE dTotal AS DECIMAL NO-UNDO.
 *   dTotal = calcTax(dAmount).   →   dTotal = calcTax(dAmount)./* : DECIMAL */
 *
 * Les routines PROCEDURE (sans retour) et les fonctions retournant CHARACTER
 * dont le nom est déjà explicite sont filtrées pour réduire le bruit.
 */
@Suppress("UnstableApiUsage")
class AblReturnValueInlayHintsProvider : InlayHintsProvider<NoSettings> {

    override val key: SettingsKey<NoSettings> = SettingsKey("abl.return.hints")
    override val name: String                  = "Function return type hints"
    override val previewText: String           = """
        FUNCTION calcTax RETURNS DECIMAL (INPUT dAmount AS DECIMAL):
          RETURN dAmount * 0.2.
        END FUNCTION.
        DEFINE VARIABLE dTotal AS DECIMAL NO-UNDO.
        dTotal = calcTax(100).
    """.trimIndent()

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

        val returnTypes = buildReturnTypeMap(scope)
        if (returnTypes.isEmpty()) return null

        return AblReturnHintsCollector(editor, returnTypes)
    }

    private fun buildReturnTypeMap(scope: TreeParserSymbolScope): Map<String, String> {
        val map = mutableMapOf<String, String>()
        fun addFrom(s: TreeParserSymbolScope) {
            try {
                for (r in s.routines) {
                    val type = runCatching {
                        r.javaClass.getMethod("getReturnDatatype").invoke(r)?.toString()
                    }.getOrNull()?.takeIf { it.isNotBlank() && it != "VOID" && it != "UNKNOWN" } ?: continue
                    map[r.name.uppercase()] = type
                }
                for (child in s.childScopes) addFrom(child)
            } catch (_: Exception) {}
        }
        addFrom(scope)
        return map
    }
}

// ─── Collecteur ───────────────────────────────────────────────────────────────

@Suppress("UnstableApiUsage")
private class AblReturnHintsCollector(
    editor: Editor,
    private val returnTypes: Map<String, String>
) : FactoryInlayHintsCollector(editor) {

    private val pFactory = PresentationFactory(editor)

    override fun collect(element: PsiElement, editor: Editor, sink: InlayHintsSink): Boolean {
        if (element.node?.elementType != AblTokenTypes.IDENTIFIER) return true
        val name = element.text.trim()
        val retType = returnTypes[name.uppercase()] ?: return true

        // Must be followed by '(' — this token is a function call, not a reference
        val next = nextNonWS(element) ?: return true
        if (next.node?.elementType != AblTokenTypes.LPAREN) return true

        // Must NOT be a definition site
        if (isDefinitionSite(element)) return true

        // Find the matching closing parenthesis offset
        val closeOffset = findMatchingClose(element) ?: return true

        val presentation = pFactory.roundWithBackgroundAndSmallInset(
            pFactory.smallText(": $retType")
        )
        sink.addInlineElement(
            closeOffset,
            /* relatesToPrecedingText = */ true,
            presentation,
            /* placeAfterIfSame = */ false
        )
        return true
    }

    /** Walk forward from the LPAREN sibling, counting depth to find the matching RPAREN offset. */
    private fun findMatchingClose(callNameElement: PsiElement): Int? {
        var depth = 0
        var s = nextNonWS(callNameElement)
        while (s != null) {
            when (s.node?.elementType) {
                AblTokenTypes.LPAREN -> depth++
                AblTokenTypes.RPAREN -> {
                    depth--
                    if (depth == 0) return s.textRange.endOffset
                }
            }
            s = s.nextSibling
        }
        return null
    }

    private fun nextNonWS(el: PsiElement): PsiElement? {
        var s = el.nextSibling
        while (s != null && s.text.isBlank()) s = s.nextSibling
        return s
    }

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
            "FUNCTION", "PROCEDURE", "METHOD", "CONSTRUCTOR", "DESTRUCTOR"
        )
    }
}
