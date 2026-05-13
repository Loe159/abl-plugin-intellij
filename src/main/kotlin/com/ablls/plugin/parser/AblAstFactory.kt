package com.ablls.plugin.parser

import com.intellij.lang.ASTFactory
import com.intellij.psi.impl.source.tree.LeafElement
import com.intellij.psi.tree.IElementType

/**
 * ASTFactory ABL — crée [AblNamedLeafElement] pour les tokens IDENTIFIER.
 *
 * Enregistré via <lang.ast.factory language="ABL"> dans plugin.xml.
 * Appelé par l'infrastructure IntelliJ quand elle construit l'arbre PSI
 * depuis les tokens du lexer.
 *
 * Seuls les tokens IDENTIFIER reçoivent une classe spécifique ; tous les
 * autres tokens utilisent le [LeafElement] standard.
 */
class AblAstFactory : ASTFactory() {

    override fun createLeaf(type: IElementType, text: CharSequence): LeafElement? =
        if (type === AblTokenTypes.IDENTIFIER)
            AblNamedLeafElement(type, text)
        else
            super.createLeaf(type, text)
}
