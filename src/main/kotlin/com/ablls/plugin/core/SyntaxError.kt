package com.ablls.plugin.core

/**
 * Erreur syntaxique ABL, compatible avec les conventions IntelliJ (0-based).
 *
 * CABL/ANTLR4 produit des positions 1-based.
 * La conversion vers 0-based est effectuée dans [AblParserFacade].
 */
data class SyntaxError(
    val line: Int,     // 0-based
    val column: Int,   // 0-based
    val message: String,
    val uri: String = ""
)
