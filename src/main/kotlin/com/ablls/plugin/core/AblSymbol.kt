package com.ablls.plugin.core

/**
 * Plage de texte dans un fichier source (lignes/colonnes 0-based).
 */
data class AblRange(
    val startLine: Int,
    val startCol: Int,
    val endLine: Int,
    val endCol: Int,
)

/**
 * Symbole ABL extrait par l'analyse syntaxique et sémantique.
 *
 * Couvre variables, paramètres, procédures, fonctions, classes,
 * méthodes, tables temporaires, buffers, datasets, queries, events.
 */
data class AblSymbol(
    val name: String,
    val kind: Kind,
    val uri: String?,
    val definitionRange: AblRange?,
    val dataType: String?,
    val documentation: String?,
) {
    enum class Kind {
        VARIABLE,
        PARAMETER,
        PROCEDURE,
        FUNCTION,
        CLASS,
        METHOD,
        TABLE,
        FIELD,
        DATASET,
        QUERY,
        BUFFER,
        TEMP_TABLE,
        EVENT,
        UNKNOWN,
    }

    override fun toString(): String = "AblSymbol{$kind '$name' ($dataType)}"
}
