package com.ablls.plugin.debug

import com.ablls.plugin.language.AblFileType
import com.intellij.openapi.fileTypes.FileType
import com.intellij.openapi.project.Project
import com.intellij.openapi.vfs.VirtualFile
import com.intellij.xdebugger.breakpoints.XBreakpointHandler
import com.intellij.xdebugger.breakpoints.XBreakpointProperties
import com.intellij.xdebugger.breakpoints.XBreakpointType
import com.intellij.xdebugger.breakpoints.XLineBreakpoint
import com.intellij.xdebugger.breakpoints.XLineBreakpointType
import com.intellij.xdebugger.evaluation.XDebuggerEditorsProvider
import com.intellij.xdebugger.frame.XCompositeNode
import com.intellij.xdebugger.frame.XNamedValue
import com.intellij.xdebugger.frame.XStackFrame
import com.intellij.xdebugger.frame.XSuspendContext
import com.intellij.xdebugger.frame.XValueNode
import com.intellij.xdebugger.frame.XValuePlace

// ─── Type de point d'arrêt ────────────────────────────────────────────────────

class AblLineBreakpointType
    : XLineBreakpointType<XBreakpointProperties<*>>("abl-line", "ABL Line Breakpoints") {

    override fun canPutAt(file: VirtualFile, line: Int, project: Project): Boolean =
        file.extension?.lowercase() in listOf("p", "cls", "w", "i")

    override fun createBreakpointProperties(file: VirtualFile, line: Int): XBreakpointProperties<*>? = null
}

// ─── Handler de points d'arrêt ────────────────────────────────────────────────

@Suppress("UNCHECKED_CAST")
class AblBreakpointHandler(private val conn: AblDebugConnection)
    : XBreakpointHandler<XLineBreakpoint<*>>(
        AblLineBreakpointType::class.java as Class<out XBreakpointType<XLineBreakpoint<*>, *>>
    ) {

    override fun registerBreakpoint(breakpoint: XLineBreakpoint<*>) {
        conn.setBreakpoint(normalizeFilePath(breakpoint.fileUrl), breakpoint.line + 1)
    }

    override fun unregisterBreakpoint(breakpoint: XLineBreakpoint<*>, temporary: Boolean) {
        conn.clearBreakpoint(normalizeFilePath(breakpoint.fileUrl), breakpoint.line + 1)
    }

    /**
     * Convertit une URL VFS (file:///C:/path/to/file.p) en chemin natif OE.
     * Sur Windows, OE attend un backslash ou slash selon la version.
     */
    private fun normalizeFilePath(fileUrl: String): String =
        fileUrl
            .removePrefix("file:///")
            .removePrefix("file://")
            .removePrefix("file:/")
            // Sur Windows, OE accepte les deux séparateurs ; on garde le slash
            .replace('\\', '/')
}

// ─── Fournisseur d'éditeur (nécessaire pour XDebugProcess) ───────────────────

class AblDebugEditorsProvider : XDebuggerEditorsProvider() {
    override fun getFileType(): FileType = AblFileType.INSTANCE
}

// ─── Stack frame ──────────────────────────────────────────────────────────────

class AblStackFrame(
    private val sourcePosition: com.intellij.xdebugger.XSourcePosition?
) : XStackFrame() {
    override fun getSourcePosition() = sourcePosition
    override fun computeChildren(node: XCompositeNode) { node.setAlreadySorted(true) }
}

// ─── Valeur de variable ───────────────────────────────────────────────────────

class AblValue(
    name: String,
    private val value: String,
    private val type: String
) : XNamedValue(name) {
    override fun computePresentation(node: XValueNode, place: XValuePlace) {
        node.setPresentation(null, type, value, false)
    }
}

// ─── Contexte de suspension ───────────────────────────────────────────────────

class AblSuspendContext(
    private val position: com.intellij.xdebugger.XSourcePosition?
) : XSuspendContext() {

    override fun getActiveExecutionStack(): com.intellij.xdebugger.frame.XExecutionStack? =
        object : com.intellij.xdebugger.frame.XExecutionStack("ABL") {
            override fun getTopFrame() = AblStackFrame(position)
            override fun computeStackFrames(firstFrameIndex: Int, container: XStackFrameContainer) {
                container.addStackFrames(listOf(AblStackFrame(position)), true)
            }
        }
}
