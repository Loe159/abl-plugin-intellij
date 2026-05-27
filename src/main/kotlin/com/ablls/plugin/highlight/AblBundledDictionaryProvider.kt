package com.ablls.plugin.highlight

import com.intellij.spellchecker.BundledDictionaryProvider

/**
 * Fournit le dictionnaire ABL embarqué au moteur de vérification orthographique.
 *
 * Contient les termes ABL spécifiques (PROPATH, RECID, LONGCHAR, etc.) afin qu'ils
 * ne soient pas signalés comme fautes dans les commentaires et les chaînes.
 *
 * Enregistré via <spellchecker.bundledDictionaryProvider> dans plugin.xml.
 */
class AblBundledDictionaryProvider : BundledDictionaryProvider {
    override fun getBundledDictionaries(): Array<String> = arrayOf("/spellchecker/abl.dic")
}
