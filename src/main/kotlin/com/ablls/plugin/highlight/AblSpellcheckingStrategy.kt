package com.ablls.plugin.highlight

import com.ablls.plugin.language.AblLanguage
import com.ablls.plugin.parser.AblTokenTypes
import com.intellij.psi.PsiElement
import com.intellij.spellchecker.tokenizer.SpellcheckingStrategy
import com.intellij.spellchecker.tokenizer.Tokenizer

/**
 * Spell checking ABL — vérifie l'orthographe dans les commentaires et strings.
 *
 * Délègue au tokenizer standard IntelliJ :
 *  - Commentaires (// et /* */) → vérifiés mot par mot
 *  - Chaînes de caractères → vérifiées mot par mot
 *
 * Activation : Settings → Editor → Inspections → Spelling → Typo.
 */
class AblSpellcheckingStrategy : SpellcheckingStrategy() {
    override fun isMyContext(element: PsiElement): Boolean = element.language == AblLanguage

    override fun getTokenizer(element: PsiElement): Tokenizer<out PsiElement> {
        val type = element.node?.elementType ?: return EMPTY_TOKENIZER
        return when (type) {
            AblTokenTypes.LINE_COMMENT,
            AblTokenTypes.BLOCK_COMMENT,
            -> TEXT_TOKENIZER

            AblTokenTypes.STRING -> TEXT_TOKENIZER

            else -> EMPTY_TOKENIZER
        }
    }
}
