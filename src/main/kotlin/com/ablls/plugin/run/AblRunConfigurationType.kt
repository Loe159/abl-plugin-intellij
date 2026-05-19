package com.ablls.plugin.run

import com.ablls.plugin.language.AblFileType
import com.ablls.plugin.language.AblIcons
import com.ablls.plugin.project.OpenEdgeProjectService
import com.ablls.plugin.project.resolveOpenEdgeSdkHome
import com.intellij.execution.ExecutionException
import com.intellij.execution.configurations.*
import com.intellij.execution.process.OSProcessHandler
import com.intellij.execution.process.ProcessHandlerFactory
import com.intellij.execution.process.ProcessTerminatedListener
import com.intellij.execution.runners.ExecutionEnvironment
import com.intellij.openapi.components.service
import com.intellij.openapi.fileChooser.FileChooserDescriptorFactory
import com.intellij.openapi.options.SettingsEditor
import com.intellij.openapi.project.Project
import com.intellij.openapi.ui.TextFieldWithBrowseButton
import com.intellij.ui.components.JBCheckBox
import com.intellij.ui.components.JBTextField
import com.intellij.ui.dsl.builder.panel
import org.jdom.Element
import java.io.File
import javax.swing.JComponent

// ─── Type de configuration ────────────────────────────────────────────────────

class AblRunConfigurationType : ConfigurationType {
    override fun getDisplayName()                  = "ABL Program"
    override fun getConfigurationTypeDescription() = "Run or debug a Progress OpenEdge ABL program"
    override fun getIcon()                         = AblIcons.FILE
    override fun getId()                           = "ABL_RUN_CONFIGURATION"
    override fun getConfigurationFactories()       = arrayOf(AblRunConfigurationFactory(this))
}

// ─── Factory ──────────────────────────────────────────────────────────────────

class AblRunConfigurationFactory(type: ConfigurationType) : ConfigurationFactory(type) {
    override fun getId() = "ABL_RUN_CONFIGURATION_FACTORY"
    override fun createTemplateConfiguration(project: Project): RunConfiguration =
        AblRunConfiguration(project, this)
}

// ─── Configuration ────────────────────────────────────────────────────────────

/**
 * IMPORTANT : on utilise RunConfigurationOptions (pas de sous-classe custom)
 * pour éviter un ClassCastException lors de la création de la config depuis le "+" menu.
 */
class AblRunConfiguration(
    project: Project,
    factory: ConfigurationFactory
) : RunConfigurationBase<RunConfigurationOptions>(project, factory, "ABL Program") {

    var programFile:      String  = ""
    var programParam:     String  = ""
    var dlcPath:          String  = ""
    var workingDirectory: String  = ""
    var batchMode:        Boolean = true
    /** Port du debugger OE. 0 = pas de debug (exécution normale). */
    var debugPort:        Int     = 0

    override fun getConfigurationEditor(): SettingsEditor<out RunConfiguration> =
        AblRunConfigurationEditor()

    override fun getState(
        executor: com.intellij.execution.Executor,
        env: ExecutionEnvironment
    ): CommandLineState = AblRunState(env, this)

    // ── Persistance XML ──────────────────────────────────────────────────────

    override fun writeExternal(element: Element) {
        super.writeExternal(element)
        element.setAttribute("programFile",      programFile)
        element.setAttribute("programParam",     programParam)
        element.setAttribute("dlcPath",          dlcPath)
        element.setAttribute("workingDirectory", workingDirectory)
        element.setAttribute("batchMode",        batchMode.toString())
        element.setAttribute("debugPort",        debugPort.toString())
    }

    override fun readExternal(element: Element) {
        super.readExternal(element)
        programFile      = element.getAttributeValue("programFile")      ?: ""
        programParam     = element.getAttributeValue("programParam")     ?: ""
        dlcPath          = element.getAttributeValue("dlcPath")          ?: ""
        workingDirectory = element.getAttributeValue("workingDirectory") ?: ""
        batchMode        = element.getAttributeValue("batchMode")?.toBooleanStrictOrNull() ?: true
        debugPort        = element.getAttributeValue("debugPort")?.toIntOrNull() ?: 0
    }

    // ── Validation ────────────────────────────────────────────────────────────

    @Throws(RuntimeConfigurationException::class)
    override fun checkConfiguration() {
        if (programFile.isBlank())
            throw RuntimeConfigurationError("Program file (.p) is required")

        // Mirror resolveDlc() priority: field → SDK → openedge-project.json → $DLC
        val resolvedDlc = dlcPath.ifBlank { null }
            ?: resolveOpenEdgeSdkHome(project)
            ?: runCatching { project.service<OpenEdgeProjectService>().config.dlcPath }.getOrNull()
            ?: System.getenv("DLC")

        if (resolvedDlc.isNullOrBlank())
            throw RuntimeConfigurationWarning(
                "DLC path not configured — set it in File → Project Structure → SDKs (OpenEdge ABL), " +
                "in the run config, in openedge-project.json (\"dlcPath\"), or via \$DLC"
            )

        if (debugPort in 1..1023)
            throw RuntimeConfigurationWarning(
                "Debug port $debugPort is in the privileged range (< 1024) — it may be blocked on Windows.\n" +
                "Use 3075 or higher, or leave 0 for automatic port selection."
            )
    }
}

// ─── État d'exécution ─────────────────────────────────────────────────────────

class AblRunState(
    environment: ExecutionEnvironment,
    val config: AblRunConfiguration
) : CommandLineState(environment) {

    /**
     * Résout le chemin DLC selon la priorité :
     *   1. Champ "DLC path" de la config Run (si renseigné)
     *   2. SDK OpenEdge configuré dans File → Project Structure → SDKs
     *   3. `dlcPath` dans openedge-project.json (OpenEdgeProjectService)
     *   4. Variable d'environnement $DLC
     *
     * Lève [ExecutionException] si aucune source ne fournit le chemin.
     */
    fun resolveDlc(): String {
        // Priority: Run config field → Project SDK → openedge-project.json → $DLC
        if (config.dlcPath.isNotBlank()) return config.dlcPath

        val fromSdk = resolveOpenEdgeSdkHome(config.project)
        if (!fromSdk.isNullOrBlank()) return fromSdk

        val fromJson = runCatching {
            config.project.service<OpenEdgeProjectService>().config.dlcPath
        }.getOrNull()
        if (!fromJson.isNullOrBlank()) return fromJson

        val fromEnv = System.getenv("DLC")
        if (!fromEnv.isNullOrBlank()) return fromEnv

        throw ExecutionException(
            "DLC path not found.\n\n" +
            "Set it in one of these places (in order of priority):\n" +
            "  1. Run Configuration → DLC path field\n" +
            "  2. File → Project Structure → SDKs → Add OpenEdge ABL SDK\n" +
            "  3. openedge-project.json → \"dlcPath\": \"C:/Progress/OpenEdge\"\n" +
            "  4. Environment variable \$DLC"
        )
    }

    /**
     * Construit la ligne de commande.
     * @param debugPort  si > 0, ajoute -debugport PORT pour le mode Launch+Debug.
     * @param forDebug   si true, supprime le flag -b (batch incompatible avec le debugger
     *                   sur certaines versions OE Windows — prowin.exe doit démarrer normalement).
     */
    fun buildCommandLine(debugPort: Int = 0, forDebug: Boolean = false): GeneralCommandLine {
        val dlc = resolveDlc()
        val isWindows = System.getProperty("os.name").lowercase().contains("win")

        // Mode debug : _progres.exe (client caractère) est requis — prowin.exe (client GUI)
        // ne reconnaît pas -debugport et le parse caractère par caractère (-d -e -b -u -g -p -o …),
        // ce qui déclenche l'erreur (1403) « pas précisé de valeur pour l'option -o ».
        // Mode run normal : prowin.exe en priorité (splash / GUI mode), _progres.exe en fallback.
        val executable = if (isWindows) {
            val candidates = if (forDebug || debugPort > 0)
                listOf("bin/_progres.exe", "bin/prowin.exe", "bin/prowin32.exe")
            else
                listOf("bin/prowin.exe", "bin/_progres.exe", "bin/prowin32.exe")
            candidates.map { File(dlc, it) }.firstOrNull { it.exists() }?.absolutePath
                ?: File(dlc, candidates.first()).absolutePath  // message d'erreur OS explicite
        } else {
            File(dlc, "bin/_progres").absolutePath
        }

        // Normaliser le chemin du fichier programme (forward slashes → séparateur natif)
        val programPath = java.io.File(config.programFile).path
        val args = buildArgList(executable, programPath, config.batchMode, forDebug, debugPort, config.programParam)
        val workDir = config.workingDirectory.ifBlank { config.project.basePath ?: "." }
        return GeneralCommandLine(args).withWorkDirectory(workDir)
    }

    override fun startProcess(): OSProcessHandler {
        val handler = ProcessHandlerFactory.getInstance()
            .createColoredProcessHandler(buildCommandLine())
        ProcessTerminatedListener.attach(handler)
        return handler
    }

    companion object {
        /**
         * Construit la liste d'arguments OE — fonction pure, testable sans IntelliJ.
         *
         * Règles :
         *  - `-b` supprimé en mode debug (incompatible avec `-debugReady` sur certaines versions OE Windows)
         *  - `-debugReady PORT` ajouté si debugPort > 0
         *  - `-param` ajouté si programParam non vide
         */
        /**
         * Construit la liste d'arguments OE — fonction pure, testable sans IntelliJ.
         *
         * Règles :
         *  - `-b` présent si batchMode=true, quel que soit le mode (run ou debug).
         *    Le proxy PDSOE↔OE confirme : `_progres.exe -b -p prog.p -debugReady PORT`.
         *    Sans `-b`, `_progres.exe` essaie d'ouvrir un terminal interactif et termine
         *    immédiatement si aucun n'est disponible (cas d'IntelliJ).
         *  - `-debugReady PORT` ajouté si debugPort > 0
         *  - `-param` ajouté si programParam non vide
         */
        internal fun buildArgList(
            executable: String,
            programFile: String,
            batchMode: Boolean,
            forDebug: Boolean,
            debugPort: Int,
            programParam: String = ""
        ): List<String> {
            val args = mutableListOf(executable, "-p", programFile)
            if (batchMode) args.add(1, "-b")   // requis pour headless, y compris en debug
            if (debugPort > 0) args += listOf("-debugReady", debugPort.toString())
            if (programParam.isNotBlank()) args += listOf("-param", programParam)
            return args
        }
    }
}

// ─── Éditeur de configuration (UI) ───────────────────────────────────────────

class AblRunConfigurationEditor : SettingsEditor<AblRunConfiguration>() {

    private val programFileField = TextFieldWithBrowseButton().apply {
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
    private val debugPortField     = JBTextField()

    override fun createEditor(): JComponent = panel {
        group("Program") {
            row("Program file (.p):") { cell(programFileField).resizableColumn() }
            row("Parameters:")        { cell(programParamField).resizableColumn() }
            row("Working directory:") { cell(workingDirField).resizableColumn() }
            row("DLC path:") {
                cell(dlcPathField).resizableColumn()
                comment("Leave empty to use \$DLC environment variable")
            }
            row("") { cell(batchModeCheckbox) }
        }
        group("Debug (optional)") {
            row("Debug port:") {
                cell(debugPortField)
                comment(
                    "Port for -debugport (e.g. 3075). " +
                    "When set, the <b>Debug</b> button launches OE with -debugport and auto-attaches. " +
                    "Leave 0 or empty for normal run (no debugger)."
                )
            }
        }
    }

    override fun resetEditorFrom(config: AblRunConfiguration) {
        programFileField.text        = config.programFile
        programParamField.text       = config.programParam
        dlcPathField.text            = config.dlcPath
        workingDirField.text         = config.workingDirectory
        batchModeCheckbox.isSelected = config.batchMode
        debugPortField.text          = if (config.debugPort > 0) config.debugPort.toString() else ""
    }

    override fun applyEditorTo(config: AblRunConfiguration) {
        config.programFile       = programFileField.text.trim()
        config.programParam      = programParamField.text.trim()
        config.dlcPath           = dlcPathField.text.trim()
        config.workingDirectory  = workingDirField.text.trim()
        config.batchMode         = batchModeCheckbox.isSelected
        config.debugPort         = debugPortField.text.trim().toIntOrNull() ?: 0
    }
}
