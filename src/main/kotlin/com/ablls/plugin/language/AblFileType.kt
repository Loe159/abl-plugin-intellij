package com.ablls.plugin.language

import com.intellij.openapi.fileTypes.LanguageFileType
import javax.swing.Icon

/**
 * Type de fichier ABL — enregistré dans plugin.xml pour les extensions
 * .p (procédure), .cls (classe OO), .i (include), .w (window), .t (table)
 */
class AblFileType private constructor() : LanguageFileType(AblLanguage) {
    companion object {
        @JvmField
        val INSTANCE = AblFileType()

        val EXTENSIONS = setOf("p", "cls", "i", "w", "t")
    }

    override fun getName(): String = "ABL File"

    override fun getDescription(): String = "Progress OpenEdge ABL source file"

    override fun getDefaultExtension(): String = "p"

    override fun getIcon(): Icon = AblIcons.FILE
}
