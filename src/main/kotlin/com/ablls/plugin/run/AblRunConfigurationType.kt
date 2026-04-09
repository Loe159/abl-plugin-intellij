package com.ablls.plugin.run

import com.ablls.plugin.language.AblFileType
import com.ablls.plugin.language.AblIcons
import com.intellij.execution.configurations.*
import com.intellij.execution.process.OSProcessHandler
import com.intellij.execution.process.ProcessHandlerFactory
import com.intellij.execution.process.ProcessTerminatedListener
import com.intellij.execution.runners.ExecutionEnvironment
import com.intellij.openapi.components.service
import com.intellij.openapi.options.SettingsEditor
import com.intellij.openapi.project.Project
import com.intellij.ui.components.JBTextField
import com.intellij.ui.dsl.builder.panel
import javax.swing.JComponent

// ─── Type de configuration ────────────────────────────────────────────────────

class AblRunConfigurationType : ConfigurationType {
    override fun getDisplayName(): String = "ABL Program"
    override fun getConfigurationTypeDescription(): String = "Run a Progress OpenEdge ABL program"
    override fun getIcon() = AblIcons.FILE
    override fun getId(): String = "ABL_RUN_CONFIGURATION"

    override fun getConfigurationFactories(): Array<ConfigurationFactory> =
        arrayOf(AblRunConfigurationFactory(this))
}

// ─── Factory ──────────────────────────────────────────────────────────────────

class AblRunConfigurationFactory(type: ConfigurationType) : ConfigurationFactory(type) {

    override fun getId(): String = "ABL_RUN_CONFIGURATION_FACTORY"

    override fun createTemplateConfiguration(project: Project): RunConfiguration =
        AblRunConfiguration(project, this)
}

// ─── Configuration ────────────────────────────────────────────────────────────

class AblRunConfiguration(
    project: Project,
    factory: ConfigurationFactory
) : RunConfigurationBase<AblRunConfigurationOptions>(project, factory, "ABL Program") {

    // Options persistées (fichier, paramètres, DLC path...)
    var programFile: String = ""
    var programParam: String = ""
    var dlcPath: String = ""

    override fun getOptions(): AblRunConfigurationOptions =
        super.getOptions() as AblRunConfigurationOptions

    override fun getConfigurationEditor(): SettingsEditor<out RunConfiguration> =
        AblRunConfigurationEditor()

    override fun getState(
        executor: com.intellij.execution.Executor,
        environment: ExecutionEnvironment
    ): CommandLineState {
        return AblRunState(environment, this)
    }
}

// ─── Options persistées ───────────────────────────────────────────────────────

class AblRunConfigurationOptions : RunConfigurationOptions()

// ─── État d'exécution ─────────────────────────────────────────────────────────

class AblRunState(
    private val environment: ExecutionEnvironment,
    private val config: AblRunConfiguration
) : CommandLineState(environment) {

    override fun startProcess(): OSProcessHandler {
        // Résoudre l'exécutable Progress (_progres ou prowin.exe)
        val dlc = config.dlcPath.ifBlank {
            System.getenv("DLC") ?: "/usr/dlc"
        }
        val isWindows = System.getProperty("os.name").lowercase().contains("win")
        val executable = if (isWindows) "$dlc/bin/prowin.exe" else "$dlc/bin/_progres"

        val commandLine = com.intellij.execution.configurations.GeneralCommandLine(
            executable,
            "-b",                          // Mode batch
            "-nosplash",
            "-p", config.programFile
        ).apply {
            if (config.programParam.isNotBlank()) {
                addParameters("-param", config.programParam)
            }
            config.project.basePath?.let { setWorkDirectory(it as String?) }
        }

        val handler = ProcessHandlerFactory.getInstance()
            .createColoredProcessHandler(commandLine)
        ProcessTerminatedListener.attach(handler)
        return handler
    }
}

// ─── Éditeur de configuration (UI) ───────────────────────────────────────────

class AblRunConfigurationEditor : SettingsEditor<AblRunConfiguration>() {

    private val programFileField = JBTextField()
    private val programParamField = JBTextField()
    private val dlcPathField = JBTextField()

    override fun createEditor(): JComponent = panel {
        row("Program file (.p):") {
            cell(programFileField).resizableColumn()
        }
        row("Parameters:") {
            cell(programParamField).resizableColumn()
        }
        row("DLC path (optional):") {
            cell(dlcPathField).resizableColumn()
            comment("Leave empty to use \$DLC environment variable")
        }
    }

    override fun resetEditorFrom(config: AblRunConfiguration) {
        programFileField.text  = config.programFile
        programParamField.text = config.programParam
        dlcPathField.text      = config.dlcPath
    }

    override fun applyEditorTo(config: AblRunConfiguration) {
        config.programFile  = programFileField.text.trim()
        config.programParam = programParamField.text.trim()
        config.dlcPath      = dlcPathField.text.trim()
    }
}
