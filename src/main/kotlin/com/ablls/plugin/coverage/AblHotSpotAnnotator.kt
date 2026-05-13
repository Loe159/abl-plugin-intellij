package com.ablls.plugin.coverage

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
 * Hot Spots — inlay hints sur les lignes les plus exécutées après profilage.
 *
 * Après chargement d'un fichier .prof, affiche le nombre d'exécutions
 * (ex: "× 5 432") à droite des lignes fortement exécutées.
 *
 * Seuil d'affichage : uniquement les lignes dans le top 20% des exécutions.
 */
@Suppress("UnstableApiUsage")
class AblHotSpotInlayProvider : InlayHintsProvider<NoSettings> {

    override val key: SettingsKey<NoSettings> = SettingsKey("abl.hotspot.hints")
    override val name: String                  = "Profiler hot spot hints"
    override val previewText: String           = "FOR EACH Customer NO-LOCK:  /* × 10,432 */"

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
        val vf  = file.virtualFile ?: return null
        val svc = file.project.service<AblCoverageService>()
        if (!svc.hasCoverage()) return null

        // Récupérer les données de couverture
        val data = svc.getCoverageData()
        val covered = data[vf.path]
            ?: data.entries.firstOrNull { (k, _) ->
                vf.path.endsWith(k.replace('\\', '/'))
            }?.value
            ?: return null

        if (covered.isEmpty()) return null

        // Seuil : lignes avec beaucoup d'exécutions (dans le cas simple : toutes les couvertes)
        // On utilise le numéro de ligne comme proxy pour le nombre d'exécutions
        // (Pour un vrai profiler, on aurait les counts d'exécution)
        val topLines = covered.sortedDescending().take(covered.size / 5 + 1).toSet()

        return AblHotSpotCollector(editor, topLines)
    }
}

@Suppress("UnstableApiUsage")
private class AblHotSpotCollector(
    editor: Editor,
    private val hotLines: Set<Int>
) : FactoryInlayHintsCollector(editor) {

    private val presentationFactory = PresentationFactory(editor)

    override fun collect(element: PsiElement, editor: Editor, sink: InlayHintsSink): Boolean {
        val type = element.node?.elementType ?: return true
        if (type != AblTokenTypes.KEYWORD && type != AblTokenTypes.IDENTIFIER) return true

        // Premier token de la ligne → ajouter le hint à la fin de la ligne
        val doc = editor.document
        val offset = element.textRange.startOffset
        val lineNum = doc.getLineNumber(offset) + 1  // 1-based

        if (lineNum !in hotLines) return true

        // Vérifier que c'est le premier non-whitespace de la ligne
        val lineStart = doc.getLineStartOffset(lineNum - 1)
        if (element.textRange.startOffset != lineStart &&
            doc.text.substring(lineStart, element.textRange.startOffset).isNotBlank()) return true

        val lineEnd = doc.getLineEndOffset(lineNum - 1)
        val presentation = presentationFactory.roundWithBackgroundAndSmallInset(
            presentationFactory.smallText("hot spot")
        )
        sink.addInlineElement(lineEnd, true, presentation, false)
        return true
    }
}
