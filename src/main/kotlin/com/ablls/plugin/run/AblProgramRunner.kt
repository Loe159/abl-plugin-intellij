package com.ablls.plugin.run

import com.ablls.plugin.debug.AblDebugConnection
import com.ablls.plugin.debug.AblDebugProcess
import com.ablls.plugin.project.OpenEdgeProjectService
import com.intellij.execution.ExecutionException
import com.intellij.execution.configurations.GeneralCommandLine
import com.intellij.execution.configurations.RunProfile
import com.intellij.execution.configurations.RunProfileState
import com.intellij.execution.configurations.RunnerSettings
import com.intellij.execution.executors.DefaultDebugExecutor
import com.intellij.execution.process.ProcessAdapter
import com.intellij.execution.process.ProcessEvent
import com.intellij.execution.process.ProcessHandlerFactory
import com.intellij.execution.process.ProcessTerminatedListener
import com.intellij.execution.runners.ExecutionEnvironment
import com.intellij.execution.runners.GenericProgramRunner
import com.intellij.execution.ui.RunContentDescriptor
import com.intellij.openapi.application.PathManager
import com.intellij.openapi.components.service
import com.intellij.openapi.diagnostic.thisLogger
import com.intellij.openapi.util.Key
import com.intellij.xdebugger.XDebugProcess
import com.intellij.xdebugger.XDebugProcessStarter
import com.intellij.xdebugger.XDebugSession
import com.intellij.xdebugger.XDebuggerManager
import java.io.File
import java.net.ServerSocket

/**
 * Runner Debug pour les configurations "ABL Program".
 *
 * Orchestration (suit le flux de vscode-abl) :
 *
 *   1. Allouer un port libre (sauf si l'utilisateur a fixé `debugPort` > 0).
 *   2. Extraire `oe-debug-bootstrap.p` dans un fichier temporaire — c'est le programme
 *      réellement passé à OE via `-p`. Le bootstrap fait `READKEY` pour attendre
 *      qu'IntelliJ ait fini son handshake avant de lancer le programme utilisateur.
 *   3. Spawn `_progres.exe -b -p bootstrap.p -debugReady PORT` avec les env :
 *        ABL_DEBUG_PROGRAM  = chemin absolu du fichier ABL à debugger
 *        ABL_DEBUG_PROPATH  = PROPATH déduit d'openedge-project.json (optionnel)
 *        ENABLE_OPENEDGE_DEBUGGER = 1
 *   4. Démarrer la session XDebug. IntelliJ enregistre les breakpoints existants.
 *   5. [AblDebugConnection.connectWithRetry] — IntelliJ ouvre 2 sockets vers le port.
 *      Retry pendant 15s pour laisser OE finir de démarrer.
 *   6. [AblDebugProcess.sessionInitialized] envoie `SETPROP IDE 1`, la liste des
 *      breakpoints, puis écrit `\r` sur stdin → libère le READKEY du bootstrap.
 *   7. Le programme utilisateur démarre, OE envoie MSG_ENTER aux breakpoints.
 */
class AblProgramRunner : GenericProgramRunner<RunnerSettings>() {
    private val log = thisLogger()

    override fun getRunnerId() = "AblProgramRunner"

    override fun canRun(
        executorId: String,
        profile: RunProfile,
    ): Boolean = profile is AblRunConfiguration && executorId == DefaultDebugExecutor.EXECUTOR_ID

    @Throws(ExecutionException::class)
    override fun doExecute(
        state: RunProfileState,
        environment: ExecutionEnvironment,
    ): RunContentDescriptor? {
        val config = environment.runProfile as AblRunConfiguration
        val runState = state as AblRunState

        return XDebuggerManager.getInstance(environment.project)
            .startSession(
                environment,
                object : XDebugProcessStarter() {
                    override fun start(session: XDebugSession): XDebugProcess = launch(session, runState, config)
                },
            )
            .runContentDescriptor
    }

    private fun launch(
        session: XDebugSession,
        runState: AblRunState,
        config: AblRunConfiguration,
    ): XDebugProcess {
        // 1. Port debug (fixe si configuré, sinon dynamique).
        val port = config.debugPort.takeIf { it > 0 } ?: findFreePort()

        // 2. Bootstrap .p extrait dans un tempfile.
        val bootstrap = extractBootstrap()

        // 3. PROPATH éventuel pour le programme utilisateur.
        val propath =
            runCatching {
                session.project.service<OpenEdgeProjectService>().config.propath.joinToString(",")
            }.getOrDefault("")

        // 4. Construction de la ligne de commande _progres.exe.
        val cmdLine = buildBootstrapCommandLine(runState, config, bootstrap, port, propath)

        // 5. Spawn OE.
        val processHandler =
            ProcessHandlerFactory.getInstance()
                .createColoredProcessHandler(cmdLine)
        ProcessTerminatedListener.attach(processHandler)

        val oeOutput = StringBuilder()
        processHandler.addProcessListener(
            object : ProcessAdapter() {
                override fun onTextAvailable(
                    event: ProcessEvent,
                    outputType: Key<*>,
                ) {
                    oeOutput.append(event.text)
                }
            },
        )
        processHandler.startNotify()
        log.info("ABL debug: spawned OE, awaiting connection on port $port")

        // 6. IntelliJ se connecte à OE (avec retry — OE met ~500ms-2s à ouvrir le socket).
        val conn = AblDebugConnection(port = port)
        val connected = conn.connectWithRetry(timeoutMs = 15_000, retryIntervalMs = 100)
        if (!connected) {
            if (!processHandler.isProcessTerminated) processHandler.destroyProcess()
            val exit = processHandler.exitCode ?: -1
            val first = oeOutput.lines().firstOrNull { it.isNotBlank() } ?: "(no output)"
            throw ExecutionException(
                "Could not connect to OpenEdge debugger on port $port (exit=$exit).\n  $first\n\n" +
                    "Vérifie que _progres.exe accepte -debugReady (variable d'environnement " +
                    "ENABLE_OPENEDGE_DEBUGGER=1 requise pour certaines versions OE).",
            )
        }
        log.info("ABL debug: connected to OE on port $port")

        // 7. Fermer la connexion proprement quand le process meurt.
        processHandler.addProcessListener(
            object : ProcessAdapter() {
                override fun processTerminated(event: ProcessEvent) {
                    conn.close()
                }
            },
        )

        return AblDebugProcess(session, conn, processHandler, bootstrap.absolutePath)
    }

    /**
     * Construit la commande pour spawn OE avec le bootstrap. Le programme utilisateur
     * passe par la variable d'environnement `ABL_DEBUG_PROGRAM`, lue par le bootstrap.
     */
    private fun buildBootstrapCommandLine(
        runState: AblRunState,
        config: AblRunConfiguration,
        bootstrap: File,
        port: Int,
        propath: String,
    ): GeneralCommandLine {
        // _progres.exe (client caractère) est le seul à supporter -debugReady proprement.
        val dlc = runState.resolveDlc()
        val executable = pickClientExecutable(dlc)

        val args = mutableListOf(executable, "-p", bootstrap.absolutePath, "-debugReady", port.toString())
        if (config.batchMode) args.add(1, "-b")
        if (config.programParam.isNotBlank()) args += listOf("-param", config.programParam)

        val workDir = config.workingDirectory.ifBlank { config.project.basePath ?: "." }

        return GeneralCommandLine(args)
            .withWorkDirectory(workDir)
            .withEnvironment("ENABLE_OPENEDGE_DEBUGGER", "1")
            .withEnvironment("ABL_DEBUG_PROGRAM", File(config.programFile).absolutePath)
            .withEnvironment("ABL_DEBUG_PROPATH", propath)
            .withEnvironment("DLC", dlc)
    }

    /**
     * Sélectionne le binaire client OE — `_progres.exe` en priorité car c'est le seul
     * à interpréter `-debugReady` correctement (prowin.exe le parse caractère par caractère).
     */
    private fun pickClientExecutable(dlc: String): String {
        val isWindows = System.getProperty("os.name").lowercase().contains("win")
        val candidates =
            if (isWindows) {
                listOf("bin/_progres.exe", "bin/prowin.exe", "bin/prowin32.exe")
            } else {
                listOf("bin/_progres", "bin/mpro")
            }
        return candidates.map { File(dlc, it) }.firstOrNull { it.exists() }?.absolutePath
            ?: File(dlc, candidates.first()).absolutePath
    }

    /**
     * Extrait `oe-debug-bootstrap.p` du JAR plugin vers un tempfile. OE ne peut pas lire
     * dans un JAR — on doit matérialiser un fichier sur disque.
     */
    private fun extractBootstrap(): File {
        val dir = File(PathManager.getTempPath(), "abl-debug")
        dir.mkdirs()
        val target = File(dir, "oe-debug-bootstrap.p")
        val resource =
            AblProgramRunner::class.java.classLoader
                .getResourceAsStream("abl/oe-debug-bootstrap.p")
                ?: throw ExecutionException("Bootstrap resource abl/oe-debug-bootstrap.p missing from plugin JAR")
        target.outputStream().use { out -> resource.use { it.copyTo(out) } }
        return target
    }

    companion object {
        /**
         * Retourne un port libre dans la plage éphémère (>= 1024).
         * Sur Windows, ServerSocket(0) peut renvoyer des ports privilégiés rejetés par
         * `-debugReady` ; on retente jusqu'à obtenir un port >= 1024.
         */
        fun findFreePort(): Int {
            repeat(20) {
                try {
                    ServerSocket(0).use { s ->
                        if (s.localPort >= 1024) return s.localPort
                    }
                } catch (_: Exception) {
                    // retry
                }
            }
            return 3075 // fallback raisonnable
        }
    }
}
