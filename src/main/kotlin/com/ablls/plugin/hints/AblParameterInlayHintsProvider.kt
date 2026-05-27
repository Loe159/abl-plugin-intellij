package com.ablls.plugin.hints

import com.ablls.plugin.core.AblProjectAnalysisService
import com.ablls.plugin.language.AblLanguage
import com.ablls.plugin.parser.AblTokenTypes
import com.intellij.codeInsight.hints.ChangeListener
import com.intellij.codeInsight.hints.FactoryInlayHintsCollector
import com.intellij.codeInsight.hints.ImmediateConfigurable
import com.intellij.codeInsight.hints.InlayHintsCollector
import com.intellij.codeInsight.hints.InlayHintsProvider
import com.intellij.codeInsight.hints.InlayHintsSink
import com.intellij.codeInsight.hints.NoSettings
import com.intellij.codeInsight.hints.SettingsKey
import com.intellij.codeInsight.hints.presentation.PresentationFactory
import com.intellij.openapi.components.service
import com.intellij.openapi.editor.Document
import com.intellij.openapi.editor.Editor
import com.intellij.psi.PsiElement
import com.intellij.psi.PsiFile
import org.antlr.v4.runtime.Token
import org.prorefactor.treeparser.TreeParserSymbolScope
import javax.swing.JComponent
import javax.swing.JPanel

/**
 * Inlay hints de noms de paramètres pour les appels de fonctions ABL.
 *
 * Affiche `paramName:` avant chaque argument d'un appel de fonction ou de procédure
 * dont la signature est connue du scope sémantique.
 *
 * Ne s'active pas pour les arguments précédés de INPUT/OUTPUT/INPUT-OUTPUT
 * (déjà explicites dans le source ABL).
 */
@Suppress("UnstableApiUsage")
class AblParameterInlayHintsProvider : InlayHintsProvider<NoSettings> {
    override val key: SettingsKey<NoSettings> = SettingsKey("abl.parameter.hints")
    override val name: String = "Call parameter name hints"
    override val previewText: String =
        """
        FUNCTION max RETURNS INTEGER(INPUT a AS INTEGER, INPUT b AS INTEGER):
          RETURN IF a > b THEN a ELSE b.
        END FUNCTION.
        DEFINE VARIABLE x AS INTEGER NO-UNDO.
        x = max(5, 3).
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
        sink: InlayHintsSink,
    ): InlayHintsCollector? {
        if (file.language != AblLanguage) return null
        val uri = file.virtualFile?.url ?: return null
        val service = file.project.service<AblProjectAnalysisService>()
        val scope = service.getSemanticResult(uri)?.rootScope ?: return null
        val tokens = service.analyzeFile(file.text, uri).tokens ?: return null

        val routineParams = buildRoutineParamMap(scope)
        if (routineParams.isEmpty()) return null

        val hintMap = buildHintMap(tokens, routineParams, editor.document)
        if (hintMap.isEmpty()) return null

        return AblParamHintsCollector(editor, hintMap)
    }

    // ─── Construction de la map routineName → [nomParam1, nomParam2, …] ──────

    private fun buildRoutineParamMap(scope: TreeParserSymbolScope): Map<String, List<String>> {
        val map = mutableMapOf<String, List<String>>()
        collectRoutineParamsFromScope(scope, map)
        return map
    }

    private fun collectRoutineParamsFromScope(
        scope: TreeParserSymbolScope,
        map: MutableMap<String, List<String>>,
    ) {
        for (routine in runCatching { scope.routines }.getOrNull() ?: emptyList()) {
            val params = runCatching { routine.parameters }.getOrNull() ?: continue
            if (params.isEmpty()) continue
            val labels =
                params.mapNotNull { param ->
                    runCatching { param.javaClass.getMethod("getName").invoke(param) as? String }
                        .getOrNull()
                        ?.takeIf { it.isNotBlank() }
                }
            if (labels.isNotEmpty()) map[routine.name.uppercase()] = labels
        }
        for (child in runCatching { scope.childScopes }.getOrNull() ?: emptyList()) {
            collectRoutineParamsFromScope(child, map)
        }
    }

    // ─── Scan du token stream pour trouver les sites d'appel ─────────────────

    @Suppress("CyclomaticComplexMethod", "NestedBlockDepth")
    private fun buildHintMap(
        tokens: org.antlr.v4.runtime.CommonTokenStream,
        routineParams: Map<String, List<String>>,
        document: Document,
    ): Map<Int, String> {
        val hintMap = mutableMapOf<Int, String>()
        val size = tokens.size()

        var i = 0
        while (i < size) {
            val tok = tokens.get(i)
            if (tok.channel != Token.DEFAULT_CHANNEL) {
                i++
                continue
            }

            val routineName = tok.text?.uppercase()
            val params = if (routineName != null) routineParams[routineName] else null
            if (params == null) {
                i++
                continue
            }

            // Le prochain token du default channel doit être "("
            var j = i + 1
            while (j < size && tokens.get(j).channel != Token.DEFAULT_CHANNEL) j++
            if (j >= size || tokens.get(j).text != "(") {
                i++
                continue
            }

            // Analyser les arguments
            j++ // dépasse "("
            var depth = 1
            var argIndex = 0
            var argFirstToken: Token? = null
            var argHasDirection = false

            while (j < size && depth > 0) {
                val t = tokens.get(j)
                if (t.channel == Token.DEFAULT_CHANNEL) {
                    val txt = t.text ?: ""
                    when {
                        txt == "(" -> depth++
                        txt == ")" -> {
                            depth--
                            if (depth == 0) {
                                val ft = argFirstToken
                                if (ft != null && !argHasDirection && argIndex < params.size) {
                                    val offset = tokenOffset(ft, document)
                                    if (offset >= 0) hintMap[offset] = "${params[argIndex]}:"
                                }
                            }
                        }
                        txt == "," && depth == 1 -> {
                            val ft = argFirstToken
                            if (ft != null && !argHasDirection && argIndex < params.size) {
                                val offset = tokenOffset(ft, document)
                                if (offset >= 0) hintMap[offset] = "${params[argIndex]}:"
                            }
                            argIndex++
                            argFirstToken = null
                            argHasDirection = false
                        }
                        depth == 1 && argFirstToken == null -> {
                            argFirstToken = t
                            argHasDirection = txt.uppercase() in DIRECTION_KEYWORDS
                        }
                    }
                }
                j++
            }
            i = j
        }
        return hintMap
    }

    private fun tokenOffset(
        token: Token,
        document: Document,
    ): Int {
        val line = (token.line - 1).coerceAtLeast(0)
        if (line >= document.lineCount) return -1
        return document.getLineStartOffset(line) + token.charPositionInLine
    }

    companion object {
        private val DIRECTION_KEYWORDS =
            setOf(
                "INPUT", "OUTPUT", "INPUT-OUTPUT",
                "BY-VALUE", "BY-REFERENCE", "TABLE", "TABLE-HANDLE", "DATASET", "DATASET-HANDLE",
            )
    }
}

// ─── Collecteur ───────────────────────────────────────────────────────────────

@Suppress("UnstableApiUsage")
private class AblParamHintsCollector(
    editor: Editor,
    private val hintMap: Map<Int, String>,
) : FactoryInlayHintsCollector(editor) {
    private val presentationFactory = PresentationFactory(editor)

    override fun collect(
        element: PsiElement,
        editor: Editor,
        sink: InlayHintsSink,
    ): Boolean {
        if (element.node?.elementType != AblTokenTypes.IDENTIFIER) return true
        val startOffset = element.textRange.startOffset
        val hint = hintMap[startOffset] ?: return true

        val presentation =
            presentationFactory.roundWithBackgroundAndSmallInset(
                presentationFactory.smallText(hint),
            )
        sink.addInlineElement(startOffset, false, presentation, false)
        return true
    }
}
