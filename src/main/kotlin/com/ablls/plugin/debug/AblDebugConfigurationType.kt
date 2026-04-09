package com.ablls.plugin.debug

import com.ablls.plugin.language.AblIcons
import com.intellij.execution.configurations.*
import com.intellij.openapi.options.SettingsEditor
import com.intellij.openapi.project.Project
import com.intellij.ui.components.JBTextField
import com.intellij.ui.dsl.builder.panel
import javax.swing.JComponent
import com.intellij.xdebugger.XDebugProcess
import com.intellij.xdebugger.XDebugProcessStarter
import com.intellij.xdebugger.XDebugSession
import com.intellij.xdebugger.XDebuggerManager
import com.intellij.execution.ExecutionResult
import com.intellij.execution.Executor
import com.intellij.execution.runners.ExecutionEnvironment
import com.intellij.execution.runners.ProgramRunner

// ─── Type de configuration ────────────────────────────────────────────────────

class AblDebugConfigurationType : ConfigurationType {
    override fun getDisplayName()              = "ABL Remote Debug"
    override fun getConfigurationTypeDescription() = "Attach to a running OpenEdge process via ABL debugger"
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
}

// ─── Run state ────────────────────────────────────────────────────────────────

class AblDebugRunState(
    private val env: ExecutionEnvironment,
    private val config: AblDebugConfiguration
) : RunProfileState {

    override fun execute(executor: Executor?, runner: ProgramRunner<*>): ExecutionResult? {
        val project = env.project
        XDebuggerManager.getInstance(project).startSession(env, object : XDebugProcessStarter() {
            override fun start(session: XDebugSession): XDebugProcess {
                val conn = AblDebugConnection(config.host, config.port)
                return AblDebugProcess(session, conn)
            }
        })
        return null
    }
}

// ─── Éditeur de configuration ─────────────────────────────────────────────────

class AblDebugConfigurationEditor : SettingsEditor<AblDebugConfiguration>() {
    private val hostField = JBTextField()
    private val portField = JBTextField()

    override fun createEditor(): JComponent = panel {
        row("Host:") { cell(hostField).resizableColumn() }
        row("Port:") { cell(portField).comment("Default: 3075") }
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
