package com.ablls.plugin.refactor

import com.ablls.plugin.core.AblProjectAnalysisService
import com.ablls.plugin.language.AblLanguage
import com.ablls.plugin.parser.AblLexerAdapter
import com.ablls.plugin.parser.AblTokenTypes
import com.intellij.openapi.actionSystem.DataContext
import com.intellij.openapi.command.WriteCommandAction
import com.intellij.openapi.components.service
import com.intellij.openapi.editor.Editor
import com.intellij.openapi.project.Project
import com.intellij.openapi.ui.Messages
import com.intellij.psi.PsiDocumentManager
import com.intellij.psi.PsiElement
import com.intellij.psi.PsiFile
import com.intellij.refactoring.rename.PsiElementRenameHandler
import com.intellij.refactoring.rename.RenameHandler
import org.prorefactor.core.JPNode
import org.prorefactor.treeparser.TreeParserSymbolScope

/**
 * Handler de renommage sémantique pour les symboles ABL (Shift+F6).
 *
 * Lorsque le résultat sémantique est disponible ([AblProjectAnalysisService.getSemanticResult]),
 * le renommage est scope-aware : seules les occurrences qui résolvent vers la MÊME définition
 * que le curseur sont renommées. Les homonymes dans d'autres scopes sont préservés.
 *
 * Algorithme (pour chaque occurrence du mot dans le fichier) :
 *   1. Tokeniser via [AblLexerAdapter] → skip strings, commentaires, preprocesseur.
 *   2. Pour chaque token IDENTIFIER correspondant, appeler [findNearestDef] avec la ligne
 *      de ce token : si la définition retournée est identique (même ligne, même colonne)
 *      à celle du curseur → l'occurrence est renommée.
 *
 * Limitation connue : toutes les variantes de casse sont remplacées par le nouveau nom
 * exact fourni par l'utilisateur (ABL est insensible à la casse).
 *
 * Si la sémantique n'est pas en cache, délègue au renommage textuel IntelliJ standard.
 */
class AblRenameHandler : RenameHandler {

    /** Contourne le dialog de saisie dans les tests. Remettre à null après chaque test. */
    internal var testNewName: String? = null

    override fun isAvailableOnDataContext(dataContext: DataContext): Boolean {
        val editor  = dataContext.getData(com.intellij.openapi.actionSystem.CommonDataKeys.EDITOR) ?: return false
        val psiFile = dataContext.getData(com.intellij.openapi.actionSystem.CommonDataKeys.PSI_FILE) ?: return false
        return psiFile.language == AblLanguage
    }

    override fun invoke(project: Project, editor: Editor, file: PsiFile, dataContext: DataContext) {
        val offset  = editor.caretModel.offset
        val element = file.findElementAt(offset) ?: return
        val word    = element.text?.trim() ?: return
        if (word.isBlank() || word.length < 2) return

        val uri     = file.virtualFile?.url ?: return
        val service = project.service<AblProjectAnalysisService>()
        val doc     = PsiDocumentManager.getInstance(project).getDocument(file) ?: return
        val cursorLine = doc.getLineNumber(offset) + 1  // proparse est 1-based

        val rootScope = service.getSemanticResult(uri)?.rootScope
        val targetDef = rootScope?.let { findNearestDef(it, word, cursorLine) }

        val newName = testNewName
            ?: Messages.showInputDialog(
                project,
                "Renommer '$word' en : (toutes les variantes de casse seront remplacées par le texte exact)",
                "Renommer le symbole ABL",
                Messages.getQuestionIcon(),
                word,
                null
            )?.trim()
            ?: return
        if (newName.isBlank() || newName == word) return

        if (targetDef != null && rootScope != null) {
            performScopeAwareRename(project, file, word, newName, rootScope, targetDef)
        } else {
            val symbols = service.symbolIndex.findByName(word, uri)
            if (symbols.isNotEmpty())
                PsiElementRenameHandler.invoke(element, project, element, editor)
        }
    }

    override fun invoke(project: Project, elements: Array<out PsiElement>, dataContext: DataContext) {
        // Renommage multi-éléments non supporté depuis un contexte hors-éditeur
    }

    // ─── Renommage scope-aware ────────────────────────────────────────────────

    /**
     * Applique le renommage [oldName] → [newName] uniquement sur les occurrences qui résolvent
     * vers [targetDef]. Les tokens sont identifiés via [AblLexerAdapter] (strings et commentaires
     * exclus). Les remplacements sont appliqués en ordre décroissant pour préserver les offsets.
     */
    internal fun performScopeAwareRename(
        project: Project,
        file: PsiFile,
        oldName: String,
        newName: String,
        rootScope: TreeParserSymbolScope,
        targetDef: JPNode
    ) {
        val doc        = PsiDocumentManager.getInstance(project).getDocument(file) ?: return
        val targetLine = targetDef.token?.line ?: return
        val targetCol  = targetDef.token?.charPositionInLine ?: return

        val tokenRanges = findIdentifierTokenRanges(doc.text, oldName)
        val toRename = tokenRanges
            .filter { range ->
                val matchLine = doc.getLineNumber(range.first) + 1  // proparse 1-based
                val def = findNearestDef(rootScope, oldName, matchLine)
                def?.token?.line == targetLine && def.token?.charPositionInLine == targetCol
            }
            .sortedByDescending { it.first }  // ordre décroissant pour stabilité des offsets

        if (toRename.isEmpty()) return

        WriteCommandAction.runWriteCommandAction(
            project, "Rename '$oldName' → '$newName'", null, {
                toRename.forEach { range ->
                    doc.replaceString(range.first, range.last + 1, newName)
                }
                PsiDocumentManager.getInstance(project).commitDocument(doc)
            }, file
        )
    }

    // ─── Scan de tokens via le lexer ABL ─────────────────────────────────────

    /**
     * Retourne les plages (startOffset until endOffset) de tous les tokens IDENTIFIER
     * dans [text] dont le texte correspond à [name] (insensible à la casse).
     * Les strings, commentaires et preprocesseur sont ignorés par le lexer.
     */
    private fun findIdentifierTokenRanges(text: String, name: String): List<IntRange> {
        val lexer = AblLexerAdapter()
        lexer.start(text, 0, text.length, 0)
        val ranges = mutableListOf<IntRange>()
        while (lexer.tokenType != null) {
            if (lexer.tokenType == AblTokenTypes.IDENTIFIER) {
                val tokenText = text.substring(lexer.tokenStart, lexer.tokenEnd)
                if (tokenText.equals(name, ignoreCase = true))
                    ranges.add(lexer.tokenStart until lexer.tokenEnd)
            }
            lexer.advance()
        }
        return ranges
    }

    // ─── Résolution de définition par scope ──────────────────────────────────

    /**
     * Parmi tous les symboles nommés [word] dans [scope] (récursivement),
     * retourne le define-node de celui dont la ligne de définition est la plus haute ≤ [line].
     *
     * Même algorithme que AblGotoDeclarationHandler.findNearestDefinition.
     * Limitation : les scopes frères (procédures non ancêtres du curseur) sont inclus.
     */
    internal fun findNearestDef(scope: TreeParserSymbolScope, word: String, line: Int): JPNode? {
        var best: JPNode? = null
        var bestLine = 0

        fun check(node: JPNode?) {
            val l = node?.token?.line ?: return
            if (l in 1..line && l > bestLine) { best = node; bestLine = l }
        }

        for (v in runCatching { scope.variables }.getOrNull() ?: emptyList()) {
            if (v.name.equals(word, ignoreCase = true))
                check(runCatching { v.getDefineNode() }.getOrNull())
        }
        for (r in runCatching { scope.routines }.getOrNull() ?: emptyList()) {
            if (r.name.equals(word, ignoreCase = true))
                check(runCatching { r.getDefineNode() }.getOrNull())
        }
        for (child in runCatching { scope.childScopes }.getOrNull() ?: emptyList()) {
            val childBest = findNearestDef(child, word, line)
            val childLine = childBest?.token?.line ?: 0
            if (childLine > bestLine) { best = childBest; bestLine = childLine }
        }
        return best
    }
}
