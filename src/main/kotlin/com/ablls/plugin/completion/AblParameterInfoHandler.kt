package com.ablls.plugin.completion

import com.ablls.plugin.core.AblProjectAnalysisService
import com.ablls.plugin.language.AblLanguage
import com.intellij.lang.parameterInfo.*
import com.intellij.openapi.components.service
import com.intellij.psi.PsiElement
import com.intellij.psi.PsiFile
import org.prorefactor.treeparser.TreeParserSymbolScope
import org.prorefactor.treeparser.symbols.Routine

/**
 * Parameter Info Handler ABL — affiche la signature d'appel via Ctrl+P.
 *
 * Quand le curseur est à l'intérieur d'un appel de procédure ou de fonction ABL,
 * Ctrl+P (ou affichage automatique après `(`) affiche la signature complète avec
 * les noms et types de paramètres. Le paramètre courant est mis en surbrillance.
 *
 * Exemple :
 *   myRoutine(INPUT cust-num, OUTPUT cust-name)
 *                ^^^^^^^^^^^  ← paramètre courant en gras
 *
 * Stratégie :
 *   1. Trouver le nom de la routine avant le `(` le plus proche non fermé.
 *   2. Chercher la routine dans le TreeParserSymbolScope.
 *   3. Construire la signature "PARAM_1, PARAM_2, …" et la passer à IntelliJ.
 *   4. Lors de updateParameterInfo, compter les virgules pour identifier
 *      le paramètre actif.
 */
class AblParameterInfoHandler : ParameterInfoHandler<PsiElement, AblParameterInfoHandler.AblCallInfo> {

    data class AblCallInfo(
        val routineName: String,
        val params: List<String>,
        val fullSignature: String
    )

    // ─── Recherche de l'élément porteur de l'info ────────────────────────────

    override fun findElementForParameterInfo(context: CreateParameterInfoContext): PsiElement? {
        val file   = context.file ?: return null
        if (file.language != AblLanguage) return null
        val offset = context.offset
        return findCallAnchor(file, offset)
    }

    override fun findElementForUpdatingParameterInfo(context: UpdateParameterInfoContext): PsiElement? {
        val file = context.file ?: return null
        return findCallAnchor(file, context.offset)
    }

    // ─── Affichage initial ────────────────────────────────────────────────────

    override fun showParameterInfo(element: PsiElement, context: CreateParameterInfoContext) {
        val callInfo = buildCallInfo(element) ?: return
        context.itemsToShow = arrayOf(callInfo)
    }

    // ─── Mise à jour du paramètre actif ──────────────────────────────────────

    override fun updateParameterInfo(parameterOwner: PsiElement, context: UpdateParameterInfoContext) {
        val text     = parameterOwner.containingFile?.text ?: return
        val offset   = context.offset
        val openParen = findOpenParenOffset(text, offset) ?: return
        val paramIdx  = countCommas(text, openParen + 1, offset)
        context.setCurrentParameter(paramIdx)
    }

    // ─── Rendu de la popup ────────────────────────────────────────────────────

    override fun updateUI(callInfo: AblCallInfo?, context: ParameterInfoUIContext) {
        callInfo ?: return
        if (callInfo.params.isEmpty()) {
            context.setupUIComponentPresentation(
                "(no parameters)", 0, 0, false, false, false,
                context.defaultParameterColor
            )
            return
        }

        val currentIdx = context.currentParameterIndex
        val text       = callInfo.params.joinToString(", ")
        var start      = 0
        var end        = text.length

        if (currentIdx in callInfo.params.indices) {
            var pos = 0
            for (i in 0 until currentIdx) {
                pos += callInfo.params[i].length + 2  // +2 for ", "
            }
            start = pos
            end   = pos + callInfo.params[currentIdx].length
        }

        context.setupUIComponentPresentation(
            text,
            start,
            end,
            !context.isUIComponentEnabled,
            false,
            currentIdx < 0 || currentIdx >= callInfo.params.size,
            context.defaultParameterColor
        )
    }

    // ─── Helpers ──────────────────────────────────────────────────────────────

    /**
     * Trouve le PsiElement correspondant au nom de la routine appelée
     * (le token juste avant le `(` non fermé le plus proche du curseur).
     */
    private fun findCallAnchor(file: PsiFile, offset: Int): PsiElement? {
        val text = file.text
        val openParenPos = findOpenParenOffset(text, offset) ?: return null
        if (openParenPos < 1) return null
        // Le nom de la routine est le token (lettres/tirets) juste avant `(`
        var end = openParenPos - 1
        while (end >= 0 && text[end].isWhitespace()) end--
        if (end < 0) return null
        var start = end
        while (start > 0 && (text[start - 1].isLetterOrDigit() || text[start - 1] == '-' || text[start - 1] == '_')) start--
        if (start > end) return null
        return file.findElementAt(start)
    }

    /**
     * Cherche le décalage du `(` non fermé le plus proche avant [offset].
     */
    private fun findOpenParenOffset(text: String, offset: Int): Int? {
        var depth = 0
        var i = minOf(offset - 1, text.length - 1)
        while (i >= 0) {
            when (text[i]) {
                ')' -> depth++
                '(' -> {
                    if (depth == 0) return i
                    depth--
                }
            }
            i--
        }
        return null
    }

    /**
     * Compte les virgules de niveau 0 dans [text] entre [from] et [to]
     * pour déterminer l'index du paramètre actif.
     */
    private fun countCommas(text: String, from: Int, to: Int): Int {
        var count = 0
        var depth = 0
        for (i in from until minOf(to, text.length)) {
            when (text[i]) {
                '(' -> depth++
                ')' -> if (depth > 0) depth--
                ',' -> if (depth == 0) count++
            }
        }
        return count
    }

    /**
     * Construit l'objet [AblCallInfo] pour la routine dont l'élément anchor correspond.
     * Cherche dans le scope sémantique du fichier courant.
     */
    private fun buildCallInfo(element: PsiElement): AblCallInfo? {
        val routineName = element.text?.trim()?.takeIf { it.isNotBlank() } ?: return null
        val uri         = element.containingFile?.virtualFile?.url ?: return null
        val service     = element.project.service<AblProjectAnalysisService>()
        val scope       = service.getSemanticResult(uri)?.rootScope ?: return null

        val routine = findRoutineInScope(scope, routineName) ?: return null
        val params  = buildParamLabels(routine)

        val sig = runCatching { routine.ideSignature }.getOrNull()
            ?: runCatching { routine.signature }.getOrNull()
            ?: routineName

        return AblCallInfo(routineName, params, sig)
    }

    private fun findRoutineInScope(scope: TreeParserSymbolScope, name: String): Routine? {
        for (r in runCatching { scope.routines }.getOrNull() ?: emptyList()) {
            if (r.name.equals(name, ignoreCase = true)) return r
        }
        for (child in runCatching { scope.childScopes }.getOrNull() ?: emptyList()) {
            findRoutineInScope(child, name)?.let { return it }
        }
        return null
    }

    private fun buildParamLabels(routine: Routine): List<String> {
        val params = runCatching { routine.parameters }.getOrNull() ?: return emptyList()
        return params.mapNotNull { param ->
            val name = runCatching {
                param.javaClass.getMethod("getName").invoke(param) as? String
            }.getOrNull() ?: return@mapNotNull null
            val dir = runCatching {
                param.javaClass.methods
                    .firstOrNull { it.name == "getDirectionILB" || it.name == "getDirection" }
                    ?.invoke(param)?.toString()
            }.getOrNull() ?: "INPUT"
            val type = runCatching {
                param.javaClass.getMethod("getDataType").invoke(param)?.toString()
            }.getOrNull()
            if (type != null) "$dir $name AS $type" else "$dir $name"
        }
    }
}
