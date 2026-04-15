package com.ablls.plugin.completion

import com.ablls.plugin.language.AblLanguage
import com.intellij.codeInsight.editorActions.TypedHandlerDelegate
import com.intellij.openapi.command.WriteCommandAction
import com.intellij.openapi.editor.Editor
import com.intellij.openapi.project.Project
import com.intellij.psi.PsiFile

/**
 * Gère l'insertion automatique de END. et l'indentation après les mots-clés de bloc ABL.
 *
 * Quand l'utilisateur tape un mot-clé de bloc suivi d'espace ou retour à la ligne,
 * ce handler insère automatiquement :
 * - Le END. correspondant
 * - Une ligne vide indentée entre les deux
 */
class AblAutoEndTypedHandler : TypedHandlerDelegate() {

    /**
     * Mapping des mots-clés de bloc vers leur END. correspondant.
     * Certains blocs ont des END spécifiques (END PROCEDURE, END METHOD, etc.)
     */
    private val BLOCK_KEYWORDS = mapOf(
        "DO" to "END.",
        "FOR" to "END.",
        "REPEAT" to "END.",
        "CASE" to "END CASE.",
        "PROCEDURE" to "END PROCEDURE.",
        "FUNCTION" to "END FUNCTION.",
        "METHOD" to "END METHOD.",
        "CONSTRUCTOR" to "END CONSTRUCTOR.",
        "DESTRUCTOR" to "END DESTRUCTOR.",
        "CLASS" to "END CLASS.",
        "INTERFACE" to "END INTERFACE.",
        "ENUM" to "END ENUM.",
        "TRIGGER" to "END TRIGGER."
    )

    override fun charTyped(c: Char, project: Project, editor: Editor, file: PsiFile): Result {
        if (file.language != AblLanguage) return Result.CONTINUE

        // On ne déclenche que sur espace ou retour à la ligne
        if (c != ' ' && c != '\n' && c != '\t') {
            return Result.CONTINUE
        }

        val document = editor.document
        val offset = editor.caretModel.offset

        // Vérifier qu'on n'est pas au début du document
        if (offset < 2) return Result.CONTINUE

        // Extraire le mot précédent le curseur
        val (word, wordStart) = extractPreviousWord(document, offset - 1)
        if (word.isEmpty()) return Result.CONTINUE

        // Vérifier si c'est un mot-clé de bloc
        val upperWord = word.uppercase()
        val endStatement = BLOCK_KEYWORDS[upperWord]
            ?: BLOCK_KEYWORDS[word]  // Essayer aussi tel quel (pour cas mixtes)
            ?: return Result.CONTINUE

        // Calculer l'indentation actuelle
        val currentLine = document.getLineNumber(offset)
        val lineStartOffset = document.getLineStartOffset(currentLine)
        val currentIndent = calculateIndent(document, lineStartOffset, offset)

        // Vérifier si un END. correspondant existe déjà (éviter les doublons)
        if (hasMatchingEnd(document, offset, endStatement)) {
            return Result.CONTINUE
        }

        // Insérer le bloc avec END.
        WriteCommandAction.runWriteCommandAction(project) {
            val indent = "\t"  // Utiliser une tabulation pour l'indentation interne
            val textToInsert = when (c) {
                '\n' -> {
                    // Si retour à la ligne déjà tapé, insérer après
                    "$indent\n${currentIndent}$endStatement"
                }
                else -> {
                    // Si espace ou tab, insérer bloc complet
                    "\n${currentIndent}$indent\n${currentIndent}$endStatement"
                }
            }

            document.insertString(offset, textToInsert)

            // Positionner le curseur sur la ligne vide indentée
            val newOffset = if (c == '\n') {
                offset + 1 + currentIndent.length + indent.length
            } else {
                offset + 1 + currentIndent.length + indent.length
            }
            editor.caretModel.moveToOffset(newOffset)
        }

        return Result.STOP
    }

    /**
     * Extrait le mot précédent la position donnée.
     * Retourne le mot et sa position de début.
     */
    private fun extractPreviousWord(document: com.intellij.openapi.editor.Document, endPos: Int): Pair<String, Int> {
        val text = document.charsSequence
        var start = endPos

        // Reculer jusqu'au début du mot
        while (start >= 0) {
            val ch = text[start]
            if (!ch.isLetterOrDigit() && ch != '-' && ch != '_') {
                start++
                break
            }
            start--
        }

        if (start < 0) start = 0
        if (start > endPos) return Pair("", 0)

        val word = text.subSequence(start, endPos + 1).toString()
        return Pair(word, start)
    }

    /**
     * Calcule l'indentation (espaces/tabs en début de ligne).
     */
    private fun calculateIndent(document: com.intellij.openapi.editor.Document, lineStart: Int, currentPos: Int): String {
        val text = document.charsSequence
        val indent = StringBuilder()
        var pos = lineStart

        while (pos < currentPos && pos < text.length) {
            val ch = text[pos]
            if (ch == ' ' || ch == '\t') {
                indent.append(ch)
                pos++
            } else {
                break
            }
        }

        return indent.toString()
    }

    /**
     * Vérifie si un END. correspondant existe déjà après la position courante.
     * Évite d'insérer des END. en double.
     */
    private fun hasMatchingEnd(document: com.intellij.openapi.editor.Document, offset: Int, endStatement: String): Boolean {
        val text = document.charsSequence
        val searchLimit = minOf(offset + 500, text.length)  // Chercher dans les 500 caractères suivants
        val endUpper = endStatement.uppercase()

        var pos = offset
        while (pos < searchLimit) {
            // Chercher le début de ligne
            while (pos < searchLimit && text[pos] != '\n') {
                pos++
            }
            if (pos >= searchLimit) break
            pos++  // Passer le \n

            // Sauter les espaces/tabs
            while (pos < searchLimit && (text[pos] == ' ' || text[pos] == '\t')) {
                pos++
            }

            // Vérifier si la ligne commence par END.
            if (pos + endStatement.length <= text.length) {
                val lineStart = text.subSequence(pos, minOf(pos + endStatement.length + 5, text.length))
                    .toString()
                    .trim()
                    .uppercase()
                if (lineStart.startsWith(endUpper) ||
                    lineStart.startsWith("END.") ||
                    (endUpper.startsWith("END ") && lineStart.startsWith(endUpper.split(" ")[0]))) {
                    return true
                }
            }
        }

        return false
    }
}
