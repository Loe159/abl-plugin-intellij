package com.ablls.plugin.core

import com.ablls.plugin.project.OpenEdgeProjectService
import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.components.Service
import com.intellij.openapi.components.service
import com.intellij.openapi.diagnostic.Logger
import com.intellij.openapi.project.Project
import java.nio.file.Files
import java.nio.file.Paths
import java.util.concurrent.ConcurrentHashMap

/**
 * Service de projet IntelliJ centralisant le parsing CABL et l'index de symboles.
 *
 * Fournit deux niveaux d'analyse :
 *  - [analyzeFile] : parse syntaxique rapide + extraction de symboles → mise à jour de [symbolIndex].
 *  - [analyzeFileSemantic] : analyse sémantique complète via ParseUnit.treeParser01()
 *    → types résolus, signatures, références (en arrière-plan).
 *
 * Toutes les opérations sont thread-safe.
 */
@Service(Service.Level.PROJECT)
class AblProjectAnalysisService(private val project: Project) {

    private val LOG = Logger.getInstance(AblProjectAnalysisService::class.java)

    val parserFacade = AblParserFacade()
    val symbolIndex  = AblSymbolIndex()

    /** Cache syntaxique : uri → (contentHash, AblParseResult) */
    private val parseCache = ConcurrentHashMap<String, Pair<Int, AblParseResult>>()

    /** Cache sémantique : uri → (contentHash, AblSemanticResult) */
    private val semanticCache = ConcurrentHashMap<String, Pair<Int, AblSemanticResult>>()

    init {
        ApplicationManager.getApplication().executeOnPooledThread {
            updateEnvironment()
        }
    }

    // ─── Analyse syntaxique rapide ────────────────────────────────────────────

    /**
     * Parse le fichier ABL, met à jour [symbolIndex], retourne erreurs + arbre.
     * Utilise un cache par hash — adapté à l'appel sur chaque frappe.
     */
    fun analyzeFile(content: String, uri: String): AblParseResult {
        val hash = content.hashCode()
        parseCache[uri]?.let { (h, r) -> if (h == hash) return r }

        val result  = parserFacade.parse(content, uri)
        val symbols = AblSymbolCollector.collect(result)
        symbolIndex.updateFile(uri, symbols)
        parseCache[uri] = hash to result

        LOG.debug("Analysé $uri : ${symbols.size} symboles, ${result.syntaxErrors.size} erreurs")
        return result
    }

    // ─── Analyse sémantique complète (background) ─────────────────────────────

    /**
     * Analyse sémantique via ParseUnit.treeParser01().
     * Met à jour [symbolIndex] avec les informations de type résolu.
     * Retourne le résultat sémantique (JPNode + TreeParserSymbolScope).
     */
    fun analyzeFileSemantic(content: String, uri: String): AblSemanticResult {
        val hash = content.hashCode()
        semanticCache[uri]?.let { (h, r) -> if (h == hash) return r }

        // Réutilise le parse result en cache — analyse sans re-parser le fichier
        val parseResult = parseCache[uri]?.let { (h, r) -> if (h == hash) r else null }
            ?: analyzeFile(content, uri)
        val result = parserFacade.analyze(parseResult)

        if (result.rootScope != null) {
            val scopeSymbols = AblSymbolCollector.collectFromScope(result.rootScope, uri)
            if (scopeSymbols.isNotEmpty()) symbolIndex.updateFile(uri, scopeSymbols)
        }

        semanticCache[uri] = hash to result
        LOG.debug("Analyse sémantique $uri : scope=${result.rootScope != null}")
        return result
    }

    /**
     * Lance l'analyse sémantique en arrière-plan pour le fichier donné.
     * Non-bloquant — le résultat sera disponible dans [semanticCache] quand prêt.
     */
    fun analyzeSemanticAsync(content: String, uri: String) {
        val hash = content.hashCode()
        if (semanticCache[uri]?.first == hash) return  // déjà à jour
        ApplicationManager.getApplication().executeOnPooledThread {
            try {
                analyzeFileSemantic(content, uri)
            } catch (e: Exception) {
                LOG.warn("Analyse sémantique async échouée pour $uri : ${e.message}")
            }
        }
    }

    /**
     * Retourne le résultat sémantique en cache s'il est disponible,
     * ou null si l'analyse n'a pas encore été effectuée.
     */
    fun getSemanticResult(uri: String): AblSemanticResult? =
        semanticCache[uri]?.second

    // ─── Invalidation ─────────────────────────────────────────────────────────

    fun invalidate(uri: String) {
        parseCache.remove(uri)
        semanticCache.remove(uri)
        symbolIndex.removeFile(uri)
    }

    // ─── Environnement PROPATH ────────────────────────────────────────────────

    fun updateEnvironment() {
        try {
            val config   = project.service<OpenEdgeProjectService>().config
            val basePath = project.basePath ?: return
            val dlcPath  = config.dlcPath ?: System.getenv("DLC") ?: ""

            val propath = config.propath.mapNotNull { pathStr ->
                val resolved = pathStr
                    .replace("\${DLC}", dlcPath)
                    .replace("\$DLC", dlcPath)
                try {
                    val p = Paths.get(resolved)
                    if (p.isAbsolute) p else Paths.get(basePath).resolve(p)
                } catch (_: Exception) { null }
            }.filter { Files.isDirectory(it) }

            if (propath.isNotEmpty()) {
                val env = AblParserFacade.createProjectEnvironment(propath, config.version)
                parserFacade.updateEnvironment(env)
                parseCache.clear()
                semanticCache.clear()
                LOG.info("Environnement PROPATH mis à jour : ${propath.size} entrées")
            }
        } catch (e: Exception) {
            LOG.warn("Impossible de mettre à jour PROPATH : ${e.message}")
        }
    }

    // ─── Indexation initiale ──────────────────────────────────────────────────

    fun buildIndexInBackground() {
        ApplicationManager.getApplication().executeOnPooledThread {
            try {
                val config   = project.service<OpenEdgeProjectService>().config
                val basePath = project.basePath ?: return@executeOnPooledThread
                val dlcPath  = config.dlcPath ?: System.getenv("DLC") ?: ""
                var count    = 0

                config.propath.forEach { pathStr ->
                    val resolved = pathStr
                        .replace("\${DLC}", dlcPath)
                        .replace("\$DLC", dlcPath)
                    val dir = try {
                        val p = Paths.get(resolved)
                        if (p.isAbsolute) p else Paths.get(basePath).resolve(p)
                    } catch (_: Exception) { return@forEach }

                    if (!Files.isDirectory(dir)) return@forEach

                    Files.walk(dir).use { stream ->
                        stream.filter { f ->
                            Files.isRegularFile(f) &&
                            f.fileName.toString().let { n ->
                                n.endsWith(".p") || n.endsWith(".cls") ||
                                n.endsWith(".i") || n.endsWith(".w")
                            }
                        }.forEach { file ->
                            try {
                                val uri     = file.toUri().toString()
                                val content = Files.readString(file)
                                analyzeFile(content, uri)
                                count++
                            } catch (_: Exception) {}
                        }
                    }
                }
                LOG.info("Indexation initiale : $count fichiers, ${symbolIndex.symbolCount} symboles")
            } catch (e: Exception) {
                LOG.warn("Erreur indexation initiale : ${e.message}")
            }
        }
    }
}
