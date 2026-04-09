package com.ablls.plugin.debug

import com.intellij.openapi.vfs.LocalFileSystem
import com.intellij.xdebugger.XDebugProcess
import com.intellij.xdebugger.XDebugSession
import com.intellij.xdebugger.XSourcePosition
import com.intellij.xdebugger.breakpoints.XBreakpointHandler
import com.intellij.xdebugger.evaluation.XDebuggerEditorsProvider
import com.intellij.xdebugger.frame.XSuspendContext

/**
 * Processus de debug ABL — pilote la session XDebug IntelliJ via la connexion TCP.
 */
class AblDebugProcess(
    session: XDebugSession,
    private val conn: AblDebugConnection
) : XDebugProcess(session) {

    init {
        conn.startListening { file, line ->
            val vFile = LocalFileSystem.getInstance().findFileByPath(file)
                ?: session.project.basePath?.let {
                    LocalFileSystem.getInstance().findFileByPath("$it/$file")
                }
            val position: XSourcePosition? = vFile?.let {
                com.intellij.xdebugger.XDebuggerUtil.getInstance().createPosition(it, line - 1)
            }
            session.positionReached(AblSuspendContext(position))
        }
    }

    override fun getEditorsProvider(): XDebuggerEditorsProvider = AblDebugEditorsProvider()

    override fun getBreakpointHandlers(): Array<XBreakpointHandler<*>> =
        arrayOf(AblBreakpointHandler(conn))

    override fun resume(context: XSuspendContext?)   { conn.send("RESUME") }
    override fun startStepOver(context: XSuspendContext?) { conn.send("STEP_OVER") }
    override fun startStepInto(context: XSuspendContext?) { conn.send("STEP_INTO") }
    override fun startStepOut(context: XSuspendContext?)  { conn.send("STEP_OUT") }
    override fun stop()  { conn.close() }
}
