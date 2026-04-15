package com.ablls.plugin.debug

import com.intellij.execution.process.ProcessHandler
import com.intellij.openapi.vfs.LocalFileSystem
import com.intellij.xdebugger.XDebugProcess
import com.intellij.xdebugger.XDebugSession
import com.intellij.xdebugger.XDebuggerUtil
import com.intellij.xdebugger.breakpoints.XBreakpointHandler
import com.intellij.xdebugger.evaluation.XDebuggerEditorsProvider
import com.intellij.xdebugger.evaluation.XDebuggerEvaluator
import com.intellij.xdebugger.frame.XSuspendContext
import com.intellij.xdebugger.frame.XValue
import com.intellij.xdebugger.frame.XValueNode
import com.intellij.xdebugger.frame.XValuePlace

/**
 * Processus de debug ABL.
 *
 * Deux modes selon [processHandler] :
 *  - null (AblRemoteProcessHandler fourni par le runner) → Remote Attach
 *  - OSProcessHandler → Launch & Debug (OE lancé par nous)
 *
 * Dans les deux cas [processHandler] doit être non-null pour que la session
 * XDebug reste vivante (IntelliJ ferme la session si le handler est null).
 */
/**
 * @param sendGo  true (mode Launch+Debug) : envoyer GO dans sessionInitialized(),
 *                après que IntelliJ ait enregistré les breakpoints existants.
 *                false (Remote Attach) : OE est déjà en cours d'exécution.
 */
class AblDebugProcess(
    session: XDebugSession,
    private val conn: AblDebugConnection,
    private val processHandler: ProcessHandler,
    private val sendGo: Boolean = true
) : XDebugProcess(session) {

    init {
        conn.startListening(
            onSuspend = { file, line ->
                val vFile = resolveFile(file)
                val position = vFile?.let {
                    XDebuggerUtil.getInstance().createPosition(it, line - 1)
                }
                session.positionReached(AblSuspendContext(position))
            }
        )
    }

    /**
     * Appelé par IntelliJ après que la session est initialisée ET que les breakpoints
     * existants ont été enregistrés via AblBreakpointHandler.
     * C'est le moment sûr pour envoyer GO : OE démarre l'exécution, s'arrêtera
     * sur le premier breakpoint rencontré.
     */
    override fun sessionInitialized() {
        if (sendGo) conn.go()
    }

    /** Retourne le process handler pour que la session XDebug reste active. */
    override fun doGetProcessHandler(): ProcessHandler = processHandler

    override fun getEditorsProvider(): XDebuggerEditorsProvider = AblDebugEditorsProvider()

    override fun getBreakpointHandlers(): Array<XBreakpointHandler<*>> =
        arrayOf(AblBreakpointHandler(conn))

    override fun getEvaluator(): XDebuggerEvaluator = AblDebugEvaluator(conn)

    // ── Contrôle de l'exécution ───────────────────────────────────────────────

    override fun resume(context: XSuspendContext?)        { conn.cont() }
    override fun startStepOver(context: XSuspendContext?) { conn.stepOver() }
    override fun startStepInto(context: XSuspendContext?) { conn.stepInto() }
    override fun startStepOut(context: XSuspendContext?)  { conn.stepReturn() }

    override fun stop() {
        conn.quit()
        conn.close()
        // Si c'est un handler factice (remote attach), on le termine manuellement
        if (!processHandler.isProcessTerminated) {
            processHandler.destroyProcess()
        }
    }

    // ── Résolution du chemin de fichier OE → VirtualFile ─────────────────────

    private fun resolveFile(file: String) =
        LocalFileSystem.getInstance().findFileByPath(file)
            ?: session.project.basePath?.let {
                LocalFileSystem.getInstance().findFileByPath("$it/$file")
                    ?: LocalFileSystem.getInstance().findFileByPath("$it/${file.replace('\\', '/')}")
            }
}

// ─── Évaluateur d'expression ─────────────────────────────────────────────────

/**
 * Implémente "Evaluate Expression" (Alt+F8).
 * Envoie EVAL <expr> à OE, attend la réponse VALUE <expr>=<val>:<type>.
 */
class AblDebugEvaluator(private val conn: AblDebugConnection) : XDebuggerEvaluator() {

    override fun evaluate(
        expression: String,
        callback: XEvaluationCallback,
        expressionPosition: com.intellij.xdebugger.XSourcePosition?
    ) {
        conn.eval(expression) { value, type ->
            callback.evaluated(object : XValue() {
                override fun computePresentation(node: XValueNode, place: XValuePlace) {
                    node.setPresentation(null, type, value, false)
                }
            })
        }
    }
}
