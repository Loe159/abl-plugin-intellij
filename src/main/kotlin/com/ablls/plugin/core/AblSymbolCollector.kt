package com.ablls.plugin.core

import com.intellij.openapi.diagnostic.Logger
import org.antlr.v4.runtime.ParserRuleContext
import org.antlr.v4.runtime.Token
import org.antlr.v4.runtime.TokenStream
import org.prorefactor.proparse.antlr4.Proparse
import org.prorefactor.proparse.antlr4.ProparseBaseVisitor
import org.prorefactor.treeparser.TreeParserSymbolScope
import org.prorefactor.treeparser.symbols.Routine
import org.prorefactor.treeparser.symbols.Variable

/**
 * Collecte les symboles ABL depuis l'AST CABL (Proparse.ProgramContext).
 *
 * Deux sources de symboles sont combinées :
 *   1. [collectFromParseTree] — visiteur ANTLR4 sur le ProgramContext.
 *      Extrait définitions : DEFINE VARIABLE, PROCEDURE, FUNCTION, CLASS, etc.
 *
 *   2. [collectFromScope] — parcourt le [TreeParserSymbolScope] issu de treeParser01().
 *      Donne les types résolus, signatures et informations sémantiques complètes.
 *      Utilisé quand l'analyse sémantique est disponible.
 */
object AblSymbolCollector {

    private val LOG = Logger.getInstance(AblSymbolCollector::class.java)

    // ─── Source 1 : arbre ANTLR4 ─────────────────────────────────────────────

    fun collect(result: AblParseResult): List<AblSymbol> {
        if (!result.hasTree) return emptyList()
        val symbols = mutableListOf<AblSymbol>()
        try {
            val visitor = AblSymbolVisitor(symbols, result.uri, result.tokens)
            visitor.visit(result.tree)
        } catch (e: Exception) {
            LOG.warn("Erreur collecte symboles (${result.uri}) : ${e.message}")
        }
        return symbols
    }

    // ─── Source 2 : TreeParserSymbolScope (après treeParser01) ───────────────

    /**
     * Extrait les symboles depuis un [TreeParserSymbolScope] résolu sémantiquement.
     *
     * Complète les informations de [collect] avec :
     *   - Types résolus (INTEGER au lieu de "INTEGER-STRING")
     *   - Signatures complètes des routines via [Routine.getIDESignature]
     *   - Types des variables via [Variable.getDataType]
     */
    fun collectFromScope(scope: TreeParserSymbolScope?, uri: String): List<AblSymbol> {
        if (scope == null) return emptyList()
        val symbols = mutableListOf<AblSymbol>()
        try {
            collectScopeRecursive(scope, uri, symbols)
        } catch (e: Exception) {
            LOG.warn("Erreur collecte scope ($uri) : ${e.message}")
        }
        return symbols
    }

    private fun collectScopeRecursive(
        scope: TreeParserSymbolScope,
        uri: String,
        symbols: MutableList<AblSymbol>
    ) {
        // Variables — utilise l'API proparse TreeParserSymbolScope.getVariables()
        for (variable in runCatching { scope.variables }.getOrNull() ?: emptyList()) {
            runCatching {
                    val defNodeMethod = variable.javaClass.getMethod("getDefineNode")
                    val defNode = defNodeMethod.invoke(variable) as? org.prorefactor.core.JPNode
                    val range = defNode?.let { node ->
                        val line = node.token?.line ?: 1
                        val col = node.token?.charPositionInLine ?: 0
                        AblRange(line - 1, col, line - 1, col + variable.name.length)
                    }
                val dataType = runCatching { variable.dataType?.toString() }.getOrNull() ?: "UNKNOWN"
                val isParam  = runCatching { variable.javaClass.simpleName == "Parameter" }.getOrNull() ?: false
                symbols.add(AblSymbol(
                    name = variable.name,
                    kind = if (isParam) AblSymbol.Kind.PARAMETER else AblSymbol.Kind.VARIABLE,
                    uri = uri,
                    definitionRange = range,
                    dataType = dataType,
                    documentation = null
                ))
            }
        }

        // Routines (procédures, fonctions, méthodes)
        for (routine in runCatching { scope.routines }.getOrNull() ?: emptyList()) {
            runCatching {
                    val defNodeMethod = routine.javaClass.getMethod("getDefineNode")
                    val defNode = defNodeMethod.invoke(routine) as? org.prorefactor.core.JPNode
                    val range = defNode?.let { node ->
                        val line = node.token?.line ?: 1
                        val col = node.token?.charPositionInLine ?: 0
                        AblRange(line - 1, col, line - 1, col + routine.name.length)
                    }
                val (kind, sig) = routineKindAndSig(routine)
                symbols.add(AblSymbol(
                    name = routine.name,
                    kind = kind,
                    uri = uri,
                    definitionRange = range,
                    dataType = sig,
                    documentation = null
                ))
            }
        }

        // Buffers (table buffers)
        val bufferList = runCatching { 
            val method = scope.javaClass.getMethod("getBufferList")
            method.invoke(scope) as? Collection<*> 
        }.getOrNull() ?: runCatching { 
            val method = scope.javaClass.getMethod("getBuffers")
            method.invoke(scope) as? Collection<*> 
        }.getOrNull() ?: emptyList<Any>()

        for (bufferObj in bufferList) {
            runCatching {
                val defNodeMethod = bufferObj?.javaClass?.getMethod("getDefineNode")
                val defNode = defNodeMethod?.invoke(bufferObj) as? org.prorefactor.core.JPNode
                val range = defNode?.let { node ->
                    val line = node.token?.line ?: 1
                    val col = node.token?.charPositionInLine ?: 0
                    val len = (bufferObj.javaClass.getMethod("getName").invoke(bufferObj) as? String)?.length ?: 0
                    AblRange(line - 1, col, line - 1, col + len)
                }
                val name = bufferObj?.javaClass?.getMethod("getName")?.invoke(bufferObj) as? String ?: "?"
                val tableObj = runCatching { bufferObj?.javaClass?.getMethod("getTable")?.invoke(bufferObj) }.getOrNull()
                val tableName = runCatching { tableObj?.javaClass?.getMethod("getName")?.invoke(tableObj) as? String }.getOrNull() ?: "?"
                symbols.add(AblSymbol(
                    name = name,
                    kind = AblSymbol.Kind.BUFFER,
                    uri = uri,
                    definitionRange = range,
                    dataType = "BUFFER FOR $tableName",
                    documentation = null
                ))
            }
        }

        // Scope enfants (corps de procédures, méthodes, etc.)
        for (child in runCatching { scope.childScopes }.getOrNull() ?: emptyList()) {
            collectScopeRecursive(child, uri, symbols)
        }
    }

    private fun routineKindAndSig(routine: Routine): Pair<AblSymbol.Kind, String> {
        val sig = runCatching { routine.ideSignature }.getOrNull()
            ?: runCatching { routine.signature }.getOrNull()
            ?: routine.name
        val kind = when {
            routine.name.contains("::") -> AblSymbol.Kind.METHOD
            sig.contains("FUNCTION") || sig.contains("RETURNS") -> AblSymbol.Kind.FUNCTION
            else -> AblSymbol.Kind.PROCEDURE
        }
        return kind to sig
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Visiteur ANTLR4 — extrait les définitions de symboles depuis ProgramContext
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Visiteur qui étend [ProparseBaseVisitor] (CABL/Riverside).
 *
 * Les noms de méthodes correspondent exactement aux règles générées par CABL.
 * Si une mise à jour de proparse renomme des règles, les méthodes orphelines
 * sont simplement ignorées (pas d'erreur, mais moins de symboles collectés).
 */
private class AblSymbolVisitor(
    private val symbols: MutableList<AblSymbol>,
    private val uri: String,
    private val tokens: TokenStream?
) : ProparseBaseVisitor<Void?>() {

    private val scopeStack = ArrayDeque<String>()

    // ─── DEFINE VARIABLE ─────────────────────────────────────────────────────

    override fun visitDefineVariableStatement(ctx: Proparse.DefineVariableStatementContext): Void? {
        val name = ctx.newIdentifier()?.text ?: return visitChildren(ctx)
        val type = ctx.fieldOption()
            ?.firstOrNull { it.datatype() != null }
            ?.datatype()?.text?.uppercase() ?: "UNKNOWN"
        addSymbol(name, AblSymbol.Kind.VARIABLE, type, ctx)
        return visitChildren(ctx)
    }

    // ─── DEFINE PARAMETER ────────────────────────────────────────────────────

    override fun visitDefineParameterStatementSub2Variable(
        ctx: Proparse.DefineParameterStatementSub2VariableContext
    ): Void? {
        val name = ctx.identifier()?.text ?: return visitChildren(ctx)
        val type = ctx.defineParamVar()?.datatype()?.text?.uppercase() ?: "UNKNOWN"
        addSymbol(name, AblSymbol.Kind.PARAMETER, type, ctx)
        return visitChildren(ctx)
    }

    // ─── DEFINE TEMP-TABLE ────────────────────────────────────────────────────

    override fun visitDefineTempTableStatement(ctx: Proparse.DefineTempTableStatementContext): Void? {
        val name = ctx.identifier()?.text ?: return visitChildren(ctx)
        addSymbol(name, AblSymbol.Kind.TEMP_TABLE, "TEMP-TABLE", ctx)
        return visitChildren(ctx)
    }

    // ─── DEFINE DATASET / QUERY / BUFFER / STREAM ────────────────────────────

    override fun visitDefineDatasetStatement(ctx: Proparse.DefineDatasetStatementContext): Void? {
        ctx.identifier()?.text?.let { addSymbol(it, AblSymbol.Kind.DATASET, "DATASET", ctx) }
        return visitChildren(ctx)
    }

    override fun visitDefineQueryStatement(ctx: Proparse.DefineQueryStatementContext): Void? {
        ctx.identifier()?.text?.let { addSymbol(it, AblSymbol.Kind.QUERY, "QUERY", ctx) }
        return visitChildren(ctx)
    }

    override fun visitDefineBufferStatement(ctx: Proparse.DefineBufferStatementContext): Void? {
        val name = ctx.identifier()?.text ?: return visitChildren(ctx)
        val tableName = ctx.record()?.text ?: "?"
        addSymbol(name, AblSymbol.Kind.BUFFER, "BUFFER FOR $tableName", ctx)
        return visitChildren(ctx)
    }

    override fun visitDefineStreamStatement(ctx: Proparse.DefineStreamStatementContext): Void? {
        ctx.identifier()?.text?.let { addSymbol(it, AblSymbol.Kind.VARIABLE, "STREAM", ctx) }
        return visitChildren(ctx)
    }

    // ─── PROCEDURE ────────────────────────────────────────────────────────────

    override fun visitProcedureStatement(ctx: Proparse.ProcedureStatementContext): Void? {
        val name = ctx.filename()?.text ?: return visitChildren(ctx)
        // Ignorer les forward declarations (déjà enregistrées)
        if (symbols.any { it.name.equals(name, ignoreCase = true) && it.kind == AblSymbol.Kind.PROCEDURE }) {
            return visitChildren(ctx)
        }
        addSymbol(name, AblSymbol.Kind.PROCEDURE, "PROCEDURE", ctx)
        scopeStack.addLast(name)
        visitChildren(ctx)
        scopeStack.removeLastOrNull()
        return null
    }

    // ─── FUNCTION ─────────────────────────────────────────────────────────────

    override fun visitFunctionStatement(ctx: Proparse.FunctionStatementContext): Void? {
        val ids = ctx.identifier() ?: return visitChildren(ctx)
        if (ids.isEmpty()) return visitChildren(ctx)
        val name = ids[0].text
        if (symbols.any { it.name.equals(name, ignoreCase = true) && it.kind == AblSymbol.Kind.FUNCTION }) {
            return visitChildren(ctx)
        }
        val retType = ctx.datatype()?.text?.uppercase() ?: "VOID"
        addSymbol(name, AblSymbol.Kind.FUNCTION, "FUNCTION RETURNS $retType", ctx)
        scopeStack.addLast(name)
        visitChildren(ctx)
        scopeStack.removeLastOrNull()
        return null
    }

    // ─── CLASS / INTERFACE / ENUM ─────────────────────────────────────────────

    override fun visitClassStatement(ctx: Proparse.ClassStatementContext): Void? {
        val name = ctx.typeName2()?.text ?: return visitChildren(ctx)
        addSymbol(name, AblSymbol.Kind.CLASS, "CLASS", ctx)
        scopeStack.addLast(name)
        visitChildren(ctx)
        scopeStack.removeLastOrNull()
        return null
    }

    override fun visitInterfaceStatement(ctx: Proparse.InterfaceStatementContext): Void? {
        val name = ctx.typeName2()?.text ?: return visitChildren(ctx)
        addSymbol(name, AblSymbol.Kind.CLASS, "INTERFACE", ctx)
        scopeStack.addLast(name)
        visitChildren(ctx)
        scopeStack.removeLastOrNull()
        return null
    }

    override fun visitEnumStatement(ctx: Proparse.EnumStatementContext): Void? {
        val name = ctx.typeName2()?.text ?: return visitChildren(ctx)
        val flags = ctx.FLAGS() != null
        addSymbol(name, AblSymbol.Kind.CLASS, if (flags) "ENUM FLAGS" else "ENUM", ctx)
        scopeStack.addLast(name)
        ctx.defEnumStatement()?.forEach { defEnum ->
            defEnum.enumMember()?.forEach { member ->
                val memberNames = member.typeName2()
                if (!memberNames.isNullOrEmpty()) {
                    addSymbol("$name:${memberNames[0].text}", AblSymbol.Kind.FIELD, name, member)
                }
            }
        }
        scopeStack.removeLastOrNull()
        return null
    }

    // ─── METHOD / PROPERTY / EVENT / CONSTRUCTOR / DESTRUCTOR ────────────────

    override fun visitMethodStatement(ctx: Proparse.MethodStatementContext): Void? {
        val name = ctx.newIdentifier()?.text ?: return visitChildren(ctx)
        val retType = ctx.datatype()?.text?.uppercase() ?: "VOID"
        val scope = currentScope()
        val qName = if (scope.isEmpty()) name else "$scope:$name"
        addSymbol(qName, AblSymbol.Kind.METHOD, "METHOD RETURNS $retType", ctx)
        scopeStack.addLast(qName)
        visitChildren(ctx)
        scopeStack.removeLastOrNull()
        return null
    }

    override fun visitDefinePropertyStatement(ctx: Proparse.DefinePropertyStatementContext): Void? {
        val name = ctx.newIdentifier()?.text ?: return visitChildren(ctx)
        val type = ctx.definePropertyAs()?.datatype()?.text?.uppercase() ?: "UNKNOWN"
        val scope = currentScope()
        val qName = if (scope.isEmpty()) name else "$scope:$name"
        addSymbol(qName, AblSymbol.Kind.FIELD, "PROPERTY $type", ctx)
        return null
    }

    override fun visitDefineEventStatement(ctx: Proparse.DefineEventStatementContext): Void? {
        val name = ctx.identifier()?.text ?: return visitChildren(ctx)
        val scope = currentScope()
        val qName = if (scope.isEmpty()) name else "$scope:$name"
        addSymbol(qName, AblSymbol.Kind.EVENT, "EVENT", ctx)
        return visitChildren(ctx)
    }

    override fun visitConstructorStatement(ctx: Proparse.ConstructorStatementContext): Void? {
        val scope = currentScope()
        val qName = if (scope.isEmpty()) "constructor" else "$scope:constructor"
        addSymbol(qName, AblSymbol.Kind.METHOD, "CONSTRUCTOR", ctx)
        scopeStack.addLast(qName)
        visitChildren(ctx)
        scopeStack.removeLastOrNull()
        return null
    }

    override fun visitDestructorStatement(ctx: Proparse.DestructorStatementContext): Void? {
        val scope = currentScope()
        val qName = if (scope.isEmpty()) "destructor" else "$scope:destructor"
        addSymbol(qName, AblSymbol.Kind.METHOD, "DESTRUCTOR", ctx)
        scopeStack.addLast(qName)
        visitChildren(ctx)
        scopeStack.removeLastOrNull()
        return null
    }

    // ─── Utilitaires ──────────────────────────────────────────────────────────

    private fun addSymbol(name: String, kind: AblSymbol.Kind, dataType: String, ctx: ParserRuleContext) {
        val doc = extractPrecedingComment(ctx)
        symbols.add(AblSymbol(
            name = name,
            kind = kind,
            uri = uri,
            definitionRange = toRange(ctx),
            dataType = dataType,
            documentation = doc
        ))
    }

    private fun currentScope(): String = scopeStack.lastOrNull() ?: ""

    private fun toRange(ctx: ParserRuleContext): AblRange {
        val start = ctx.start
        val stop  = ctx.stop ?: start
        return AblRange(
            startLine = (start.line - 1).coerceAtLeast(0),
            startCol  = start.charPositionInLine,
            endLine   = (stop.line - 1).coerceAtLeast(0),
            endCol    = stop.charPositionInLine + stop.text.length
        )
    }

    /** Cherche un commentaire de bloc /* ... */ précédant le symbole (sur le hidden channel). */
    private fun extractPrecedingComment(ctx: ParserRuleContext): String? {
        if (tokens == null) return null
        val start = ctx.start ?: return null
        val startIdx = start.tokenIndex
        if (startIdx == 0) return null

        var idx = startIdx - 1
        while (idx >= 0 && idx >= startIdx - 5) {
            val t = tokens.get(idx)
            if (t.channel == Token.HIDDEN_CHANNEL) {
                val text = t.text
                if (text.startsWith("/*")) {
                    return text
                        .removePrefix("/*").removeSuffix("*/")
                        .lines()
                        .map { it.trim().removePrefix("*").trim() }
                        .filter { it.isNotBlank() }
                        .joinToString(" ")
                }
            }
            if (t.channel != Token.HIDDEN_CHANNEL) break
            idx--
        }
        return null
    }
}
