package com.ablls.plugin.parser

import com.ablls.plugin.language.AblLanguage
import com.intellij.extapi.psi.ASTWrapperPsiElement
import com.intellij.extapi.psi.PsiFileBase
import com.intellij.lang.ASTNode
import com.intellij.lang.LightPsiParser
import com.intellij.lang.PsiBuilder
import com.intellij.lang.PsiParser
import com.intellij.openapi.fileTypes.FileType
import com.intellij.psi.FileViewProvider
import com.intellij.psi.PsiElement
import com.intellij.psi.tree.IElementType
import com.ablls.plugin.language.AblFileType

// ─── Fichier PSI racine ───────────────────────────────────────────────────────

/**
 * Représentation PSI d'un fichier ABL.
 * La navigation, les usages, et les intentions opèrent sur cette classe.
 */
class AblFile(viewProvider: FileViewProvider) : PsiFileBase(viewProvider, AblLanguage) {
    override fun getFileType(): FileType = AblFileType.INSTANCE
    override fun toString(): String = "ABL File"
}

// ─── Parser PSI léger ─────────────────────────────────────────────────────────

/**
 * Parser PSI minimal — crée un arbre plat de tokens.
 *
 * Pour un support complet (rename, find usages au niveau PSI),
 * il faudrait implémenter un vrai arbre hiérarchique ici en utilisant
 * le parser CABL (ProParser) et en mappant ses nœuds AST vers des
 * IElementType IntelliJ.
 *
 * Dans notre architecture, la sémantique est gérée par AblParserFacade
 * (proparse natif) ; le parser PSI sert surtout à la coloration et au folding.
 */
class AblPsiParser : PsiParser, LightPsiParser {

    override fun parse(root: IElementType, builder: PsiBuilder): ASTNode {
        parseLight(root, builder)
        return builder.treeBuilt
    }

    override fun parseLight(root: IElementType, builder: PsiBuilder) {
        val rootMarker = builder.mark()

        // Avancer sur tous les tokens — arbre plat
        while (!builder.eof()) {
            builder.advanceLexer()
        }

        rootMarker.done(root)
    }
}

// ─── Factory d'éléments PSI ───────────────────────────────────────────────────

object AblElementFactory {
    fun createElement(node: ASTNode): PsiElement = ASTWrapperPsiElement(node)
}
