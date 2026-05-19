package com.ablls.plugin.debug

import com.intellij.execution.filters.TextConsoleBuilderFactory
import com.intellij.execution.process.ProcessHandler
import com.intellij.execution.ui.ConsoleView
import com.intellij.execution.ui.ExecutionConsole
import com.intellij.openapi.application.ApplicationManager
import com.intellij.xdebugger.XDebugProcess
import com.intellij.xdebugger.XDebugSession
import com.intellij.xdebugger.breakpoints.XBreakpointHandler
import com.intellij.xdebugger.evaluation.XDebuggerEditorsProvider
import com.intellij.xdebugger.evaluation.XDebuggerEvaluator
import com.intellij.xdebugger.frame.XSuspendContext
import com.intellij.xdebugger.frame.XValue
import com.intellij.xdebugger.frame.XValueNode
import com.intellij.xdebugger.frame.XValuePlace

/**
 * Pont entre la session XDebug d'IntelliJ et [AblDebugConnection].
 *
 * Cycle de vie :
 *   1. Construction : on enregistre les callbacks (onStopped, onExit) sur la connexion.
 *   2. [sessionInitialized] : IntelliJ a enregistré les breakpoints existants.
 *      → on appelle [AblDebugConnection.startDebugging] pour envoyer SETPROP + BPs,
 *      puis [releaseBootstrap] pour libérer le READKEY du bootstrap.p.
 *   3. À chaque MSG_ENTER : on récupère la pile (show stack-ide) et on notifie la session.
 *   4. Commandes resume/step transmises directement à OE.
 *   5. [stop] : on ferme la connexion et le process.
 */
class AblDebugProcess(
    session: XDebugSession,
    private val conn: AblDebugConnection,
    private val processHandler: ProcessHandler,
    /**
     * Chemin absolu de `oe-debug-bootstrap.p`. Sert à filtrer cette frame de la
     * pile présentée à l'utilisateur — c'est un détail d'implémentation du runner
     * qui n'a aucune valeur lors d'une session debug.
     */
    private val bootstrapPath: String? = null,
) : XDebugProcess(session) {

    private val editors    = AblDebugEditorsProvider()
    private val breakpoint = AblBreakpointHandler(conn)
    private val evaluator  = AblDebugEvaluator(conn)

    init {
        conn.onStopped = {
            ApplicationManager.getApplication().executeOnPooledThread {
                val raw = conn.showStack()
                val filtered = raw.filterNot { isBootstrapFrame(it) }
                // Si filtrer le bootstrap vide la pile (cas où OE est encore dans
                // le bootstrap, ex. arrêt sur READKEY), on garde la pile brute.
                val frames = (if (filtered.isNotEmpty()) filtered else raw)
                    .map { AblStackFrame(it, conn, session.project) }
                val context = AblSuspendContext(AblExecutionStack(frames))
                session.positionReached(context)
            }
        }
        conn.onExit = {
            if (!processHandler.isProcessTerminated) processHandler.destroyProcess()
        }
    }

    /** True si la frame correspond au fichier bootstrap interne du plugin. */
    private fun isBootstrapFrame(frame: OeStackFrame): Boolean {
        val boot = bootstrapPath ?: return false
        val file = frame.file ?: return false
        return file.replace('\\', '/').equals(boot.replace('\\', '/'), ignoreCase = true)
    }

    /**
     * Appelée après que IntelliJ a propagé les breakpoints existants au handler.
     *
     * Séquence (suit vscode-abl/ablDebug.ts:launchRequest) :
     *   1. SETPROP IDE 1 + liste des BPs.
     *   2. Écrire `\r` sur stdin pour libérer le READKEY du bootstrap.
     *   3. Envoyer `cont` — en mode IDE, OE attend une commande de démarrage explicite.
     *      Sans `cont`, OE se figerait à l'entrée du programme utilisateur et l'utilisateur
     *      devrait cliquer Resume manuellement avant d'atteindre le premier breakpoint.
     */
    override fun sessionInitialized() {
        conn.startDebugging()
        releaseBootstrap()
        conn.cont()
    }

    /** Écrit un CR sur stdin du process OE pour faire avancer READKEY dans bootstrap.p. */
    private fun releaseBootstrap() {
        val stream = processHandler.processInput ?: return
        try {
            stream.write(byteArrayOf(0x0D))
            stream.flush()
        } catch (_: Exception) {
            // process déjà terminé — non-fatal
        }
    }

    override fun doGetProcessHandler(): ProcessHandler = processHandler
    override fun getEditorsProvider(): XDebuggerEditorsProvider = editors
    override fun getBreakpointHandlers(): Array<XBreakpointHandler<*>> = arrayOf(breakpoint)
    override fun getEvaluator(): XDebuggerEvaluator = evaluator

    /**
     * Console "Debug Console" — capture stdout/stderr du process OE.
     * Sans override, IntelliJ ne crée pas de console attachée pour XDebugProcess
     * et les MESSAGEs ABL n'apparaissent nulle part.
     */
    override fun createConsole(): ExecutionConsole {
        val console: ConsoleView = TextConsoleBuilderFactory.getInstance()
            .createBuilder(session.project)
            .console
        console.attachToProcess(processHandler)
        return console
    }

    // ── Contrôle d'exécution ──────────────────────────────────────────────────

    override fun resume(context: XSuspendContext?)        = conn.cont()
    override fun startStepOver(context: XSuspendContext?) = conn.stepOver()
    override fun startStepInto(context: XSuspendContext?) = conn.stepInto()
    override fun startStepOut(context: XSuspendContext?)  = conn.stepReturn()
    override fun startPausing()                           = conn.interrupt()

    override fun stop() {
        conn.close()
        if (!processHandler.isProcessTerminated) processHandler.destroyProcess()
    }
}

// ─── Évaluateur d'expression (Alt+F8 / hover) ────────────────────────────────

class AblDebugEvaluator(private val conn: AblDebugConnection) : XDebuggerEvaluator() {

    override fun evaluate(
        expression: String,
        callback: XEvaluationCallback,
        expressionPosition: com.intellij.xdebugger.XSourcePosition?
    ) {
        // OE ne fournit pas d'API d'évaluation directe — on transmet l'expression brute
        // (ex. "ASSIGN x = 42"). La valeur sera reflétée dans le prochain MSG_VARIABLES.
        conn.sendRaw(expression)
        callback.evaluated(object : XValue() {
            override fun computePresentation(node: XValueNode, place: XValuePlace) {
                node.setPresentation(null, "", "(sent to OE)", false)
            }
        })
    }
}
