package com.ablls.plugin.completion

import com.ablls.plugin.core.AblBuiltinDocs
import com.ablls.plugin.core.AblKeywordList
import com.ablls.plugin.core.AblProjectAnalysisService
import com.ablls.plugin.core.AblSymbol
import com.ablls.plugin.language.AblLanguage
import com.intellij.codeInsight.completion.*
import com.intellij.codeInsight.lookup.LookupElementBuilder
import com.intellij.icons.AllIcons
import com.intellij.openapi.components.service
import com.intellij.patterns.PlatformPatterns
import com.intellij.util.ProcessingContext
import javax.swing.Icon

/**
 * Fournisseur d'autocomplétion ABL.
 *
 * Sources proposées (par ordre de priorité) :
 *   1. Symboles sémantiques du scope résolu (treeParser01) — types exacts, signatures
 *   2. Symboles syntaxiques de l'index (variables, procédures, classes du projet)
 *   3. Mots-clés ABL + fonctions built-in documentées
 */
class AblCompletionContributor : CompletionContributor() {
    init {
        extend(
            CompletionType.BASIC,
            PlatformPatterns.psiElement().withLanguage(AblLanguage),
            AblCompletionProvider()
        )
    }
}

private class AblCompletionProvider : CompletionProvider<CompletionParameters>() {

    override fun addCompletions(
        parameters: CompletionParameters,
        context: ProcessingContext,
        result: CompletionResultSet
    ) {
        val file    = parameters.originalFile
        val project = file.project
        val uri     = file.virtualFile?.url ?: return
        val prefix  = result.prefixMatcher.prefix
        val content = file.text

        val service = project.service<AblProjectAnalysisService>()

        // Analyser le fichier courant (syntaxe rapide)
        service.analyzeFile(content, uri)

        // Lancer l'analyse sémantique en background pour la prochaine fois
        service.analyzeSemanticAsync(content, uri)

        // ── 1. Symboles sémantiques du scope résolu ───────────────────────────
        val semanticResult = service.getSemanticResult(uri)
        if (semanticResult?.rootScope != null) {
            addScopeCompletions(semanticResult.rootScope, prefix, result)
        }

        // ── 1b. Complétion contextuelle Table.Field (dot notation) ───────────────
        val textBefore = file.text.take(parameters.offset)
        val dotCandidate = extractTableBeforeDot(textBefore, prefix)
        if (dotCandidate != null) {
            addFieldCompletions(dotCandidate, prefix, service, result)
            return  // champs uniquement dans ce contexte
        }

        // ── 2. Symboles de l'index du projet ─────────────────────────────────
        val upperPrefix = prefix.uppercase()
        service.symbolIndex.findByPrefix(prefix, uri).forEach { symbol ->
            result.addElement(
                LookupElementBuilder.create(symbol.name)
                    .withTypeText(symbol.dataType ?: "", true)
                    .withIcon(iconFor(symbol.kind))
                    .withTailText(kindLabel(symbol.kind), true)
                    .withInsertHandler(insertHandlerFor(symbol))
            )
        }

        // ── 3. Mots-clés ABL ──────────────────────────────────────────────────
        for (keyword in AblKeywordList.KEYWORDS) {
            if (keyword.startsWith(upperPrefix, ignoreCase = true)) {
                val isBuiltin = AblBuiltinDocs.has(keyword)
                val detail    = if (isBuiltin) "built-in" else "keyword"
                result.addElement(
                    LookupElementBuilder.create(keyword)
                        .withTypeText(detail, true)
                        .withIcon(if (isBuiltin) AllIcons.Nodes.Function else AllIcons.Nodes.Tag)
                        .bold()
                )
            }
        }

    }

    // ─── Complétion contextuelle : Table.Field ────────────────────────────────

    /**
     * Détecte si on est dans un contexte `Table.Field`.
     *
     * Le point doit être au caractère immédiatement avant [prefix] dans [textBefore] :
     * cela évite de confondre les terminateurs d'instruction (`.` de fin de ligne).
     *
     * Exemples :
     *   textBefore = "...Customer."  prefix = ""      → "Customer"
     *   textBefore = "...Customer.Cust" prefix = "Cust" → "Customer"
     *   textBefore = "...NO-UNDO.\n" prefix = "MESS"  → null  (terminateur, pas de dot adjacent)
     */
    private fun extractTableBeforeDot(textBefore: String, prefix: String): String? {
        // Position dans textBefore où commence le prefix (= juste après le dot si dot-context)
        val afterDotPos = textBefore.length - prefix.length
        val dotPos = afterDotPos - 1
        if (dotPos < 0 || textBefore[dotPos] != '.') return null

        // Extraire l'identifiant qui précède le point
        var i = dotPos - 1
        while (i >= 0 && (textBefore[i].isLetterOrDigit() || textBefore[i] == '-' || textBefore[i] == '_')) i--
        val name = textBefore.substring(i + 1, dotPos)
        return name.ifBlank { null }
    }

    /** Ajoute les champs de [tableName] au résultat de complétion. */
    private fun addFieldCompletions(
        tableName: String,
        prefix: String,
        service: com.ablls.plugin.core.AblProjectAnalysisService,
        result: CompletionResultSet
    ) {
        val prefixUpper    = prefix.uppercase()
        val tableNameUpper = tableName.uppercase()
        val qualifiedPrefix = "$tableNameUpper.$prefixUpper"

        service.symbolIndex.findByPrefix("$tableName.", "").forEach { symbol ->
            if (symbol.kind != AblSymbol.Kind.FIELD) return@forEach
            // symbol.name = "Customer.CustNum" → proposer "CustNum"
            val fieldName = symbol.name.substringAfterLast('.')
            if (!fieldName.startsWith(prefixUpper, ignoreCase = true)) return@forEach
            result.addElement(
                LookupElementBuilder.create(fieldName)
                    .withTypeText(symbol.dataType ?: "", true)
                    .withIcon(AllIcons.Nodes.Field)
                    .withTailText(" field of $tableName", true)
            )
        }
    }

    // ─── Complétion depuis le TreeParserSymbolScope (types résolus) ───────────

    private fun addScopeCompletions(
        scope: org.prorefactor.treeparser.TreeParserSymbolScope,
        prefix: String,
        result: CompletionResultSet
    ) {
        val upperPrefix = prefix.uppercase()

        // Variables
        for (variable in runCatching { scope.variables }.getOrNull() ?: emptyList()) {
            if (!variable.name.startsWith(upperPrefix, ignoreCase = true)) continue
            val dataType = runCatching { variable.dataType?.toString() }.getOrNull() ?: "UNKNOWN"
            result.addElement(
                LookupElementBuilder.create(variable.name)
                    .withTypeText(dataType, true)
                    .withIcon(if (variable.javaClass.simpleName == "Parameter") AllIcons.Nodes.Parameter else AllIcons.Nodes.Variable)
                    .withTailText(if (variable.javaClass.simpleName == "Parameter") " param" else " var", true)
            )
        }

        // Routines avec signature complète
        for (routine in runCatching { scope.routines }.getOrNull() ?: emptyList()) {
            if (!routine.name.startsWith(upperPrefix, ignoreCase = true)) continue
            val sig = runCatching { routine.ideSignature }.getOrNull()
                ?: runCatching { routine.signature }.getOrNull()
                ?: routine.name

            val params = runCatching {
                routine.parameters.joinToString(", ") { p ->
                    val pName = runCatching { p.javaClass.getMethod("getName").invoke(p) }.getOrNull() ?: "p"
                    "$pName"
                }
            }.getOrNull() ?: ""

            result.addElement(
                LookupElementBuilder.create(routine.name)
                    .withTypeText(sig, true)
                    .withTailText(if (params.isNotEmpty()) "($params)" else "()", true)
                    .withIcon(AllIcons.Nodes.Method)
                    .withInsertHandler { ctx, _ ->
                        // Insérer les parenthèses si c'est une fonction/méthode
                        if (routine.parameters.isNotEmpty()) {
                            ctx.document.insertString(ctx.tailOffset, "()")
                            ctx.editor.caretModel.moveToOffset(ctx.tailOffset - 1)
                        }
                    }
            )
        }

        // Scope enfants
        for (child in runCatching { scope.childScopes }.getOrNull() ?: emptyList()) {
            addScopeCompletions(child, prefix, result)
        }
    }

    // ─── Insert handlers ──────────────────────────────────────────────────────

    private fun insertHandlerFor(symbol: AblSymbol): InsertHandler<com.intellij.codeInsight.lookup.LookupElement>? {
        return when (symbol.kind) {
            AblSymbol.Kind.PROCEDURE,
            AblSymbol.Kind.FUNCTION,
            AblSymbol.Kind.METHOD -> InsertHandler { ctx, _ ->
                ctx.document.insertString(ctx.tailOffset, "()")
                ctx.editor.caretModel.moveToOffset(ctx.tailOffset - 1)
            }
            else -> null
        }
    }

    // ─── Icônes ───────────────────────────────────────────────────────────────

    private fun iconFor(kind: AblSymbol.Kind): Icon = when (kind) {
        AblSymbol.Kind.PROCEDURE  -> AllIcons.Nodes.Method
        AblSymbol.Kind.FUNCTION   -> AllIcons.Nodes.Function
        AblSymbol.Kind.CLASS      -> AllIcons.Nodes.Class
        AblSymbol.Kind.METHOD     -> AllIcons.Nodes.Method
        AblSymbol.Kind.VARIABLE   -> AllIcons.Nodes.Variable
        AblSymbol.Kind.PARAMETER  -> AllIcons.Nodes.Parameter
        AblSymbol.Kind.FIELD      -> AllIcons.Nodes.Field
        AblSymbol.Kind.TEMP_TABLE -> AllIcons.Nodes.DataTables
        AblSymbol.Kind.BUFFER     -> AllIcons.Nodes.DataTables
        AblSymbol.Kind.DATASET    -> AllIcons.Nodes.DataSchema
        AblSymbol.Kind.QUERY      -> AllIcons.Nodes.DataSchema
        AblSymbol.Kind.EVENT      -> AllIcons.Nodes.Method
        else                      -> AllIcons.Nodes.Unknown
    }

    private fun kindLabel(kind: AblSymbol.Kind): String = when (kind) {
        AblSymbol.Kind.VARIABLE   -> " var"
        AblSymbol.Kind.PARAMETER  -> " param"
        AblSymbol.Kind.PROCEDURE  -> " proc"
        AblSymbol.Kind.FUNCTION   -> " func"
        AblSymbol.Kind.CLASS      -> " class"
        AblSymbol.Kind.METHOD     -> " method"
        AblSymbol.Kind.TEMP_TABLE -> " tt"
        AblSymbol.Kind.FIELD      -> " field"
        AblSymbol.Kind.BUFFER     -> " buf"
        AblSymbol.Kind.DATASET    -> " ds"
        AblSymbol.Kind.QUERY      -> " query"
        AblSymbol.Kind.EVENT      -> " event"
        else                      -> ""
    }
}
