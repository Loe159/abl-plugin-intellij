package com.ablls.plugin.debug

import java.io.BufferedReader
import java.io.InputStreamReader
import java.io.PrintWriter
import java.net.Socket
import java.util.concurrent.ConcurrentHashMap

/**
 * Client TCP de debug ABL.
 *
 * Architecture (OE 12.x) avec -debugReady PORT : OE est le SERVEUR.
 *   OE démarre avec -debugReady PORT → ouvre un socket d'écoute sur PORT.
 *   IntelliJ se connecte à localhost:PORT (client).
 *
 * Protocole propriétaire Progress — non documenté publiquement.
 * Commandes envoyées par IntelliJ (texte, une par ligne) :
 *   GO                         — démarrer l'exécution (après connexion + breakpoints)
 *   CONTINUE                   — reprendre après un arrêt
 *   STEP                       — step into
 *   STEP-OVER                  — step over
 *   STEP-RETURN                — step out
 *   BREAK <file> <line>        — poser un breakpoint
 *   CLEAR <file> <line>        — supprimer un breakpoint
 *   EVAL <expression>          — évaluer une expression
 *   QUIT                       — terminer la session
 *
 * Messages reçus d'OE :
 *   STOPPED <file> <line>      — programme suspendu (breakpoint/step)
 *   VALUE <expr>=<val>:<type>  — résultat d'un EVAL
 *   ERROR <message>            — erreur OE
 *
 * NOTE : Le protocole réel est inconnu. Ces commandes sont une hypothèse
 * basée sur les projets open-source (vscode-abl). À valider via Wireshark
 * en capturant une session de debug PDSOE (Progress Developer Studio).
 */
class AblDebugConnection(private val host: String = "localhost", private val port: Int) {

    private var socket: Socket? = null
    private var writer: PrintWriter? = null
    private var reader: BufferedReader? = null

    private val pendingEvals = ConcurrentHashMap<String, (value: String, type: String) -> Unit>()

    val isConnected: Boolean
        get() = socket?.let { !it.isClosed && it.isConnected } ?: false

    // ── Connexion à OE (IntelliJ = client) ───────────────────────────────────

    /**
     * Tente de se connecter à OE (qui écoute sur [host]:[port] grâce à -debugReady).
     * Lève IOException si OE n'est pas encore prêt.
     */
    @Throws(java.io.IOException::class)
    fun connect() {
        val s = Socket(host, port)
        socket = s
        writer = PrintWriter(s.outputStream, true)
        reader = BufferedReader(InputStreamReader(s.inputStream))
    }

    /**
     * Tente de se connecter répétitivement jusqu'à [timeoutMs] ms.
     * Retourne true si la connexion a réussi.
     * OE peut mettre quelques centaines de ms à ouvrir le port après le lancement.
     */
    fun connectWithRetry(timeoutMs: Long = 15_000, retryIntervalMs: Long = 100): Boolean {
        val deadline = System.currentTimeMillis() + timeoutMs
        while (System.currentTimeMillis() < deadline) {
            try {
                connect()
                return true
            } catch (_: java.io.IOException) {
                Thread.sleep(retryIntervalMs)
            }
        }
        return false
    }

    // ── Envoi de commandes ────────────────────────────────────────────────────

    fun send(cmd: String) { if (isConnected) writer?.println(cmd) }

    fun go()         = send("GO")
    fun cont()       = send("CONTINUE")
    fun stepInto()   = send("STEP")
    fun stepOver()   = send("STEP-OVER")
    fun stepReturn() = send("STEP-RETURN")
    fun quit()       = send("QUIT")

    fun setBreakpoint(file: String, line: Int)   = send("BREAK $file $line")
    fun clearBreakpoint(file: String, line: Int) = send("CLEAR $file $line")

    fun eval(expression: String, callback: (value: String, type: String) -> Unit) {
        pendingEvals[expression] = callback
        send("EVAL $expression")
    }

    // ── Écoute des messages OE ────────────────────────────────────────────────

    fun startListening(
        onSuspend: (file: String, line: Int) -> Unit,
        onError: ((message: String) -> Unit)? = null
    ) {
        Thread(null, {
            try {
                val r = reader ?: return@Thread
                while (isConnected) {
                    val line = r.readLine() ?: break
                    handleMessage(line.trim(), onSuspend, onError)
                }
            } catch (_: Exception) {}
        }, "abl-debug-listener", 0).also { it.isDaemon = true; it.start() }
    }

    private fun handleMessage(
        msg: String,
        onSuspend: (String, Int) -> Unit,
        onError: ((String) -> Unit)?
    ) {
        Regex("""^STOPPED\s+"?([^"]+)"?\s+(\d+)""").find(msg)?.let {
            onSuspend(it.groupValues[1].trim(), it.groupValues[2].toIntOrNull() ?: 1)
            return
        }
        Regex("""^VALUE\s+([^=]+)=(.+?)(?::([A-Z\-]+))?$""").find(msg)?.let {
            val expr = it.groupValues[1].trim()
            val v    = it.groupValues[2].trim()
            val type = it.groupValues[3].ifBlank { "?" }
            pendingEvals.remove(expr)?.invoke(v, type)
            return
        }
        if (msg.startsWith("ERROR") && onError != null)
            onError(msg.removePrefix("ERROR").trim())
    }

    // ── Fermeture ─────────────────────────────────────────────────────────────

    fun close() {
        runCatching { socket?.close() }
        socket = null
        writer = null
        reader = null
        pendingEvals.clear()
    }
}
