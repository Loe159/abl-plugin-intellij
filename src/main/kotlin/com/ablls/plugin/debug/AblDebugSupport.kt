package com.ablls.plugin.debug

import com.ablls.plugin.language.AblFileType
import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.fileTypes.FileType
import com.intellij.openapi.project.Project
import com.intellij.openapi.vfs.LocalFileSystem
import com.intellij.openapi.vfs.VirtualFile
import com.intellij.xdebugger.XDebuggerUtil
import com.intellij.xdebugger.XSourcePosition
import com.intellij.xdebugger.breakpoints.XBreakpointHandler
import com.intellij.xdebugger.breakpoints.XBreakpointProperties
import com.intellij.xdebugger.breakpoints.XBreakpointType
import com.intellij.xdebugger.breakpoints.XLineBreakpoint
import com.intellij.xdebugger.breakpoints.XLineBreakpointType
import com.intellij.xdebugger.evaluation.XDebuggerEditorsProvider
import com.intellij.xdebugger.frame.XCompositeNode
import com.intellij.xdebugger.frame.XExecutionStack
import com.intellij.xdebugger.frame.XNamedValue
import com.intellij.xdebugger.frame.XStackFrame
import com.intellij.xdebugger.frame.XSuspendContext
import com.intellij.xdebugger.frame.XValueChildrenList
import com.intellij.xdebugger.frame.XValueNode
import com.intellij.xdebugger.frame.XValuePlace

// ─── Type de breakpoint ───────────────────────────────────────────────────────

class AblLineBreakpointType :
    XLineBreakpointType<XBreakpointProperties<*>>("abl-line", "ABL Line Breakpoints") {
    override fun canPutAt(
        file: VirtualFile,
        line: Int,
        project: Project,
    ): Boolean = file.extension?.lowercase() in setOf("p", "cls", "w", "i")

    override fun createBreakpointProperties(
        file: VirtualFile,
        line: Int,
    ): XBreakpointProperties<*>? = null
}

// ─── Handler de breakpoints ───────────────────────────────────────────────────

@Suppress("UNCHECKED_CAST")
class AblBreakpointHandler(private val conn: AblDebugConnection) :
    XBreakpointHandler<XLineBreakpoint<*>>(
        AblLineBreakpointType::class.java as Class<out XBreakpointType<XLineBreakpoint<*>, *>>,
    ) {
    override fun registerBreakpoint(breakpoint: XLineBreakpoint<*>) {
        conn.setBreakpoint(normalize(breakpoint.fileUrl), breakpoint.line + 1)
    }

    override fun unregisterBreakpoint(
        breakpoint: XLineBreakpoint<*>,
        temporary: Boolean,
    ) {
        conn.clearBreakpoint(normalize(breakpoint.fileUrl), breakpoint.line + 1)
    }

    private fun normalize(fileUrl: String): String =
        fileUrl
            .removePrefix("file:///")
            .removePrefix("file://")
            .removePrefix("file:/")
            .replace('\\', '/')
}

// ─── Éditeur d'expression (Evaluate Expression — Alt+F8) ─────────────────────

class AblDebugEditorsProvider : XDebuggerEditorsProvider() {
    override fun getFileType(): FileType = AblFileType.INSTANCE
}

// ─── Valeur de variable ───────────────────────────────────────────────────────

class AblValue(
    private val variable: OeVariable,
    private val conn: AblDebugConnection? = null,
) : XNamedValue(variable.name) {
    override fun computePresentation(
        node: XValueNode,
        place: XValuePlace,
    ) {
        val isArray = variable.kind == OeVarKind.ARRAY
        val displayValue =
            when {
                isArray -> "${variable.type}[]"
                variable.value == "?" -> "?"
                variable.type == "CHARACTER" ||
                    variable.type == "LONGCHAR" -> "\"${variable.value}\""
                else -> variable.value
            }
        // hasChildren = true pour les arrays → ▶ cliquable dans le panneau Variables.
        node.setPresentation(null, variable.type, displayValue, isArray)
    }

    override fun computeChildren(node: XCompositeNode) {
        if (variable.kind != OeVarKind.ARRAY || conn == null) {
            super.computeChildren(node)
            return
        }
        // Récupération asynchrone — GET-ARRAY est bloquant côté connexion (5 s).
        ApplicationManager.getApplication().executeOnPooledThread {
            val values = conn.getArray(variable.name, variable.type)
            val list = XValueChildrenList()
            values.forEachIndexed { idx, value ->
                // ABL indexe à partir de 1.
                val element =
                    OeVariable(
                        name = "[${idx + 1}]",
                        type = variable.type,
                        value = value,
                        kind = OeVarKind.VARIABLE,
                    )
                list.add(AblValue(element, conn))
            }
            node.addChildren(list, true)
        }
    }
}

// ─── Stack frame ──────────────────────────────────────────────────────────────

class AblStackFrame(
    private val frame: OeStackFrame,
    private val conn: AblDebugConnection,
    private val project: Project,
) : XStackFrame() {
    private val sourcePos: XSourcePosition? by lazy {
        resolveFile(frame.file, project)?.let { vf ->
            XDebuggerUtil.getInstance().createPosition(vf, frame.line - 1)
        }
    }

    override fun getSourcePosition(): XSourcePosition? = sourcePos

    override fun computeChildren(node: XCompositeNode) {
        // Scope unique "Local" — parameters + variables (suivant vscode-abl).
        val list = XValueChildrenList()

        for (p in conn.listParameters()) list.add(AblValue(p, conn))
        for (v in conn.listVariables()) list.add(AblValue(v, conn))

        node.addChildren(list, true)
    }

    override fun toString(): String =
        if (frame.file != null) {
            "${frame.function} — ${frame.file}:${frame.line}"
        } else {
            "${frame.function}:${frame.line}"
        }
}

// ─── Pile d'exécution ─────────────────────────────────────────────────────────

class AblExecutionStack(
    private val frames: List<AblStackFrame>,
) : XExecutionStack("ABL") {
    override fun getTopFrame(): XStackFrame? = frames.firstOrNull()

    override fun computeStackFrames(
        firstFrameIndex: Int,
        container: XStackFrameContainer,
    ) {
        val sub = if (firstFrameIndex < frames.size) frames.subList(firstFrameIndex, frames.size) else emptyList()
        container.addStackFrames(sub, true)
    }
}

// ─── Contexte de suspension ───────────────────────────────────────────────────

class AblSuspendContext(
    private val stack: AblExecutionStack,
) : XSuspendContext() {
    override fun getActiveExecutionStack(): XExecutionStack = stack
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

internal fun resolveFile(
    filePath: String?,
    project: Project,
): VirtualFile? {
    if (filePath.isNullOrBlank()) return null
    val lfs = LocalFileSystem.getInstance()
    return lfs.findFileByPath(filePath)
        ?: lfs.findFileByPath(filePath.replace('\\', '/'))
        ?: project.basePath?.let { lfs.findFileByPath("$it/$filePath") }
}
