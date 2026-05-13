package com.ablls.plugin.core

import com.intellij.openapi.diagnostic.Logger
import org.antlr.v4.runtime.*
import org.antlr.v4.runtime.tree.ErrorNode
import org.antlr.v4.runtime.tree.ParseTree
import org.prorefactor.core.schema.Schema
import org.prorefactor.proparse.ABLLexer
import org.prorefactor.proparse.Lexer
import org.prorefactor.proparse.PostLexer
import org.prorefactor.proparse.TokenList
import org.prorefactor.proparse.antlr4.Proparse
import org.prorefactor.proparse.support.IProparseEnvironment
import org.prorefactor.refactor.RefactorSession
import org.prorefactor.refactor.settings.ProparseSettings
import org.prorefactor.treeparser.ParseUnit
import org.prorefactor.treeparser.TreeParserSymbolScope
import java.nio.charset.StandardCharsets
import java.nio.file.Path

/**
 * Façade vers le parser ABL CABL (Riverside Software / sonar-openedge).
 *
 * Deux niveaux d'analyse :
 *  1. [parse] — Parsing syntaxique rapide (ANTLR4) : erreurs + arbre Proparse.
 *     Utilisé par [AblAnnotator] pour les squiggles en temps réel.
 *
 *  2. [analyze] — Analyse sémantique complète via [ParseUnit.treeParser01] :
 *     symboles résolus, types, signatures, références.
 *     Utilisé par completion, navigation, rename.
 *
 * L'environnement proparse (PROPATH, version OE) est mis à jour via [updateEnvironment].
 */
class AblParserFacade {

    private val LOG = Logger.getInstance(AblParserFacade::class.java)

    @Volatile
    var session: IProparseEnvironment = createMinimalEnvironment()
        private set

    fun updateEnvironment(env: IProparseEnvironment) {
        session = env
        LOG.info("AblParserFacade : environnement mis à jour")
    }

    // ─── Niveau 1 : parsing syntaxique rapide ────────────────────────────────

    /**
     * Parse le contenu ABL et retourne erreurs + arbre Proparse.
     * Rapide, adapté à l'appel sur chaque frappe.
     */
    fun parse(content: String, uri: String): AblParseResult {
        return try {
            parseInternal(content, uri)
        } catch (e: Exception) {
            LOG.warn("Erreur parsing CABL sur $uri : ${e.message}")
            AblParseResult.empty(uri)
        }
    }

    private fun parseInternal(content: String, uri: String): AblParseResult {
        val errors = mutableListOf<SyntaxError>()
        val errorListener = CollectingErrorListener(errors, uri)
        val bytes = content.toByteArray(StandardCharsets.UTF_8)

        val ablLexer = ABLLexer(session, StandardCharsets.UTF_8, bytes, uri, false)
        val lex = Lexer(ablLexer, bytes, uri)
        val postLexer = PostLexer(ablLexer, lex)
        val tokenList = TokenList(postLexer)
        val tokens = CommonTokenStream(tokenList)

        val parser = Proparse(tokens)
        parser.initialize(session, null)
        parser.removeErrorListeners()
        parser.addErrorListener(errorListener)

        parser.errorHandler = object : DefaultErrorStrategy() {
            override fun reportNoViableAlternative(r: Parser, e: NoViableAltException) {
                try { super.reportNoViableAlternative(r, e) }
                catch (_: NullPointerException) { r.notifyErrorListeners(e.offendingToken, "no viable alternative", e) }
            }
            override fun reportInputMismatch(r: Parser, e: InputMismatchException) {
                try { super.reportInputMismatch(r, e) }
                catch (_: NullPointerException) { r.notifyErrorListeners(e.offendingToken, "input mismatch", e) }
            }
            override fun reportMissingToken(r: Parser) {
                try { super.reportMissingToken(r) } catch (_: NullPointerException) {}
            }
            override fun recover(r: Parser, e: RecognitionException) {
                try { super.recover(r, e) } catch (_: NullPointerException) {}
            }
            override fun recoverInline(r: Parser): Token {
                return try { super.recoverInline(r) }
                catch (_: NullPointerException) { throw InputMismatchException(r) }
            }
        }

        val tree = parser.program()
        collectErrorNodes(tree, errors, uri)

        LOG.debug("Parsing CABL $uri : ${tokens.size()} tokens, ${errors.size} erreurs")
        return AblParseResult(tree, tokens, errors, uri, content, session)
    }

    // ─── Niveau 2 : analyse sémantique complète (ParseUnit + treeParser01) ───

    /**
     * Analyse sémantique : réutilise le [ParseUnit] stocké dans [parseResult]
     * (initialisé lazily par [AblParseResult.parseUnit]) — aucun re-parse.
     * À appeler en arrière-plan.
     */
    fun analyze(parseResult: AblParseResult): AblSemanticResult {
        val pu = parseResult.parseUnit
            ?: return AblSemanticResult(null, null, parseResult.syntaxErrors, parseResult.uri)
        return try {
            pu.treeParser01()
            val scope = getRootScopeSafely(pu)
            LOG.debug("Analyse sémantique ${parseResult.uri} : scope=${scope != null}")
            AblSemanticResult(parseResult.topNode, scope, emptyList(), parseResult.uri)
        } catch (e: Exception) {
            LOG.warn("Erreur analyse sémantique ${parseResult.uri} : ${e.message}")
            AblSemanticResult(null, null, parseResult.syntaxErrors, parseResult.uri)
        }
    }

    /** Surcharge de compatibilité : parse puis analyse en une passe. */
    fun analyze(content: String, uri: String): AblSemanticResult =
        analyze(parse(content, uri))

    // ─── Helpers reflection scope/topNode ────────────────────────────────────

    private fun getRootScopeSafely(pu: ParseUnit): TreeParserSymbolScope? =
        runCatching {
            pu.javaClass.getMethod("getRootScope").invoke(pu) as? TreeParserSymbolScope
        }.getOrNull() ?: runCatching {
            val tNode = pu.javaClass.getMethod("getTopNode").invoke(pu)
            tNode?.javaClass?.getMethod("getSymbolScope")?.invoke(tNode) as? TreeParserSymbolScope
        }.getOrNull()

    // ─── Erreurs ErrorNode (récupération ANTLR4) ─────────────────────────────

    private fun collectErrorNodes(node: ParseTree?, errors: MutableList<SyntaxError>, uri: String) {
        if (node == null) return
        if (node is ErrorNode) {
            val symbol = node.symbol
            if (symbol != null && symbol.type != Token.EOF) {
                val line = symbol.line - 1
                val col  = symbol.charPositionInLine
                // Éviter de spammer les erreurs sur la même ligne si ANTLR a déjà signalé une erreur (ex: lors d'une tentative de récupération)
                val alreadyCaptured = errors.any { it.line == line }
                if (!alreadyCaptured) {
                    val text = symbol.text?.replace("\r", "")?.replace("\n", " ")?.take(30) ?: ""
                    errors.add(SyntaxError(line, col, "Token inattendu : '$text'", uri))
                }
            }
        }
        for (i in 0 until node.childCount) {
            collectErrorNodes(node.getChild(i), errors, uri)
        }
    }

    // ─── Listener erreurs ANTLR4 ─────────────────────────────────────────────

    private class CollectingErrorListener(
        private val errors: MutableList<SyntaxError>,
        private val uri: String
    ) : BaseErrorListener() {
        override fun syntaxError(
            recognizer: Recognizer<*, *>?,
            offendingSymbol: Any?,
            line: Int,
            charPositionInLine: Int,
            msg: String?,
            e: RecognitionException?
        ) {
            var cleanMsg = msg ?: "Erreur syntaxique"
            
            // Rendre les messages d'erreur ANTLR plus lisibles pour un dev ABL
            if (cleanMsg.contains("mismatched input '(' expecting")) {
                cleanMsg = "Parenthèse inattendue (fonction non définie, include manquant ou point '.' manquant ?)"
            } else if (cleanMsg.contains("no viable alternative at input")) {
                val match = Regex("no viable alternative at input '(.*?)'").find(cleanMsg)
                val inputStr = match?.groupValues?.get(1)?.replace("\r", "")?.replace("\n", " ")?.take(30) ?: "..."
                cleanMsg = "Syntaxe invalide près de '$inputStr'"
            } else if (cleanMsg.contains("mismatched input")) {
                val match = Regex("mismatched input '(.*?)' expecting").find(cleanMsg)
                val inputStr = match?.groupValues?.get(1)?.replace("\r", "")?.replace("\n", " ")?.take(30) ?: "..."
                cleanMsg = "Élément inattendu '$inputStr' (point '.' manquant ou instruction incomplète ?)"
            } else if (cleanMsg.contains("extraneous input")) {
                val match = Regex("extraneous input '(.*?)'").find(cleanMsg)
                val inputStr = match?.groupValues?.get(1)?.replace("\r", "")?.replace("\n", " ")?.take(30) ?: "..."
                cleanMsg = "Élément en trop '$inputStr'"
            } else if (cleanMsg.contains("missing ") && cleanMsg.contains(" at ")) {
                val match = Regex("missing (.*?) at '(.*?)'").find(cleanMsg)
                val missing = match?.groupValues?.get(1) ?: "..."
                val at = match?.groupValues?.get(2)?.replace("\r", "")?.replace("\n", " ")?.take(30) ?: "..."
                cleanMsg = "Il manque $missing près de '$at'"
            }

            errors.add(SyntaxError(line - 1, charPositionInLine, cleanMsg, uri))
        }
    }

    // ─── Environnements ───────────────────────────────────────────────────────

    companion object {

        private val dummyIncludeFile: java.io.File by lazy {
            val f = java.io.File.createTempFile("dummy_include", ".i")
            f.deleteOnExit()
            f
        }

        /**
         * Environnement minimal : syntaxe seule, sans PROPATH ni schéma DB.
         */
        fun createMinimalEnvironment(): IProparseEnvironment {
            val settings = ProparseSettings("")
            settings.setCustomProversion("12.2.0")
            return object : RefactorSession(settings, Schema()) {
                override fun findFile3(fileName: String?): java.io.File? {
                    if (fileName == null) return null
                    val f = super.findFile3(fileName)
                    return f ?: dummyIncludeFile
                }
            }
        }

        /**
         * Environnement enrichi avec PROPATH, version OpenEdge et schéma DB optionnel.
         * Permet la résolution des `{include.i}` et la validation sémantique des tables/champs.
         */
        fun createProjectEnvironment(
            propath: List<Path>,
            oeVersion: String,
            schema: Schema = Schema()
        ): IProparseEnvironment {
            val propathStr = propath.joinToString(",") { it.toString() }
            val settings = ProparseSettings(propathStr)
            settings.setCustomProversion(oeVersion.ifBlank { "12.2.0" })
            return object : RefactorSession(settings, schema) {
                override fun findFile3(fileName: String?): java.io.File? {
                    if (fileName == null) return null
                    val f = super.findFile3(fileName)
                    return f ?: dummyIncludeFile
                }
            }
        }
    }
}
