package com.ablls.plugin.debug

import com.ablls.plugin.language.AblIcons
import com.intellij.execution.Executor
import com.intellij.execution.configurations.*
import com.intellij.execution.runners.ExecutionEnvironment
import com.intellij.execution.runners.ProgramRunner
import com.intellij.openapi.options.SettingsEditor
import com.intellij.openapi.project.Project
import com.intellij.ui.components.JBTextField
import com.intellij.ui.dsl.builder.panel
import org.jdom.Element
import javax.swing.JComponent

// ─── Type de configuration ────────────────────────────────────────────────────

class AblDebugConfigurationType : ConfigurationType {
    override fun getDisplayName()              = "ABL Remote Debug"
    override fun getConfigurationTypeDescription() =
        "Attach the IntelliJ debugger to a running OpenEdge process (-debugport)"
    override fun getIcon()                     = AblIcons.FILE
    override fun getId()                       = "ABL_DEBUG_CONFIGURATION"
    override fun getConfigurationFactories()   = arrayOf(AblDebugConfigurationFactory(this))
}

class AblDebugConfigurationFactory(type: ConfigurationType) : ConfigurationFactory(type) {
    override fun getId() = "ABL_DEBUG_CONFIGURATION_FACTORY"
    override fun createTemplateConfiguration(project: Project): RunConfiguration =
        AblDebugConfiguration(project, this)
}

// ─── Configuration ────────────────────────────────────────────────────────────

class AblDebugConfiguration(
    project: Project,
    factory: ConfigurationFactory
) : RunConfigurationBase<RunConfigurationOptions>(project, factory, "ABL Remote Debug") {

    var host: String = "localhost"
    var port: Int    = 3075

    override fun getOptions() = super.getOptions() as RunConfigurationOptions

    override fun getConfigurationEditor(): SettingsEditor<out RunConfiguration> =
        AblDebugConfigurationEditor()

    override fun getState(executor: Executor, environment: ExecutionEnvironment): RunProfileState =
        AblDebugRunState(environment, this)

    // ── Persistance ──────────────────────────────────────────────────────────

    override fun writeExternal(element: Element) {
        super.writeExternal(element)
        element.setAttribute("host", host)
        element.setAttribute("port", port.toString())
    }

    override fun readExternal(element: Element) {
        super.readExternal(element)
        host = element.getAttributeValue("host") ?: "localhost"
        port = element.getAttributeValue("port")?.toIntOrNull() ?: 3075
    }

    // ── Validation ────────────────────────────────────────────────────────────

    @Throws(RuntimeConfigurationException::class)
    override fun checkConfiguration() {
        if (host.isBlank())
            throw RuntimeConfigurationError("Host is required")
        if (port !in 1..65535)
            throw RuntimeConfigurationError("Port must be between 1 and 65535")
    }
}

// ─── Run state ────────────────────────────────────────────────────────────────
// La connexion et la session XDebug sont gérées par AblProgramRunner.
// Ce state est un placeholder pour satisfaire l'API IntelliJ.

class AblDebugRunState(
    @Suppress("unused") private val env: ExecutionEnvironment,
    @Suppress("unused") val config: AblDebugConfiguration
) : RunProfileState {
    override fun execute(executor: Executor?, runner: ProgramRunner<*>): com.intellij.execution.ExecutionResult? = null
}

// ─── Éditeur de configuration ─────────────────────────────────────────────────

class AblDebugConfigurationEditor : SettingsEditor<AblDebugConfiguration>() {

    private val hostField = JBTextField()
    private val portField = JBTextField()

    override fun createEditor(): JComponent = panel {
        row("Host:") {
            cell(hostField).resizableColumn()
                .comment("Hostname or IP of the machine running OpenEdge")
        }
        row("Port:") {
            cell(portField)
                .comment("Port passed to -debugport (default: 3075)")
        }
        row {
            comment(
                "<b>Setup:</b> start OpenEdge with <code>_progres -p yourfile.p -debugport 3075</code> " +
                "then click Debug here to attach."
            )
        }
    }

    override fun resetEditorFrom(config: AblDebugConfiguration) {
        hostField.text = config.host
        portField.text = config.port.toString()
    }

    override fun applyEditorTo(config: AblDebugConfiguration) {
        config.host = hostField.text.trim().ifBlank { "localhost" }
        config.port = portField.text.trim().toIntOrNull() ?: 3075
    }
}
