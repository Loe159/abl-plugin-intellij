package com.ablls.plugin.debug

import java.io.BufferedReader
import java.io.InputStreamReader
import java.io.PrintWriter
import java.net.Socket

/**
 * Connexion TCP vers le debugger OpenEdge.
 * Le format du protocole OE debugger est :
 *   Client → "BREAKPOINT file.p 42" / "RESUME" / "STEP_OVER" / "STEP_INTO" / "STEP_OUT"
 *   Server → "STOPPED file.p 42" / "EVAL varname=value"
 */
class AblDebugConnection(host: String, port: Int) {

    private val socket: Socket = Socket(host, port)
    private val writer = PrintWriter(socket.outputStream, true)
    private val reader = BufferedReader(InputStreamReader(socket.inputStream))

    val isConnected: Boolean get() = !socket.isClosed

    fun send(cmd: String) {
        if (isConnected) writer.println(cmd)
    }

    /**
     * Démarre le thread d'écoute des messages serveur.
     * @param onSuspend appelé quand le processus s'arrête (STOPPED file.p line)
     */
    fun startListening(onSuspend: (file: String, line: Int) -> Unit) {
        Thread(null, {
            try {
                while (isConnected) {
                    val line = reader.readLine() ?: break
                    val m = Regex("""STOPPED\s+(\S+)\s+(\d+)""").find(line) ?: continue
                    onSuspend(m.groupValues[1], m.groupValues[2].toInt())
                }
            } catch (_: Exception) {}
        }, "abl-debug-listener", 0).also {
            it.isDaemon = true
            it.start()
        }
    }

    fun close() {
        runCatching { socket.close() }
    }
}
