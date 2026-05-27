@file:Suppress("ktlint:standard:filename")

package com.ablls.plugin.coverage

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
import com.intellij.openapi.editor.Editor
import com.intellij.psi.PsiElement
import com.intellij.psi.PsiFile
import javax.swing.JComponent
import javax.swing.JPanel

/**
 * Hot Spots — inlay hints sur les lignes les plus exécutées après profilage.
 *
 * Après chargement d'un fichier .prof, affiche le count d'exécution réel
 * (ex: "× 5 432") à droite des lignes dans le top 20% des exécutions du fichier.
 *
 * Utilise [AblCoverageService.topHotLines] qui s'appuie sur les counts réels
 * issus de [AblProfilerParser.parseWithCounts] — pas un proxy par numéro de ligne.
 */
@Suppress("UnstableApiUsage")
class AblHotSpotInlayProvider : InlayHintsProvider<NoSettings> {
    override val key: SettingsKey<NoSettings> = SettingsKey("abl.hotspot.hints")
    override val name: String = "Profiler hot spot hints"
    override val previewText: String = "FOR EACH Customer NO-LOCK:  /* × 10 432 */"

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
        val vf = file.virtualFile ?: return null
        val svc = file.project.service<AblCoverageService>()
        if (!svc.hasCoverage()) return null

        // Top 20% des lignes par count d'exécution réel (au maximum 50 hints par fichier)
        val hotPairs = svc.topHotLines(vf.path, 50)
        if (hotPairs.isEmpty()) return null

        // Calcul du seuil : top 20% = au moins count > max/5
        val maxCount = hotPairs.first().second
        val threshold = maxCount / 5
        val hotMap =
            hotPairs
                .filter { (_, count) -> count >= threshold }
                .toMap()

        if (hotMap.isEmpty()) return null
        return AblHotSpotCollector(editor, hotMap)
    }
}

@Suppress("UnstableApiUsage")
private class AblHotSpotCollector(
    editor: Editor,
    /** numéro de ligne (1-based) → count d'exécution */
    private val hotMap: Map<Int, Int>,
) : FactoryInlayHintsCollector(editor) {
    private val presentationFactory = PresentationFactory(editor)

    override fun collect(
        element: PsiElement,
        editor: Editor,
        sink: InlayHintsSink,
    ): Boolean {
        val type = element.node?.elementType ?: return true
        if (type != AblTokenTypes.KEYWORD && type != AblTokenTypes.IDENTIFIER) return true

        val doc = editor.document
        val offset = element.textRange.startOffset
        val lineNum = doc.getLineNumber(offset) + 1 // 1-based
        val count = hotMap[lineNum] ?: return true

        // Uniquement le premier token non-whitespace de la ligne
        val lineStart = doc.getLineStartOffset(lineNum - 1)
        if (offset != lineStart &&
            doc.text.substring(lineStart, offset).isNotBlank()
        ) {
            return true
        }

        val label = "× %,d".format(count)
        val lineEnd = doc.getLineEndOffset(lineNum - 1)
        val presentation =
            presentationFactory.roundWithBackgroundAndSmallInset(
                presentationFactory.smallText(label),
            )
        sink.addInlineElement(lineEnd, true, presentation, false)
        return true
    }
}
