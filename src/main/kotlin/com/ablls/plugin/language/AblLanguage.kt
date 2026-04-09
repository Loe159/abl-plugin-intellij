package com.ablls.plugin.language

import com.intellij.lang.Language

/**
 * Singleton qui définit le langage "ABL" dans le registre IntelliJ.
 * Toutes les extensions qui se branchent sur le langage ABL référencent
 * cette instance (ex: SyntaxHighlighter, ParserDefinition, etc.)
 */
object AblLanguage : Language("ABL") {

    override fun getDisplayName(): String = "ABL (Progress OpenEdge)"

    // MIME types reconnus pour les fichiers ABL
    override fun getMimeTypes(): Array<String> =
        arrayOf("text/x-abl", "application/x-openedge-abl")
}
