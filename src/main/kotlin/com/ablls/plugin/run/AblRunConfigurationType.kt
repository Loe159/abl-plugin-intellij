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
import com.intellij.openapi.fileChooser.FileChooserDescriptorFactory
import com.intellij.openapi.ui.TextFieldWithBrowseButton
import com.intellij.ui.components.JBCheckBox
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
    var workingDirectory: String = ""
    var batchMode: Boolean = true

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

        val args = mutableListOf(executable, "-nosplash", "-p", config.programFile)
        if (config.batchMode) args.add(1, "-b")
        if (config.programParam.isNotBlank()) { args += listOf("-param", config.programParam) }

        val workDir = config.workingDirectory.ifBlank { config.project.basePath ?: "." }
        val commandLine = com.intellij.execution.configurations.GeneralCommandLine(args)
            .withWorkDirectory(workDir)

        val handler = ProcessHandlerFactory.getInstance()
            .createColoredProcessHandler(commandLine)
        ProcessTerminatedListener.attach(handler)
        return handler
    }
}

// ─── Éditeur de configuration (UI) ───────────────────────────────────────────

class AblRunConfigurationEditor : SettingsEditor<AblRunConfiguration>() {

    private val programFileField  = TextFieldWithBrowseButton().apply {
        addBrowseFolderListener("Select ABL Program", null, null,
            FileChooserDescriptorFactory.createSingleFileDescriptor())
    }
    private val programParamField  = JBTextField()
    private val dlcPathField       = TextFieldWithBrowseButton().apply {
        addBrowseFolderListener("Select DLC Directory", null, null,
            FileChooserDescriptorFactory.createSingleFolderDescriptor())
    }
    private val workingDirField    = TextFieldWithBrowseButton().apply {
        addBrowseFolderListener("Select Working Directory", null, null,
            FileChooserDescriptorFactory.createSingleFolderDescriptor())
    }
    private val batchModeCheckbox  = JBCheckBox("Batch mode (-b)")

    override fun createEditor(): JComponent = panel {
        row("Program file (.p):") {
            cell(programFileField).resizableColumn()
        }
        row("Parameters:") {
            cell(programParamField).resizableColumn()
        }
        row("Working directory:") {
            cell(workingDirField).resizableColumn()
        }
        row("DLC path (optional):") {
            cell(dlcPathField).resizableColumn()
            comment("Leave empty to use \$DLC environment variable")
        }
        row("") {
            cell(batchModeCheckbox)
        }
    }

    override fun resetEditorFrom(config: AblRunConfiguration) {
        programFileField.text  = config.programFile
        programParamField.text = config.programParam
        dlcPathField.text      = config.dlcPath
        workingDirField.text   = config.workingDirectory
        batchModeCheckbox.isSelected = config.batchMode
    }

    override fun applyEditorTo(config: AblRunConfiguration) {
        config.programFile       = programFileField.text.trim()
        config.programParam      = programParamField.text.trim()
        config.dlcPath           = dlcPathField.text.trim()
        config.workingDirectory  = workingDirField.text.trim()
        config.batchMode         = batchModeCheckbox.isSelected
    }
}
