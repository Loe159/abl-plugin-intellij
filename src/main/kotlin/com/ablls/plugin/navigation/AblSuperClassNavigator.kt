package com.ablls.plugin.navigation

import com.ablls.plugin.core.AblProjectAnalysisService
import com.ablls.plugin.core.AblSymbol
import com.ablls.plugin.language.AblLanguage
import com.intellij.codeInsight.navigation.actions.GotoSuperAction
import com.intellij.lang.LanguageCodeInsightActionHandler
import com.intellij.openapi.components.service
import com.intellij.openapi.editor.Editor
import com.intellij.openapi.fileEditor.OpenFileDescriptor
import com.intellij.openapi.project.Project
import com.intellij.openapi.vfs.VirtualFileManager
import com.intellij.psi.PsiFile

/**
 * Navigate to Super Class / implemented interface (Ctrl+U) pour ABL.
 *
 * Depuis une classe ABL héritant d'une autre classe :
 *   CLASS MyClass INHERITS ParentClass:
 * place le curseur sur `ParentClass` et appuie sur Ctrl+U → ouvre ParentClass.cls.
 *
 * Stratégie :
 *   1. Lire le texte source autour du curseur pour trouver la classe courante.
 *   2. Trouver le mot-clé INHERITS ou IMPLEMENTS dans la déclaration.
 *   3. Extraire le nom de la super-classe et naviguer vers son symbole.
 */
class AblSuperClassNavigator : LanguageCodeInsightActionHandler {

    override fun isValidFor(editor: Editor, file: PsiFile): Boolean =
        file.language == AblLanguage && findSuperClassName(editor, file) != null

    override fun invoke(project: Project, editor: Editor, file: PsiFile) {
        val superName = findSuperClassName(editor, file) ?: return
        val service   = project.service<AblProjectAnalysisService>()

        // Chercher la super-classe dans l'index
        val symbol = service.symbolIndex.findByName(superName, file.virtualFile?.url ?: "")
            .firstOrNull { it.kind == AblSymbol.Kind.CLASS }
            ?: service.symbolIndex.allSymbols()
                .firstOrNull { it.kind == AblSymbol.Kind.CLASS && it.name.endsWith(".$superName", ignoreCase = true) }

        if (symbol != null) {
            navigateTo(project, symbol)
        }
    }

    override fun startInWriteAction(): Boolean = false

    companion object {
        /**
         * Recherche le nom de la super-classe dans le source du fichier.
         * Scanne le texte avant le curseur pour trouver `INHERITS ClassName`.
         */
        fun findSuperClassName(editor: Editor, file: PsiFile): String? {
            val text = file.text
            val inheritsIdx = text.indexOf("INHERITS", ignoreCase = true)
                .takeIf { it >= 0 } ?: text.indexOf("IMPLEMENTS", ignoreCase = true)
                .takeIf { it >= 0 } ?: return null

            val afterKeyword = text.substring(inheritsIdx).substringAfter(" ").trimStart()
            val name = afterKeyword.takeWhile { it.isLetterOrDigit() || it == '.' || it == '-' || it == '_' }
            return name.takeIf { it.isNotBlank() }
        }

        fun navigateTo(project: Project, symbol: AblSymbol) {
            val uri = symbol.uri?.takeIf { !it.startsWith("db://") } ?: return
            val vf  = VirtualFileManager.getInstance().findFileByUrl(uri) ?: return
            val line = (symbol.definitionRange?.startLine ?: 0).coerceAtLeast(0)
            val col  = (symbol.definitionRange?.startCol  ?: 0).coerceAtLeast(0)
            OpenFileDescriptor(project, vf, line, col).navigate(true)
        }
    }
}
