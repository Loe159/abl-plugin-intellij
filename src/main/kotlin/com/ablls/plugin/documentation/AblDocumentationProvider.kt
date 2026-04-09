package com.ablls.plugin.documentation

import com.ablls.plugin.core.AblBuiltinDocs
import com.ablls.plugin.core.AblProjectAnalysisService
import com.ablls.plugin.core.AblSymbol
import com.ablls.plugin.language.AblLanguage
import com.intellij.lang.documentation.AbstractDocumentationProvider
import com.intellij.openapi.components.service
import com.intellij.openapi.editor.Editor
import com.intellij.psi.PsiElement
import com.intellij.psi.PsiFile

/**
 * Documentation hover pour les symboles ABL (Ctrl+Q et mouse hover).
 *
 * Ordre de priorité :
 *   1. Symboles définis par l'utilisateur (avec commentaire source et localisation)
 *   2. Built-ins ABL documentés dans [AblBuiltinDocs]
 *
 * [getCustomDocumentationElement] est surchargé pour que IntelliJ utilise
 * le token sous le curseur même sans référence résolue (arbre PSI plat).
 */
class AblDocumentationProvider : AbstractDocumentationProvider() {

    /**
     * Indique à IntelliJ quel élément utiliser comme cible de documentation
     * quand il n'y a pas de référence résolue (cas d'un arbre PSI plat).
     * Sans cette surcharge, IntelliJ ne cherche pas de documentation pour les tokens ABL.
     */
    override fun getCustomDocumentationElement(
        editor: Editor,
        file: PsiFile,
        contextElement: PsiElement?,
        targetOffset: Int
    ): PsiElement? {
        if (file.language != AblLanguage) return null
        return contextElement
    }

    override fun generateDoc(element: PsiElement?, originalElement: PsiElement?): String? {
        val target = originalElement ?: element ?: return null
        if (target.containingFile?.language != AblLanguage) return null

        val word = target.text?.trim() ?: return null
        if (word.isBlank() || word.length < 2) return null

        val project = target.project
        val file    = target.containingFile ?: return null
        val uri     = file.virtualFile?.url ?: return null

        val service = project.service<AblProjectAnalysisService>()

        // S'assurer que le fichier est analysé (l'annotateur peut ne pas encore avoir tourné)
        service.analyzeFile(file.text, uri)

        val symbols = service.symbolIndex.findByName(word, uri)
        if (symbols.isNotEmpty()) {
            return buildSymbolDoc(symbols.first())
        }

        return AblBuiltinDocs.get(word).map { markdownToHtml(it) }.orElse(null)
    }

    override fun getDocumentationElementForLookupItem(
        psiManager: com.intellij.psi.PsiManager,
        `object`: Any?,
        element: PsiElement?
    ): PsiElement? = element

    override fun getDocumentationElementForLink(
        psiManager: com.intellij.psi.PsiManager,
        link: String?,
        context: PsiElement?
    ): PsiElement? = null

    // ─── Construction HTML ────────────────────────────────────────────────────

    private fun buildSymbolDoc(symbol: AblSymbol): String {
        val sb = StringBuilder()
        sb.append("<pre><code>")
        sb.append(buildSignature(symbol))
        sb.append("</code></pre>")

        if (!symbol.documentation.isNullOrBlank()) {
            sb.append("<p>").append(escapeHtml(symbol.documentation)).append("</p>")
        }

        if (symbol.uri != null) {
            val short = symbol.uri.substringAfterLast('/')
            val line  = (symbol.definitionRange?.startLine ?: -1) + 1
            if (line > 0) {
                sb.append("<p><i>Défini dans <code>$short</code> ligne $line</i></p>")
            }
        }
        return sb.toString()
    }

    private fun buildSignature(symbol: AblSymbol): String = when (symbol.kind) {
        AblSymbol.Kind.VARIABLE   -> "DEFINE VARIABLE ${symbol.name} AS ${symbol.dataType}"
        AblSymbol.Kind.PARAMETER  -> "DEFINE PARAMETER ${symbol.name} AS ${symbol.dataType}"
        AblSymbol.Kind.PROCEDURE  -> "PROCEDURE ${symbol.name}"
        AblSymbol.Kind.FUNCTION   -> {
            val ret = symbol.dataType?.replace("FUNCTION RETURNS ", "") ?: "VOID"
            "FUNCTION ${symbol.name} RETURNS $ret"
        }
        AblSymbol.Kind.CLASS      -> {
            val kw = when {
                symbol.dataType?.startsWith("INTERFACE") == true -> "INTERFACE"
                symbol.dataType?.startsWith("ENUM")      == true -> "ENUM"
                else -> "CLASS"
            }
            "$kw ${symbol.name}"
        }
        AblSymbol.Kind.METHOD     -> {
            val ret = symbol.dataType?.replace("METHOD RETURNS ", "") ?: "VOID"
            "METHOD ${symbol.name} RETURNS $ret"
        }
        AblSymbol.Kind.FIELD      -> {
            val type = symbol.dataType?.replace("PROPERTY ", "") ?: ""
            if (symbol.name.contains(".")) "FIELD ${symbol.name} AS $type"
            else "PROPERTY ${symbol.name} AS $type"
        }
        AblSymbol.Kind.TEMP_TABLE -> "DEFINE TEMP-TABLE ${symbol.name}"
        AblSymbol.Kind.DATASET    -> "DEFINE DATASET ${symbol.name}"
        AblSymbol.Kind.QUERY      -> "DEFINE QUERY ${symbol.name}"
        AblSymbol.Kind.BUFFER     -> {
            val tbl = symbol.dataType?.replace("BUFFER FOR ", "") ?: "?"
            "DEFINE BUFFER ${symbol.name} FOR $tbl"
        }
        AblSymbol.Kind.EVENT      -> "EVENT ${symbol.name}"
        else                      -> "${symbol.kind} ${symbol.name}"
    }

    /** Conversion Markdown basique → HTML pour les built-ins. */
    private fun markdownToHtml(md: String): String {
        var html = escapeHtml(md)
        // Titres **gras**
        html = html.replace(Regex("\\*\\*(.+?)\\*\\*"), "<b>$1</b>")
        // Code inline `code`
        html = html.replace(Regex("`([^`]+)`"), "<code>$1</code>")
        // Blocs de code ```abl ... ```
        html = html.replace(Regex("```[a-z]*\\n([\\s\\S]*?)```"), "<pre><code>$1</code></pre>")
        // Sauts de ligne
        html = html.replace("\n\n", "<p>").replace("\n", "<br>")
        return html
    }

    private fun escapeHtml(text: String): String = text
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\"", "&quot;")
}
