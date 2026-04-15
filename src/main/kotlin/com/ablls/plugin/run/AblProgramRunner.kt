package com.ablls.plugin.run

import com.ablls.plugin.debug.AblDebugConfiguration
import com.ablls.plugin.debug.AblDebugConnection
import com.ablls.plugin.debug.AblDebugProcess
import com.intellij.execution.ExecutionException
import com.intellij.execution.configurations.RunProfile
import com.intellij.execution.configurations.RunProfileState
import com.intellij.execution.configurations.RunnerSettings
import com.intellij.execution.executors.DefaultDebugExecutor
import com.intellij.execution.executors.DefaultRunExecutor
import com.intellij.execution.process.ProcessAdapter
import com.intellij.execution.process.ProcessEvent
import com.intellij.execution.process.ProcessHandler
import com.intellij.execution.process.ProcessHandlerFactory
import com.intellij.execution.process.ProcessTerminatedListener
import com.intellij.execution.runners.ExecutionEnvironment
import com.intellij.execution.runners.GenericProgramRunner
import com.intellij.execution.ui.RunContentDescriptor
import com.intellij.xdebugger.XDebugProcess
import com.intellij.xdebugger.XDebugProcessStarter
import com.intellij.xdebugger.XDebugSession
import com.intellij.xdebugger.XDebuggerManager
import java.io.OutputStream

/**
 * Runner ABL pour le mode Debug.
 *
 * Architecture (OE 12.x) avec -debugReady PORT : OE est le SERVEUR TCP, IntelliJ est le CLIENT.
 *   1. OE démarre avec -debugReady PORT → ouvre un socket d'écoute sur PORT
 *   2. IntelliJ se connecte à localhost:PORT (avec retry, OE peut mettre ~100-500ms à ouvrir le port)
 *   3. IntelliJ enregistre les breakpoints (BREAK file line)
 *   4. IntelliJ envoie GO via sessionInitialized() → OE démarre l'exécution
 *   5. OE envoie STOPPED <file> <line> à chaque breakpoint atteint
 */
class AblProgramRunner : GenericProgramRunner<RunnerSettings>() {

    override fun getRunnerId() = "AblProgramRunner"

    override fun canRun(executorId: String, profile: RunProfile): Boolean = when {
        profile is AblRunConfiguration   && executorId == DefaultDebugExecutor.EXECUTOR_ID -> true
        profile is AblDebugConfiguration && executorId == DefaultDebugExecutor.EXECUTOR_ID -> true
        profile is AblDebugConfiguration && executorId == DefaultRunExecutor.EXECUTOR_ID   -> true
        else -> false
    }

    @Throws(ExecutionException::class)
    override fun doExecute(state: RunProfileState, env: ExecutionEnvironment): RunContentDescriptor? =
        when (val profile = env.runProfile) {
            is AblDebugConfiguration -> when (env.executor.id) {
                DefaultRunExecutor.EXECUTOR_ID ->
                    throw ExecutionException(
                        "\"ABL Remote Debug\" requires the Debug button.\n\n" +
                        "Start OpenEdge manually with:\n" +
                        "  _progres.exe -b -p yourprog.p -debugReady ${profile.port}\n\n" +
                        "Then click Debug to attach."
                    )
                else -> attachRemote(profile, env)
            }
            is AblRunConfiguration -> launchAndDebug(state as AblRunState, profile, env)
            else -> null
        }

    // ── Mode 1 : OE lancé automatiquement par IntelliJ ───────────────────────

    private fun launchAndDebug(
        state: AblRunState,
        config: AblRunConfiguration,
        env: ExecutionEnvironment
    ): RunContentDescriptor? {
        val port = config.debugPort.takeIf { it > 0 } ?: 3075

        return XDebuggerManager.getInstance(env.project)
            .startSession(env, object : XDebugProcessStarter() {
                override fun start(session: XDebugSession): XDebugProcess {
                    // 1. Lancer OE avec -debugReady (OE va ouvrir le port d'écoute)
                    val cmdLine = state.buildCommandLine(debugPort = port, forDebug = true)
                    val processHandler = ProcessHandlerFactory.getInstance()
                        .createColoredProcessHandler(cmdLine)
                    ProcessTerminatedListener.attach(processHandler)
                    processHandler.startNotify()

                    // 2. Se connecter à OE (IntelliJ = client, OE = serveur)
                    //    OE peut mettre quelques centaines de ms à ouvrir le port.
                    val conn = AblDebugConnection(port = port)
                    val connected = connectWithHealthCheck(conn, processHandler, timeoutMs = 15_000)

                    if (!connected) {
                        val crashed = processHandler.isProcessTerminated
                        if (!crashed) processHandler.destroyProcess()
                        throw ExecutionException(
                            if (crashed)
                                "OpenEdge terminated before the debug port was ready.\n\n" +
                                "Possible causes:\n" +
                                "  • The .p file does not compile (run it without debug first)\n" +
                                "  • Incorrect DLC path or program path\n\n" +
                                "Command used:\n  ${cmdLine.commandLineString}"
                            else
                                "Could not connect to OpenEdge debug port $port within 15 seconds.\n\n" +
                                "Command used:\n  ${cmdLine.commandLineString}"
                        )
                    }

                    // 3. Session établie — sessionInitialized() enverra GO après les breakpoints
                    val process = AblDebugProcess(session, conn, processHandler, sendGo = true)
                    processHandler.addProcessListener(object : ProcessAdapter() {
                        override fun processTerminated(event: ProcessEvent) { conn.close() }
                    })
                    return process
                }
            }).runContentDescriptor
    }

    // ── Mode 2 : Attach à un OE déjà démarré manuellement ────────────────────

    private fun attachRemote(config: AblDebugConfiguration, env: ExecutionEnvironment): RunContentDescriptor? {
        val conn = AblDebugConnection(host = config.host, port = config.port)

        val remoteHandler = AblRemoteProcessHandler()

        // Connexion en background — l'utilisateur doit démarrer OE avec -debugReady PORT
        Thread {
            val connected = conn.connectWithRetry(timeoutMs = 120_000)
            if (!connected) {
                remoteHandler.destroyProcess()
            }
            // Si connecté, sessionInitialized() (sendGo=false) prend le relais
        }.also { it.isDaemon = true }.start()

        val descriptor = XDebuggerManager.getInstance(env.project)
            .startSession(env, object : XDebugProcessStarter() {
                override fun start(session: XDebugSession): XDebugProcess =
                    AblDebugProcess(session, conn, remoteHandler, sendGo = false)
            }).runContentDescriptor

        remoteHandler.startNotify()
        return descriptor
    }

    // ── Connexion à OE avec health-check du process ───────────────────────────

    /**
     * Tente de se connecter à OE (qui écoute sur le port) tout en vérifiant
     * que le processus OE est encore vivant. Si OE plante au démarrage,
     * on le détecte immédiatement plutôt que d'attendre le timeout.
     */
    private fun connectWithHealthCheck(
        conn: AblDebugConnection,
        processHandler: ProcessHandler,
        timeoutMs: Long
    ): Boolean {
        val deadline = System.currentTimeMillis() + timeoutMs
        while (System.currentTimeMillis() < deadline) {
            if (processHandler.isProcessTerminated) return false
            try {
                conn.connect()
                return true
            } catch (_: java.io.IOException) {
                Thread.sleep(100)
            }
        }
        return false
    }
}

// ─── ProcessHandler factice pour Remote Attach ────────────────────────────────

class AblRemoteProcessHandler : ProcessHandler() {
    override fun destroyProcessImpl()  { notifyProcessTerminated(0) }
    override fun detachProcessImpl()   { notifyProcessTerminated(0) }
    override fun detachIsDefault()     = false
    override fun getProcessInput(): OutputStream? = null
}
