package com.ablls.plugin.completion

import com.ablls.plugin.language.AblLanguage
import com.intellij.codeInsight.template.TemplateActionContext
import com.intellij.codeInsight.template.TemplateContextType

class AblTemplateContextType : TemplateContextType("ABL", "ABL") {
    override fun isInContext(templateActionContext: TemplateActionContext): Boolean {
        return templateActionContext.file.language == AblLanguage
    }
}
