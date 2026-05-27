package com.ablls.plugin.navigation

import com.ablls.plugin.core.AblProjectAnalysisService
import com.ablls.plugin.language.AblLanguage
import com.ablls.plugin.parser.AblTokenTypes
import com.ablls.plugin.project.OpenEdgeProjectService
import com.intellij.codeInsight.navigation.actions.GotoDeclarationHandler
import com.intellij.openapi.components.service
import com.intellij.openapi.editor.Editor
import com.intellij.openapi.vfs.LocalFileSystem
import com.intellij.openapi.vfs.VirtualFileManager
import com.intellij.psi.PsiDocumentManager
import com.intellij.psi.PsiElement
import com.intellij.psi.PsiManager
import org.prorefactor.core.JPNode
import org.prorefactor.treeparser.TreeParserSymbolScope
import java.io.File
import java.nio.file.Paths

/**
 * Go to Declaration pour :
 *   - Les symboles ABL (variables, procédures, classes…) via l'index
 *   - Les includes ABL `{filename.i}` → navigue vers le fichier source
 */
class AblGotoDeclarationHandler : GotoDeclarationHandler {
    @Suppress("ReturnCount")
    override fun getGotoDeclarationTargets(
        sourceElement: PsiElement?,
        offset: Int,
        editor: Editor,
    ): Array<PsiElement>? {
        if (sourceElement == null) return null
        if (sourceElement.containingFile?.language != AblLanguage) return null

        val project = sourceElement.project

        // ── Cas 1 : include `{filename.i}` ───────────────────────────────────
        if (sourceElement.node?.elementType == AblTokenTypes.PREPROCESSOR) {
            val text = sourceElement.text ?: return null
            val includeFile = resolveInclude(text, project) ?: return null
            val psiFile =
                PsiManager.getInstance(project).findFile(includeFile)
                    ?: return null
            return arrayOf(psiFile)
        }

        // ── Cas 2 : symbole défini par l'utilisateur ──────────────────────────
        val word = sourceElement.text?.trim() ?: return null
        if (word.isBlank() || word.length < 2) return null

        val currentFile = sourceElement.containingFile ?: return null
        val uri = currentFile.virtualFile?.url ?: return null
        val service = project.service<AblProjectAnalysisService>()

        // ── Résolution sémantique via TreeParserSymbolScope ───────────────────
        val rootScope = service.getSemanticResult(uri)?.rootScope
        if (rootScope != null) {
            val doc = PsiDocumentManager.getInstance(project).getDocument(currentFile)
            if (doc != null) {
                val elemOffset = sourceElement.textOffset
                val lineIdx = doc.getLineNumber(elemOffset)
                val cursorLine = lineIdx + 1 // proparse est 1-based

                val defNode = findNearestDefinition(rootScope, word, cursorLine)
                if (defNode?.token != null) {
                    val defLineIdx = (defNode.token.line - 1).coerceIn(0, doc.lineCount - 1)
                    val defCol = defNode.token.charPositionInLine
                    val defOffset = (doc.getLineStartOffset(defLineIdx) + defCol).coerceAtMost(doc.textLength)
                    val target = currentFile.findElementAt(defOffset)
                    if (target != null) return arrayOf(target)
                }
            }
        }

        // ── Fallback : recherche par nom dans l'index ─────────────────────────
        val symbols = service.symbolIndex.findByName(word, uri)
        if (symbols.isEmpty()) return null

        val targets =
            symbols.mapNotNull { symbol ->
                if (symbol.uri == null) return@mapNotNull null
                val vf =
                    VirtualFileManager.getInstance().findFileByUrl(symbol.uri)
                        ?: return@mapNotNull null
                val psiFile =
                    PsiManager.getInstance(project).findFile(vf)
                        ?: return@mapNotNull null
                val doc =
                    PsiDocumentManager.getInstance(project).getDocument(psiFile)
                        ?: return@mapNotNull null

                val range = symbol.definitionRange
                val targetLine = (range?.startLine ?: 0).coerceIn(0, doc.lineCount - 1)
                val lineStart = doc.getLineStartOffset(targetLine)
                val col = range?.startCol ?: 0
                val targetOffset = (lineStart + col).coerceAtMost(doc.textLength)

                psiFile.findElementAt(targetOffset)
            }

        return if (targets.isEmpty()) null else targets.toTypedArray()
    }

    // ─── Résolution de définition par scope ──────────────────────────────────

    /**
     * Among all symbols named [word] in [scope] (recursively including child scopes),
     * returns the define-node of the one with the highest definition line ≤ [cursorLine].
     *
     * Approximates scope-aware resolution by preferring the nearest preceding definition.
     * Handles the common case (local variable shadowing a global in a nested procedure)
     * correctly. Known limitation: walks ALL child scopes, so a variable in a sibling
     * procedure can win over the global when the cursor is in a different procedure that
     * refers to the global. Full correctness would require bounding the recursion to
     * the routine that contains the cursor line.
     */
    private fun findNearestDefinition(
        scope: TreeParserSymbolScope,
        word: String,
        cursorLine: Int,
    ): JPNode? {
        var best: JPNode? = null
        var bestLine = 0

        fun checkNode(node: JPNode?) {
            val line = node?.token?.line ?: return
            if (line in 1..cursorLine && line > bestLine) {
                best = node
                bestLine = line
            }
        }

        for (v in runCatching { scope.variables }.getOrNull() ?: emptyList()) {
            if (v.name.equals(word, ignoreCase = true)) {
                checkNode(runCatching { v.getDefineNode() }.getOrNull())
            }
        }
        for (r in runCatching { scope.routines }.getOrNull() ?: emptyList()) {
            if (r.name.equals(word, ignoreCase = true)) {
                checkNode(runCatching { r.getDefineNode() }.getOrNull())
            }
        }
        for (child in runCatching { scope.childScopes }.getOrNull() ?: emptyList()) {
            val childBest = findNearestDefinition(child, word, cursorLine)
            val childLine = childBest?.token?.line ?: 0
            if (childLine > bestLine) {
                best = childBest
                bestLine = childLine
            }
        }
        return best
    }

    // ─── Résolution d'include ────────────────────────────────────────────────

    /**
     * Résout `{include.i}` ou `{path/to/include.i &arg=val}` vers un VirtualFile.
     *
     * Ordre de résolution :
     *   1. Relatif au fichier courant
     *   2. Dans chaque entrée du PROPATH (openedge-project.json)
     *   3. Dans le dossier DLC/tty (si dlcPath configuré)
     */
    private fun resolveInclude(
        tokenText: String,
        project: com.intellij.openapi.project.Project,
    ): com.intellij.openapi.vfs.VirtualFile? {
        // Extraire le nom de fichier entre { et le premier espace ou }
        // ex: "{myinc.i}" → "myinc.i"
        // ex: "{myinc.i &param=1}" → "myinc.i"
        if (!tokenText.startsWith("{")) return null
        val inner = tokenText.removePrefix("{").removeSuffix("}").trim()
        val filename = inner.split("\\s+".toRegex()).firstOrNull()?.trim() ?: return null
        if (filename.isEmpty()) return null

        val config = project.service<OpenEdgeProjectService>().config
        val basePath = project.basePath ?: return null
        val dlcPath = config.dlcPath ?: System.getenv("DLC") ?: ""

        // Construire la liste des dossiers de recherche
        val searchDirs =
            buildList {
                // 1. Répertoire courant du projet
                add(basePath)

                // 2. Entrées du PROPATH
                for (pathStr in config.propath) {
                    val resolved =
                        pathStr
                            .replace("\${DLC}", dlcPath)
                            .replace("\$DLC", dlcPath)
                    try {
                        val p = Paths.get(resolved)
                        add(if (p.isAbsolute) resolved else Paths.get(basePath).resolve(p).toString())
                    } catch (_: Exception) {
                    }
                }
            }

        for (dir in searchDirs) {
            val candidate = File(dir, filename)
            if (candidate.isFile) {
                return LocalFileSystem.getInstance().findFileByIoFile(candidate)
            }
        }

        return null
    }
}
