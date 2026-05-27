package com.ablls.plugin.debug

import com.intellij.openapi.diagnostic.thisLogger
import java.io.InputStream
import java.io.OutputStream
import java.net.Socket
import java.util.concurrent.CompletableFuture
import java.util.concurrent.CopyOnWriteArrayList
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicInteger
import java.util.concurrent.atomic.AtomicReference

/**
 * Connexion TCP au debugger OpenEdge (`_progres.exe -debugReady PORT`).
 *
 * Protocole reverse-engineerd par vscode-abl (https://github.com/chriscamicas/vscode-abl)
 * et confirmé via proxy PDSOE ↔ OE (`tools/oe-debug-proxy.py`). Closed-source côté
 * Progress, mais stable entre versions OE 11.x / 12.x.
 *
 * ## Architecture
 *
 * OE est le **serveur** : `-debugReady PORT` fait écouter OE sur PORT.
 * IntelliJ est le **client** : on ouvre **deux** sockets vers le même port.
 *
 *   recvSocket — premier connect() — réservé aux événements OE (MSG_ENTER, MSG_LISTING, …)
 *   sendSocket — second connect()  — réservé aux commandes IDE (SETPROP, break, cont, …)
 *
 * Découvert dans vscode-abl/src/debugAdapter/ablDebug.ts (classe AblDebugger).
 *
 * ## Encodage des messages
 *
 * Tous les messages sont du texte ASCII/UTF-8 terminé par un octet nul (0x00).
 * Plusieurs messages peuvent arriver dans un même paquet TCP — le lecteur split sur 0x00.
 *
 * Format générique : `CODE;<corps>;` où `<corps>` est soit semicolon-separated soit
 * lines-then-semicolons selon le CODE. Voir [parseStack], [parseVariables].
 *
 * ## Séquence de session
 *
 *   1. [connect]            — ouvre recvSocket puis sendSocket
 *   2. [startDebugging]     — envoie `SETPROP IDE 1` puis la liste des breakpoints
 *   3. À chaque MSG_ENTER   — OE est suspendu. On renvoie les breakpoints (OE les efface
 *                              à chaque entrée dans un nouveau scope) et on notifie [onStopped].
 *   4. [showStack]          — `show stack-ide` → STACK-IDE → liste des frames
 *   5. [listVariables]      — `list variables` → MSG_VARIABLES → variables du scope courant
 *   6. [cont] / [stepXxx]   — reprend l'exécution
 *   7. MSG_EXIT             — OE quitte → [onExit]
 */
class AblDebugConnection(
    private val host: String = "localhost",
    private val port: Int,
) {
    private val log = thisLogger()

    private var recvSocket: Socket? = null
    private var sendSocket: Socket? = null
    private var sendOut: OutputStream? = null

    private val bpIdGen = AtomicInteger(1)
    private val breakpoints = CopyOnWriteArrayList<BpEntry>()
    private val sessionReady = AtomicBoolean(false)

    private val pendingVars = AtomicReference<CompletableFuture<List<OeVariable>>?>()
    private val pendingParams = AtomicReference<CompletableFuture<List<OeVariable>>?>()
    private val pendingStack = AtomicReference<CompletableFuture<List<OeStackFrame>>?>()
    private val pendingArray = AtomicReference<CompletableFuture<List<String>>?>()

    /** Notifié à chaque MSG_ENTER : OE vient de se suspendre. La position est récupérée via [showStack]. */
    var onStopped: (() -> Unit)? = null

    /** Notifié à MSG_EXIT : OE quitte (programme terminé ou interrompu). */
    var onExit: (() -> Unit)? = null

    val isConnected get() = sendSocket?.let { !it.isClosed && it.isConnected } == true

    private data class BpEntry(val id: Int, val path: String, val line: Int)

    // ── Connexion TCP ─────────────────────────────────────────────────────────

    /**
     * Ouvre les deux sockets vers OE. Lève [java.io.IOException] si la connexion échoue.
     * À appeler après que OE a été spawné avec `-debugReady PORT` et écoute effectivement.
     */
    @Throws(java.io.IOException::class)
    fun connect() {
        val recv = Socket(host, port)
        val send =
            try {
                Socket(host, port)
            } catch (e: java.io.IOException) {
                runCatching { recv.close() }
                throw e
            }
        recvSocket = recv
        sendSocket = send
        sendOut = send.outputStream
        startReaderThread(recv.inputStream)
    }

    /**
     * Réessaie [connect] jusqu'à [timeoutMs]. Utile pour attendre qu'OE
     * finisse de démarrer et ouvre son socket d'écoute.
     */
    fun connectWithRetry(
        timeoutMs: Long = 15_000,
        retryIntervalMs: Long = 100,
    ): Boolean {
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

    // ── Démarrage du debug ────────────────────────────────────────────────────

    /**
     * À appeler une fois la session XDebug initialisée (breakpoints enregistrés
     * côté IntelliJ). Envoie `SETPROP IDE 1` puis la liste complète des breakpoints.
     */
    fun startDebugging() {
        sessionReady.set(true)
        sendCmd("SETPROP IDE 1")
        sendBreakpoints()
    }

    // ── Commandes ─────────────────────────────────────────────────────────────

    private fun sendCmd(cmd: String) {
        val o = sendOut ?: return
        try {
            synchronized(o) {
                o.write(cmd.toByteArray(Charsets.UTF_8))
                o.write(0)
                o.flush()
            }
        } catch (e: Exception) {
            log.warn("Failed to send debug command '$cmd': ${e.message}")
        }
    }

    fun cont() = sendCmd("cont")

    fun stepInto() = sendCmd("step")

    fun stepOver() = sendCmd("next")

    fun stepReturn() = sendCmd("step-out")

    fun interrupt() = sendCmd("interrupt")

    /** Évalue une expression côté OE (ex. `ASSIGN x = 42`). La réponse arrive via le flux normal. */
    fun sendRaw(expression: String) = sendCmd(expression)

    // ── Breakpoints ───────────────────────────────────────────────────────────

    fun setBreakpoint(
        filePath: String,
        line: Int,
    ) {
        val path = filePath.replace('\\', '/')
        if (breakpoints.any { it.path == path && it.line == line }) return
        breakpoints.add(BpEntry(bpIdGen.getAndIncrement(), path, line))
        if (sessionReady.get() && isConnected) sendBreakpoints()
    }

    fun clearBreakpoint(
        filePath: String,
        line: Int,
    ) {
        val path = filePath.replace('\\', '/')
        val bp = breakpoints.find { it.path == path && it.line == line } ?: return
        breakpoints.remove(bp)
        if (sessionReady.get() && isConnected) sendBreakpoints()
    }

    /**
     * Envoie la liste complète des breakpoints actifs en une seule commande.
     *
     * Format reverse-engineerd : `break B;{id};E;{path};{line}; ;…`
     * Liste vide : `break;` (efface tous les breakpoints côté OE).
     */
    private fun sendBreakpoints() {
        val bps = breakpoints.toList()
        if (bps.isEmpty()) {
            sendCmd("break;")
            return
        }
        val sb = StringBuilder("break ")
        for (bp in bps) sb.append("B;${bp.id};E;${bp.path};${bp.line}; ;")
        sendCmd(sb.toString())
    }

    // ── Requêtes synchrones ───────────────────────────────────────────────────

    fun showStack(timeoutMs: Long = 5_000): List<OeStackFrame> {
        return request("show stack-ide", pendingStack, timeoutMs) ?: emptyList()
    }

    fun listVariables(timeoutMs: Long = 5_000): List<OeVariable> {
        return request("list variables", pendingVars, timeoutMs) ?: emptyList()
    }

    fun listParameters(timeoutMs: Long = 5_000): List<OeVariable> {
        return request("list parameters", pendingParams, timeoutMs) ?: emptyList()
    }

    /**
     * Récupère les éléments d'une variable EXTENT/ARRAY. ABL est 1-indexé :
     * l'élément retourné en position 0 correspond à `name[1]` dans le code.
     */
    fun getArray(
        name: String,
        type: String,
        timeoutMs: Long = 5_000,
    ): List<String> {
        val raw = request("GET-ARRAY $name", pendingArray, timeoutMs) ?: return emptyList()
        return raw.map { decodeValue(type, it) }
    }

    private fun <T> request(
        command: String,
        slot: AtomicReference<CompletableFuture<T>?>,
        timeoutMs: Long,
    ): T? {
        val future = CompletableFuture<T>()
        slot.set(future)
        sendCmd(command)
        return try {
            future.get(timeoutMs, TimeUnit.MILLISECONDS)
        } catch (_: Exception) {
            slot.set(null)
            null
        }
    }

    // ── Lecteur (thread dédié sur recvSocket) ─────────────────────────────────

    private fun startReaderThread(stream: InputStream) {
        Thread(null, {
            try {
                val buf = ArrayList<Byte>(512)
                var b: Int
                while (stream.read().also { b = it } != -1) {
                    if (b == 0) {
                        if (buf.isNotEmpty()) {
                            dispatch(String(buf.toByteArray(), Charsets.UTF_8))
                            buf.clear()
                        }
                    } else {
                        buf.add(b.toByte())
                    }
                }
            } catch (e: Exception) {
                log.debug("Debug reader thread terminated: ${e.message}")
            }
        }, "abl-debug-reader", 0).also {
            it.isDaemon = true
            it.start()
        }
    }

    private fun dispatch(msg: String) {
        val code = msg.substringBefore(';')
        when (code) {
            "MSG_ENTER" -> {
                // OE clears its breakpoints when entering a new scope — re-send them.
                sendBreakpoints()
                onStopped?.invoke()
            }
            "MSG_EXIT" -> onExit?.invoke()
            "STACK-IDE" -> pendingStack.getAndSet(null)?.complete(parseStack(msg))
            "MSG_VARIABLES" -> pendingVars.getAndSet(null)?.complete(parseVarLines(msg, "MSG_VARIABLES"))
            "MSG_PARAMETERS" -> pendingParams.getAndSet(null)?.complete(parseParameters(msg))
            "MSG_ARRAY" -> pendingArray.getAndSet(null)?.complete(parseArray(msg))
            // MSG_LISTING, MSG_STATUS, MSG_INFO : ignorés (informationnels).
        }
    }

    // ── Parsers (formats reverse-engineerd par vscode-abl/messages.ts) ────────

    /**
     * `STACK-IDE;Y;<id>;<scope>;N;<file>;<display>;<func>;<file>;<line>;…`
     *
     * Une frame par ligne logique (séparées par '\n' dans le corps).
     * Indexation reverse-engineerd par vscode-abl (ablDebug.ts:stackTraceRequest) :
     *   args[4] = chemin fichier, args[6] = nom fonction, args[8] = ligne.
     *
     * OE envoie les frames dans l'ordre **caller → callee** (la première ligne est
     * le point d'entrée, la dernière est le code en cours d'exécution).
     * On les **inverse** pour qu'XDebugger affiche la frame courante en haut de la pile
     * — sinon IntelliJ pose la ligne bleue sur le caller (par ex. le bootstrap).
     */
    private fun parseStack(msg: String): List<OeStackFrame> {
        val body = msg.removePrefix("STACK-IDE;").trimStart('\n', ';')
        val rawFrames =
            body.split('\n')
                .filter { it.isNotBlank() }
                .map { it.split(';') }
                .filter { it.isNotEmpty() }
        return rawFrames.mapNotNull { f ->
            val file = f.getOrNull(4)?.takeIf { it.isNotBlank() }
            val name = f.getOrNull(6)?.takeIf { it.isNotBlank() } ?: "(unknown)"
            val line = f.getOrNull(8)?.toIntOrNull() ?: return@mapNotNull null
            OeStackFrame(file = file, function = name, line = line)
        }.reversed()
    }

    /**
     * `MSG_VARIABLES;\n<name>;<type>;<class?>;?;<extent>;<R|RW>;<value>;\n…`
     */
    private fun parseVarLines(
        msg: String,
        prefix: String,
    ): List<OeVariable> {
        val body = msg.removePrefix("$prefix;").trimStart('\n')
        return body.split('\n')
            .map { it.trim() }
            .filter { it.isNotEmpty() }
            .mapNotNull { line ->
                val parts = line.trimEnd(';').split(';')
                if (parts.size < 7) return@mapNotNull null
                val name = parts[0]
                val type = parts[1]
                val classType = parts[2].takeIf { it != "?" && it.isNotBlank() }
                val extent = parts[4].toIntOrNull() ?: 0
                val raw = parts[6]
                val kind =
                    when {
                        classType != null -> OeVarKind.CLASS
                        extent > 0 -> OeVarKind.ARRAY
                        else -> OeVarKind.VARIABLE
                    }
                OeVariable(
                    name = name,
                    type = classType ?: type,
                    value = decodeValue(type, raw),
                    kind = kind,
                )
            }
    }

    /**
     * Réponse à `GET-ARRAY <name>` : `MSG_ARRAY;<x>;<y>;<val1>;<x>;<y>;<val2>;…`
     *
     * Format reverse-engineerd par vscode-abl/messages.ts :
     * on retire les '\n', on coupe par ';', et on garde les indices 2, 5, 8, … (chaque 3ᵉ champ).
     * Les valeurs CHARACTER conservent leur encodage DC2 — décodage géré par [getArray].
     */
    private fun parseArray(msg: String): List<String> {
        val body = msg.removePrefix("MSG_ARRAY;").replace("\n", "")
        val fields = body.split(';')
        // Indices 2, 5, 8, … — chaque 3ᵉ champ contient la valeur.
        return fields.filterIndexed { i, _ -> (i + 1) % 3 == 0 }
    }

    /**
     * `MSG_PARAMETERS;\n<INPUT|OUTPUT|INPUT-OUTPUT>;<name>;<type>;<?>;<?>;<value>;\n…`
     */
    private fun parseParameters(msg: String): List<OeVariable> {
        val body = msg.removePrefix("MSG_PARAMETERS;").trimStart('\n')
        return body.split('\n')
            .map { it.trim() }
            .filter { it.isNotEmpty() }
            .mapNotNull { line ->
                val parts = line.trimEnd(';').split(';')
                if (parts.size < 6) return@mapNotNull null
                val mode = parts[0]
                val arrow =
                    when (mode) {
                        "INPUT" -> "→ "
                        "OUTPUT" -> "← "
                        "INPUT-OUTPUT" -> "↔ "
                        else -> ""
                    }
                OeVariable(
                    name = "$arrow${parts[1]}",
                    type = parts[2],
                    value = decodeValue(parts[2], parts[5]),
                    kind = OeVarKind.PARAMETER,
                )
            }
    }

    /**
     * Les CHARACTER/LONGCHAR sont encodés `\x12<length-digits>"value"`.
     * Décodage : on retire le DC2 (0x12) puis les chiffres de longueur, on garde le contenu entre guillemets.
     */
    private fun decodeValue(
        type: String,
        raw: String,
    ): String {
        if (raw.isEmpty()) return raw
        if (type != "CHARACTER" && type != "LONGCHAR") return raw
        if (raw[0].code != 0x12) return raw

        var i = 1
        while (i < raw.length && raw[i].isDigit()) i++
        if (i >= raw.length || raw[i] != '"') return raw.drop(i)
        val content = raw.substring(i + 1)
        return if (content.endsWith('"')) content.dropLast(1) else content
    }

    // ── Fermeture ─────────────────────────────────────────────────────────────

    fun close() {
        if (sessionReady.getAndSet(false) && isConnected) {
            runCatching { sendCmd("SETPROP IDE 0") }
        }
        runCatching { recvSocket?.close() }
        runCatching { sendSocket?.close() }
        recvSocket = null
        sendSocket = null
        sendOut = null
        pendingVars.set(null)
        pendingParams.set(null)
        pendingStack.set(null)
        pendingArray.set(null)
    }
}

// ─── Types de données ────────────────────────────────────────────────────────

enum class OeVarKind { VARIABLE, PARAMETER, CLASS, ARRAY }

data class OeVariable(
    val name: String,
    val type: String,
    val value: String,
    val kind: OeVarKind = OeVarKind.VARIABLE,
)

data class OeStackFrame(
    val file: String?,
    val function: String,
    val line: Int,
)
