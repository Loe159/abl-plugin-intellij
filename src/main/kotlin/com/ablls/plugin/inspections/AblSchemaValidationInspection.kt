package com.ablls.plugin.inspections

import com.ablls.plugin.core.AblProjectAnalysisService
import com.ablls.plugin.core.AblSymbol
import com.ablls.plugin.language.AblLanguage
import com.intellij.codeInspection.*
import com.intellij.openapi.components.service
import com.intellij.psi.PsiDocumentManager
import com.intellij.psi.PsiElementVisitor
import com.intellij.psi.PsiFile
import org.antlr.v4.runtime.Token

/**
 * Inspection : table ou champ référencé dans le code ABL absent du schéma chargé.
 *
 * Vérifie que chaque `Table.Field` référencé dans le source (notation pointée)
 * correspond à un symbole existant dans l'index (alimenté par les fichiers `.df`).
 *
 * Conditions pour signaler :
 *  - Le schéma doit être chargé (au moins une TABLE dans l'index).
 *  - Le pattern `IDENTIFIER.IDENTIFIER` doit correspondre à `Table.Field`
 *    (heuristique : l'identifiant avant le point commence par une majuscule ou est connu comme table).
 *  - Le champ n'est pas trouvé dans l'index sous `Table.Field`.
 *
 * Niveau : WARNING.
 */
class AblSchemaValidationInspection : LocalInspectionTool() {

    override fun getDisplayName()      = "Table or field not found in loaded schema"
    override fun getShortName()        = "AblSchemaValidation"
    override fun getGroupDisplayName() = "ABL Database"

    override fun buildVisitor(holder: ProblemsHolder, isOnTheFly: Boolean): PsiElementVisitor =
        object : PsiElementVisitor() {
            override fun visitFile(file: PsiFile) {
                if (file.language != AblLanguage) return
                val uri     = file.virtualFile?.url ?: return
                val service = file.project.service<AblProjectAnalysisService>()
                val doc     = PsiDocumentManager.getInstance(file.project).getDocument(file) ?: return

                // Ne vérifier que si un schéma est disponible (TABLE symbols dans l'index)
                val knownTables = service.symbolIndex.allSymbols()
                    .filter { it.kind == AblSymbol.Kind.TABLE }
                    .map { it.name.uppercase() }
                    .toSet()

                if (knownTables.isEmpty()) return  // pas de schéma chargé

                val parseResult = service.analyzeFile(file.text, uri)
                val tokens = parseResult.tokens ?: return
                val size   = tokens.size()

                // Scan du flux de tokens pour trouver les patterns Table.Field
                var i = 0
                while (i < size - 2) {
                    val t1 = tokens.get(i)
                    if (t1.channel != Token.DEFAULT_CHANNEL) { i++; continue }

                    val tableName = t1.text
                    if (tableName == null) { i++; continue }

                    // Vérifier que c'est un token identifiant (pas un mot-clé commun)
                    if (tableName.uppercase() in SKIP_IDENTIFIERS) { i++; continue }

                    // Le token suivant doit être "."
                    var j = i + 1
                    while (j < size && tokens.get(j).channel != Token.DEFAULT_CHANNEL) j++
                    if (j >= size || tokens.get(j).text != ".") { i++; continue }

                    // Le token d'après le "." doit être un identifiant de champ
                    var k = j + 1
                    while (k < size && tokens.get(k).channel != Token.DEFAULT_CHANNEL) k++
                    if (k >= size) { i++; continue }
                    val fieldToken = tokens.get(k)
                    val fieldName  = fieldToken.text?.takeIf { it.isNotBlank() }
                    if (fieldName == null) { i++; continue }

                    // Vérifier si la table est connue dans le schéma
                    if (!knownTables.contains(tableName.uppercase())) { i++; continue }

                    // La table est connue — vérifier si le champ existe
                    val qualifiedField = "${tableName.uppercase()}.${fieldName.uppercase()}"
                    val fieldExists = service.symbolIndex.allSymbols().any { sym ->
                        sym.kind == AblSymbol.Kind.FIELD &&
                        sym.name.uppercase() == qualifiedField
                    }

                    if (!fieldExists) {
                        val range = AblInspectionHelper.toRange(
                            doc, fieldToken.line, fieldToken.charPositionInLine, fieldName.length
                        )
                        holder.registerProblem(
                            file,
                            "Field '$fieldName' not found in table '$tableName' (schema: ${knownTables.size} tables loaded)",
                            ProblemHighlightType.WARNING,
                            range
                        )
                    }

                    i = k + 1
                }
            }
        }

    companion object {
        // Mots-clés ABL souvent suivis d'un "." mais pas des accès de champ
        private val SKIP_IDENTIFIERS = setOf(
            "END", "MESSAGE", "ASSIGN", "IF", "THEN", "ELSE", "DO", "RETURN",
            "PROCEDURE", "FUNCTION", "CLASS", "METHOD", "NO-UNDO", "NO-LOCK",
            "NOLOCK", "ERROR-STATUS", "THIS-OBJECT", "SUPER", "CAST",
            "VIEW-AS", "ALERT-BOX", "INFORMATION", "ERROR", "WARNING"
        )
    }
}
