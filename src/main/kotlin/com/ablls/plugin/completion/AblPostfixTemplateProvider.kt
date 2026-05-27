package com.ablls.plugin.completion

import com.intellij.codeInsight.template.postfix.templates.PostfixTemplate
import com.intellij.codeInsight.template.postfix.templates.PostfixTemplateExpressionSelector
import com.intellij.codeInsight.template.postfix.templates.PostfixTemplateProvider
import com.intellij.codeInsight.template.postfix.templates.StringBasedPostfixTemplate
import com.intellij.openapi.editor.Document
import com.intellij.openapi.editor.Editor
import com.intellij.psi.PsiElement
import com.intellij.psi.PsiFile

/**
 * Fournisseur de templates postfix ABL.
 *
 * Permet d'écrire `expr.message` puis Tab pour obtenir `MESSAGE expr.`
 *
 * Templates disponibles :
 *   expr.message  → MESSAGE expr.
 *   expr.run      → RUN expr.
 *   expr.not      → NOT expr
 *   expr.return   → RETURN expr.
 *   expr.if       → IF expr THEN DO: ... END.
 *   expr.ifnot    → IF NOT expr THEN DO: ... END.
 *   expr.alert    → MESSAGE expr VIEW-AS ALERT-BOX INFORMATION.
 */
class AblPostfixTemplateProvider : PostfixTemplateProvider {
    private val templateSet: Set<PostfixTemplate> by lazy {
        setOf(
            AblPostfixTemplate("message", "MESSAGE expr.", "MESSAGE \$EXPR\$.\$END\$", this),
            AblPostfixTemplate("run", "RUN expr.", "RUN \$EXPR\$.\$END\$", this),
            AblPostfixTemplate("not", "NOT expr", "NOT \$EXPR\$\$END\$", this),
            AblPostfixTemplate("return", "RETURN expr.", "RETURN \$EXPR\$.\$END\$", this),
            AblPostfixTemplate("if", "IF expr THEN DO: ... END.", "IF \$EXPR\$ THEN DO:\n    \$END\$\nEND.", this),
            AblPostfixTemplate("ifnot", "IF NOT expr THEN DO: ... END.", "IF NOT \$EXPR\$ THEN DO:\n    \$END\$\nEND.", this),
            AblPostfixTemplate("alert", "MESSAGE expr VIEW-AS ALERT-BOX.", "MESSAGE \$EXPR\$ VIEW-AS ALERT-BOX INFORMATION.\$END\$", this),
        )
    }

    override fun getTemplates(): Set<PostfixTemplate> = templateSet

    override fun isTerminalSymbol(currentChar: Char): Boolean = currentChar == '.'

    override fun preExpand(
        file: PsiFile,
        editor: Editor,
    ) { /* no-op */ }

    override fun preCheck(
        file: PsiFile,
        editor: Editor,
        offset: Int,
    ): PsiFile = file

    override fun afterExpand(
        file: PsiFile,
        editor: Editor,
    ) { /* no-op */ }
}

// ─── Template individuel ──────────────────────────────────────────────────────

private class AblPostfixTemplate(
    key: String,
    example: String,
    private val templateText: String,
    provider: PostfixTemplateProvider,
) : StringBasedPostfixTemplate(
        // id
        key,
        // name
        key,
        // example
        example,
        // selector
        AblExpressionSelector,
        // provider
        provider,
    ) {
    override fun getTemplateString(element: PsiElement): String = templateText

    override fun getElementToRemove(expr: PsiElement): PsiElement = expr
}

// ─── Sélecteur d'expression ───────────────────────────────────────────────────

private object AblExpressionSelector : PostfixTemplateExpressionSelector {
    override fun getExpressions(
        context: PsiElement,
        document: Document,
        offset: Int,
    ): List<PsiElement> {
        val file = context.containingFile ?: return emptyList()
        if (offset < 2) return emptyList()
        val prev = file.findElementAt(offset - 2) ?: return emptyList()
        return if (prev.text.isNotBlank()) listOf(prev) else emptyList()
    }

    override fun hasExpression(
        context: PsiElement,
        document: Document,
        offset: Int,
    ): Boolean = getExpressions(context, document, offset).isNotEmpty()

    @Suppress("UnstableApiUsage")
    override fun getRenderer(): com.intellij.util.Function<PsiElement, String> {
        return com.intellij.util.Function { e -> e.text ?: "" }
    }
}
