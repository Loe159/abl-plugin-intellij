package com.ablls.plugin.intentions

import com.ablls.plugin.core.AblProjectAnalysisService
import com.ablls.plugin.core.AblSymbol
import com.ablls.plugin.language.AblLanguage
import com.intellij.codeInsight.intention.IntentionAction
import com.intellij.openapi.components.service
import com.intellij.openapi.editor.Editor
import com.intellij.openapi.project.Project
import com.intellij.psi.PsiFile

/**
 * Intention Action : "Add USING statement for class"
 *
 * Quand le curseur est sur un nom de classe non qualifié qui est indexé dans
 * le projet mais pas encore importé, propose d'ajouter un USING au début du fichier.
 *
 * Exemple :
 *   DEFINE VARIABLE obj AS CustomerManager NO-UNDO.
 *   → Alt+Entrée → "Add USING com.mypackage.CustomerManager."
 */
class AblAddUsingIntention : IntentionAction {

    override fun getText()            = "Add USING statement"
    override fun getFamilyName()      = "ABL USING"
    override fun startInWriteAction() = true

    private var foundClassName: String? = null
    private var foundFullName: String?  = null

    override fun isAvailable(project: Project, editor: Editor?, file: PsiFile?): Boolean {
        if (file?.language != AblLanguage) return false
        editor ?: return false

        val offset = editor.caretModel.offset
        val element = file.findElementAt(offset) ?: return false
        val name = element.text.trim().takeIf { it.isNotBlank() && it[0].isUpperCase() } ?: return false
        if (name.length < 3) return false

        val service = project.service<AblProjectAnalysisService>()
        val uri = file.virtualFile?.url ?: return false

        // Chercher dans l'index les classes portant ce nom court
        val classSymbols = service.symbolIndex.findByName(name, uri)
            .filter { it.kind == AblSymbol.Kind.CLASS && it.name.contains('.') }

        if (classSymbols.isEmpty()) return false

        // Vérifier qu'aucun USING ne l'importe déjà
        val text = file.text
        val alreadyImported = text.lines().any { line ->
            line.trim().uppercase().startsWith("USING ") &&
            line.contains(name, ignoreCase = true)
        }
        if (alreadyImported) return false

        foundClassName = name
        foundFullName  = classSymbols.first().name
        return true
    }

    override fun invoke(project: Project, editor: Editor?, file: PsiFile?) {
        editor ?: return
        file ?: return
        if (file.language != AblLanguage) return

        val fullName = foundFullName ?: return
        val doc = editor.document
        val text = doc.text

        // Trouver la position pour insérer le USING (après les USING existants ou au début)
        val lines = text.lines()
        var insertLine = 0
        for ((idx, line) in lines.withIndex()) {
            val trimmed = line.trim().uppercase()
            if (trimmed.startsWith("USING ") || trimmed.startsWith("/*") || trimmed.startsWith("//")) {
                insertLine = idx + 1
            } else if (trimmed.isNotBlank()) {
                break
            }
        }

        val insertOffset = if (insertLine < lines.size) {
            var offset = 0
            for (i in 0 until insertLine) {
                offset += lines[i].length + 1  // +1 for newline
            }
            offset
        } else 0

        doc.insertString(insertOffset, "USING $fullName.\n")
    }
}
