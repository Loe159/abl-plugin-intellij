package com.ablls.plugin.run

import com.intellij.execution.actions.ConfigurationContext
import com.intellij.execution.actions.LazyRunConfigurationProducer
import com.intellij.execution.configurations.ConfigurationFactory
import com.intellij.openapi.util.Ref
import com.intellij.psi.PsiElement

/**
 * Crée automatiquement une configuration "ABL Program" quand l'utilisateur
 * fait clic-droit → Run sur un fichier .p/.cls/.w, ou quand il est positionné
 * sur ce type de fichier (active les boutons Run/Debug dans la barre d'outils).
 */
class AblRunConfigurationProducer : LazyRunConfigurationProducer<AblRunConfiguration>() {

    override fun getConfigurationFactory(): ConfigurationFactory =
        AblRunConfigurationType().configurationFactories[0]

    override fun setupConfigurationFromContext(
        configuration: AblRunConfiguration,
        context: ConfigurationContext,
        sourceElement: Ref<PsiElement>
    ): Boolean {
        val file = context.location?.virtualFile ?: return false
        if (file.extension?.lowercase() !in listOf("p", "cls", "w")) return false

        configuration.programFile = file.path
        configuration.name        = file.nameWithoutExtension
        return true
    }

    override fun isConfigurationFromContext(
        configuration: AblRunConfiguration,
        context: ConfigurationContext
    ): Boolean {
        val file = context.location?.virtualFile ?: return false
        return file.path == configuration.programFile
    }
}
