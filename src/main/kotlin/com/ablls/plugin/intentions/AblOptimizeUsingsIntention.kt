package com.ablls.plugin.intentions

import com.ablls.plugin.language.AblLanguage
import com.intellij.codeInsight.intention.IntentionAction
import com.intellij.openapi.editor.Editor
import com.intellij.openapi.project.Project
import com.intellij.psi.PsiFile

/**
 * Intention Action : "Optimize USING statements"
 *
 * Supprime les déclarations USING dont le type n'est jamais référencé dans le fichier.
 * Disponible dans les fichiers .cls ABL contenant des USING.
 *
 * Algorithme :
 *   1. Collecter toutes les lignes USING et le type court (dernier segment après le point).
 *   2. Pour chaque USING, vérifier si le type court apparaît dans le reste du code.
 *   3. Supprimer les lignes USING inutilisées.
 */
class AblOptimizeUsingsIntention : IntentionAction {
    override fun getText() = "Optimize USING statements (remove unused)"

    override fun getFamilyName() = "ABL USING"

    override fun startInWriteAction() = true

    override fun isAvailable(
        project: Project,
        editor: Editor?,
        file: PsiFile?,
    ): Boolean {
        if (file?.language != AblLanguage) return false
        return file.text.lines().any { it.trim().uppercase().startsWith("USING ") }
    }

    override fun invoke(
        project: Project,
        editor: Editor?,
        file: PsiFile?,
    ) {
        file ?: return
        editor ?: return
        if (file.language != AblLanguage) return

        val doc = editor.document
        val lines = doc.text.lines()

        // Identifier les lignes USING et extraire le nom du type
        data class UsingInfo(val lineIndex: Int, val typeFull: String, val typeShort: String)

        val usings = mutableListOf<UsingInfo>()
        lines.forEachIndexed { idx, line ->
            val trimmed = line.trim()
            if (trimmed.uppercase().startsWith("USING ")) {
                val typeFull = trimmed.substringAfter(" ").trimEnd('.').trim()
                val typeShort = typeFull.substringAfterLast('.')
                if (typeShort.isNotBlank() && typeFull.isNotBlank()) {
                    usings.add(UsingInfo(idx, typeFull, typeShort))
                }
            }
        }

        if (usings.isEmpty()) return

        // Construire le texte sans les lignes USING pour vérifier les usages
        val usingLineIndices = usings.map { it.lineIndex }.toSet()
        val codeWithoutUsings =
            lines.filterIndexed { idx, _ -> idx !in usingLineIndices }
                .joinToString("\n")

        // Trouver les USING inutilisés
        val unusedLines =
            usings.filter { info ->
                // Wildcard USING (e.g. USING Progress.Lang.*) → toujours garder
                if (info.typeShort == "*") return@filter false
                // Vérifier si le type court apparaît dans le code (hors lignes USING)
                !codeWithoutUsings.contains(info.typeShort, ignoreCase = true)
            }.map { it.lineIndex }.sortedDescending() // ordre décroissant pour ne pas décaler

        if (unusedLines.isEmpty()) return

        // Supprimer les lignes en ordre décroissant
        for (lineIdx in unusedLines) {
            val lineStart = doc.getLineStartOffset(lineIdx)
            val lineEnd = if (lineIdx + 1 < doc.lineCount) doc.getLineStartOffset(lineIdx + 1) else doc.textLength
            doc.deleteString(lineStart, lineEnd)
        }
    }
}
