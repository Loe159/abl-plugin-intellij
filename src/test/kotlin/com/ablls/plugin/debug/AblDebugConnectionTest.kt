package com.ablls.plugin.debug

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.net.ServerSocket
import java.net.Socket
import java.util.concurrent.CompletableFuture
import java.util.concurrent.CountDownLatch
import java.util.concurrent.LinkedBlockingQueue
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean

/**
 * Tests du protocole OE debug capturé par vscode-abl (Wireshark).
 *
 * Architecture testée :
 *   - OE = serveur (écoute sur PORT via `-debugReady PORT`)
 *   - IntelliJ = client (ouvre 2 sockets vers PORT)
 *      • recvSocket — premier accept() côté OE — IntelliJ y lit les événements
 *      • sendSocket — second accept() côté OE   — IntelliJ y écrit les commandes
 *
 * Le MockOeServer ci-dessous simule OE pour valider le comportement bout-en-bout.
 */
class AblDebugConnectionTest {
    /**
     * Simule un processus OE en mode `-debugReady` :
     *   - bind sur un port local
     *   - accepte deux connexions consécutives (IntelliJ ouvre toujours 2 sockets)
     *   - première connexion = eventSock (on y écrit les événements OE → IntelliJ)
     *   - seconde connexion  = cmdSock   (on y lit les commandes IntelliJ → OE)
     */
    private class MockOeServer(requestedPort: Int = 0) : AutoCloseable {
        val server = ServerSocket(requestedPort).also { it.soTimeout = 5_000 }
        val port: Int = server.localPort

        private var eventSock: Socket? = null
        private var cmdSock: Socket? = null

        val received = LinkedBlockingQueue<String>()

        fun acceptConnections() {
            eventSock = server.accept()
            cmdSock = server.accept()
            startCmdReader()
        }

        private fun startCmdReader() {
            Thread(null, {
                val stream = cmdSock?.inputStream ?: return@Thread
                val buf = ArrayList<Byte>()
                var b: Int
                while (stream.read().also { b = it } != -1) {
                    if (b == 0) {
                        if (buf.isNotEmpty()) {
                            received.add(String(buf.toByteArray(), Charsets.UTF_8))
                            buf.clear()
                        }
                    } else {
                        buf.add(b.toByte())
                    }
                }
            }, "mock-oe-cmd-reader", 0).also {
                it.isDaemon = true
                it.start()
            }
        }

        fun nextCmd(timeoutMs: Long = 3_000): String =
            received.poll(timeoutMs, TimeUnit.MILLISECONDS)
                ?: throw AssertionError("Timeout: no command received in ${timeoutMs}ms")

        fun sendEvent(msg: String) {
            val s = eventSock ?: error("eventSock not initialized — call acceptConnections() first")
            s.outputStream.write(msg.toByteArray(Charsets.UTF_8))
            s.outputStream.write(0)
            s.outputStream.flush()
        }

        override fun close() {
            runCatching { eventSock?.close() }
            runCatching { cmdSock?.close() }
            runCatching { server.close() }
        }
    }

    private fun withSession(block: (MockOeServer, AblDebugConnection) -> Unit) {
        MockOeServer().use { server ->
            val acceptFuture = CompletableFuture.runAsync { server.acceptConnections() }
            val conn = AblDebugConnection(port = server.port)
            conn.connect()
            acceptFuture.get(3, TimeUnit.SECONDS)
            try {
                block(server, conn)
            } finally {
                conn.close()
            }
        }
    }

    // ── Connexion ─────────────────────────────────────────────────────────────

    @Test
    fun `connect opens exactly two sockets to OE`() {
        MockOeServer().use { server ->
            val count = java.util.concurrent.atomic.AtomicInteger(0)
            val thread =
                Thread {
                    repeat(2) { server.server.accept().also { count.incrementAndGet() } }
                }.also {
                    it.isDaemon = true
                    it.start()
                }

            val conn = AblDebugConnection(port = server.port)
            conn.connect()
            thread.join(2_000)

            assertEquals("OE must accept exactly 2 connections", 2, count.get())
            conn.close()
        }
    }

    @Test
    fun `connectWithRetry succeeds when OE starts within timeout`() {
        val port = findFreePort()
        var srv: MockOeServer? = null

        Thread {
            Thread.sleep(250) // simulate OE taking time to start
            srv = MockOeServer(port).also { it.acceptConnections() }
        }.also {
            it.isDaemon = true
            it.start()
        }

        val conn = AblDebugConnection(port = port)
        val ok = conn.connectWithRetry(timeoutMs = 5_000, retryIntervalMs = 50)

        assertTrue("connectWithRetry must succeed while OE is starting", ok)
        assertTrue(conn.isConnected)
        conn.close()
        srv?.close()
    }

    @Test
    fun `connectWithRetry returns false when timeout expires`() {
        val port = findFreePort() // unused, nothing listens
        val conn = AblDebugConnection(port = port)
        val start = System.currentTimeMillis()
        val ok = conn.connectWithRetry(timeoutMs = 300, retryIntervalMs = 50)
        val elapsed = System.currentTimeMillis() - start

        assertFalse(ok)
        assertTrue("Must give up around the timeout, elapsed=$elapsed", elapsed in 250..1_500)
    }

    // ── Handshake ─────────────────────────────────────────────────────────────

    @Test
    fun `startDebugging sends SETPROP IDE 1`() {
        withSession { server, conn ->
            conn.startDebugging()
            assertEquals("SETPROP IDE 1", server.nextCmd())
        }
    }

    @Test
    fun `startDebugging sends an empty break command when no breakpoints registered`() {
        withSession { server, conn ->
            conn.startDebugging()
            server.nextCmd() // SETPROP IDE 1
            assertEquals("break;", server.nextCmd())
        }
    }

    @Test
    fun `startDebugging sends pre-registered breakpoints in handshake`() {
        withSession { server, conn ->
            conn.setBreakpoint("C:/prog.p", 10)
            conn.setBreakpoint("C:/prog.p", 25)
            conn.startDebugging()

            server.nextCmd() // SETPROP IDE 1
            val bp = server.nextCmd()
            assertTrue(bp.contains("B;1;E;C:/prog.p;10; ;"))
            assertTrue(bp.contains("B;2;E;C:/prog.p;25; ;"))
        }
    }

    // ── Breakpoints ───────────────────────────────────────────────────────────

    @Test
    fun `setBreakpoint sends complete list in captured format`() {
        withSession { server, conn ->
            conn.startDebugging()
            server.nextCmd()
            server.nextCmd() // drain handshake

            conn.setBreakpoint("C:/oe/test.p", 18)
            assertEquals("break B;1;E;C:/oe/test.p;18; ;", server.nextCmd())
        }
    }

    @Test
    fun `setBreakpoint normalizes backslashes to forward slashes`() {
        withSession { server, conn ->
            conn.startDebugging()
            server.nextCmd()
            server.nextCmd()

            conn.setBreakpoint("D:\\ws\\Test\\test.p", 5)
            val bp = server.nextCmd()

            assertFalse("No backslash allowed", bp.contains('\\'))
            assertTrue(bp.contains("D:/ws/Test/test.p"))
        }
    }

    @Test
    fun `multiple breakpoints arrive in a single command`() {
        withSession { server, conn ->
            conn.startDebugging()
            server.nextCmd()
            server.nextCmd()

            conn.setBreakpoint("C:/test.p", 10)
            server.nextCmd()
            conn.setBreakpoint("C:/test.p", 27)
            val cmd = server.nextCmd()

            assertTrue(cmd.contains("B;1;E;C:/test.p;10; ;"))
            assertTrue(cmd.contains("B;2;E;C:/test.p;27; ;"))
        }
    }

    @Test
    fun `clearBreakpoint removes only the matching breakpoint`() {
        withSession { server, conn ->
            conn.startDebugging()
            server.nextCmd()
            server.nextCmd()

            conn.setBreakpoint("C:/test.p", 10)
            conn.setBreakpoint("C:/test.p", 27)
            server.nextCmd()
            server.nextCmd()

            conn.clearBreakpoint("C:/test.p", 10)
            val cmd = server.nextCmd()

            assertFalse(cmd.contains(";10;"))
            assertTrue(cmd.contains(";27;"))
        }
    }

    @Test
    fun `setBreakpoint is idempotent on duplicates`() {
        withSession { server, conn ->
            conn.startDebugging()
            server.nextCmd()
            server.nextCmd()

            conn.setBreakpoint("C:/test.p", 42)
            server.nextCmd()
            // Duplicate — must not send any new command
            conn.setBreakpoint("C:/test.p", 42)

            val extra = server.received.poll(200, TimeUnit.MILLISECONDS)
            assertNull("Duplicate breakpoint must not produce a new command", extra)
        }
    }

    // ── MSG_ENTER → onStopped ─────────────────────────────────────────────────

    @Test
    fun `MSG_ENTER triggers onStopped and re-sends breakpoints`() {
        val stopped = AtomicBoolean(false)
        withSession { server, conn ->
            conn.onStopped = { stopped.set(true) }
            conn.startDebugging()
            server.nextCmd()
            server.nextCmd()

            conn.setBreakpoint("C:/test.p", 42)
            server.nextCmd()

            server.sendEvent("MSG_ENTER")
            val resent = server.nextCmd()
            Thread.sleep(80)

            assertTrue(resent.contains("B;1;E;C:/test.p;42; ;"))
            assertTrue("onStopped must fire on MSG_ENTER", stopped.get())
        }
    }

    @Test
    fun `MSG_EXIT triggers onExit`() {
        val exited = AtomicBoolean(false)
        withSession { server, conn ->
            conn.onExit = { exited.set(true) }
            conn.startDebugging()
            server.nextCmd()
            server.nextCmd()

            server.sendEvent("MSG_EXIT")
            Thread.sleep(150)

            assertTrue(exited.get())
        }
    }

    // ── Stack frames ──────────────────────────────────────────────────────────

    @Test
    fun `showStack parses a single frame`() {
        withSession { server, conn ->
            conn.startDebugging()
            server.nextCmd()
            server.nextCmd()

            val future = CompletableFuture<List<OeStackFrame>>()
            Thread { future.complete(conn.showStack()) }.also { it.isDaemon = true }.start()

            assertEquals("show stack-ide", server.nextCmd())

            // Indexing (matches vscode-abl):
            //   field[4] = file path
            //   field[6] = function name
            //   field[8] = line number
            server.sendEvent("STACK-IDE;\nY;1;myProc;N;C:/oe/test.p;test.p;myProc;C:/oe/test.p;42;\n")

            val frames = future.get(3, TimeUnit.SECONDS)
            assertEquals(1, frames.size)
            assertEquals("C:/oe/test.p", frames[0].file)
            assertEquals("myProc", frames[0].function)
            assertEquals(42, frames[0].line)
        }
    }

    @Test
    fun `showStack reverses frames so the deepest call is at index 0 (top of stack)`() {
        withSession { server, conn ->
            conn.startDebugging()
            server.nextCmd()
            server.nextCmd()

            val future = CompletableFuture<List<OeStackFrame>>()
            Thread { future.complete(conn.showStack()) }.also { it.isDaemon = true }.start()
            server.nextCmd()

            // OE envoie caller (mainBlock) puis callee (helper) — vscode-abl inverse
            // pour qu'XDebugger affiche helper en haut de pile (ligne bleue = code en cours).
            server.sendEvent(
                "STACK-IDE;" +
                    "\nY;1;mainBlock;N;C:/oe/main.p;main.p;mainBlock;C:/oe/main.p;15;" +
                    "\nY;2;helper;N;C:/oe/util.p;util.p;helper;C:/oe/util.p;73;\n",
            )

            val frames = future.get(3, TimeUnit.SECONDS)
            assertEquals(2, frames.size)
            // Top of stack = frame courante = la plus profonde (helper, ligne 73)
            assertEquals("helper", frames[0].function)
            assertEquals(73, frames[0].line)
            assertEquals("C:/oe/util.p", frames[0].file)
            // En-dessous : le caller (mainBlock, ligne 15)
            assertEquals("mainBlock", frames[1].function)
            assertEquals(15, frames[1].line)
        }
    }

    // ── Variables ─────────────────────────────────────────────────────────────

    @Test
    fun `listVariables parses INTEGER`() {
        withSession { server, conn ->
            conn.startDebugging()
            server.nextCmd()
            server.nextCmd()

            val future = CompletableFuture<List<OeVariable>>()
            Thread { future.complete(conn.listVariables()) }.also { it.isDaemon = true }.start()
            assertEquals("list variables", server.nextCmd())

            server.sendEvent("MSG_VARIABLES;\ncount;INTEGER;?;?;0;RW;42;\n")

            val vars = future.get(3, TimeUnit.SECONDS)
            assertEquals(1, vars.size)
            assertEquals("count", vars[0].name)
            assertEquals("INTEGER", vars[0].type)
            assertEquals("42", vars[0].value)
            assertEquals(OeVarKind.VARIABLE, vars[0].kind)
        }
    }

    @Test
    fun `listVariables decodes CHARACTER with DC2-length-quote encoding`() {
        withSession { server, conn ->
            conn.startDebugging()
            server.nextCmd()
            server.nextCmd()

            val future = CompletableFuture<List<OeVariable>>()
            Thread { future.complete(conn.listVariables()) }.also { it.isDaemon = true }.start()
            server.nextCmd()

            // DC2 (\x12) + digits + "value"
            val dc2 = "\u0012"
            server.sendEvent("MSG_VARIABLES;\nname;CHARACTER;?;?;0;RW;${dc2}5\"hello\";\n")

            val vars = future.get(3, TimeUnit.SECONDS)
            assertEquals(1, vars.size)
            assertEquals("hello", vars[0].value)
        }
    }

    @Test
    fun `listVariables identifies array kind when extent gt 0`() {
        withSession { server, conn ->
            conn.startDebugging()
            server.nextCmd()
            server.nextCmd()

            val future = CompletableFuture<List<OeVariable>>()
            Thread { future.complete(conn.listVariables()) }.also { it.isDaemon = true }.start()
            server.nextCmd()

            server.sendEvent("MSG_VARIABLES;\narr;INTEGER;?;?;5;RW;[5];\n")

            val vars = future.get(3, TimeUnit.SECONDS)
            assertEquals(OeVarKind.ARRAY, vars[0].kind)
        }
    }

    @Test
    fun `getArray parses MSG_ARRAY and keeps every 3rd field`() {
        withSession { server, conn ->
            conn.startDebugging()
            server.nextCmd()
            server.nextCmd()

            val future = CompletableFuture<List<String>>()
            Thread { future.complete(conn.getArray("iValeurs", "INTEGER")) }
                .also { it.isDaemon = true }.start()
            assertEquals("GET-ARRAY iValeurs", server.nextCmd())

            // Format vscode-abl : on garde les indices 2, 5, 8, … (chaque 3ᵉ champ).
            server.sendEvent("MSG_ARRAY;a;b;1;c;d;4;e;f;9;g;h;16;i;j;25;")

            val values = future.get(3, TimeUnit.SECONDS)
            assertEquals(5, values.size)
            assertEquals(listOf("1", "4", "9", "16", "25"), values)
        }
    }

    @Test
    fun `getArray decodes CHARACTER DC2 encoding per element`() {
        withSession { server, conn ->
            conn.startDebugging()
            server.nextCmd()
            server.nextCmd()

            val future = CompletableFuture<List<String>>()
            Thread { future.complete(conn.getArray("noms", "CHARACTER")) }
                .also { it.isDaemon = true }.start()
            server.nextCmd()

            val dc2 = ""
            server.sendEvent(
                "MSG_ARRAY;a;b;${dc2}3\"foo\";c;d;${dc2}3\"bar\";e;f;${dc2}3\"baz\";",
            )

            val values = future.get(3, TimeUnit.SECONDS)
            assertEquals(listOf("foo", "bar", "baz"), values)
        }
    }

    @Test
    fun `listParameters decorates name with arrows by mode`() {
        withSession { server, conn ->
            conn.startDebugging()
            server.nextCmd()
            server.nextCmd()

            val future = CompletableFuture<List<OeVariable>>()
            Thread { future.complete(conn.listParameters()) }.also { it.isDaemon = true }.start()
            assertEquals("list parameters", server.nextCmd())

            server.sendEvent(
                "MSG_PARAMETERS;" +
                    "\nINPUT;in1;INTEGER;?;?;7;" +
                    "\nOUTPUT;out1;INTEGER;?;?;0;" +
                    "\nINPUT-OUTPUT;io1;INTEGER;?;?;3;\n",
            )

            val params = future.get(3, TimeUnit.SECONDS)
            assertEquals(3, params.size)
            assertEquals("→ in1", params[0].name)
            assertEquals("← out1", params[1].name)
            assertEquals("↔ io1", params[2].name)
            assertTrue(params.all { it.kind == OeVarKind.PARAMETER })
        }
    }

    // ── Commandes de contrôle ─────────────────────────────────────────────────

    @Test
    fun `cont sends 'cont'`() {
        withSession { server, conn ->
            conn.startDebugging()
            server.nextCmd()
            server.nextCmd()
            conn.cont()
            assertEquals("cont", server.nextCmd())
        }
    }

    @Test
    fun `stepOver sends 'next'`() {
        withSession { server, conn ->
            conn.startDebugging()
            server.nextCmd()
            server.nextCmd()
            conn.stepOver()
            assertEquals("next", server.nextCmd())
        }
    }

    @Test
    fun `stepInto sends 'step'`() {
        withSession { server, conn ->
            conn.startDebugging()
            server.nextCmd()
            server.nextCmd()
            conn.stepInto()
            assertEquals("step", server.nextCmd())
        }
    }

    @Test
    fun `stepReturn sends 'step-out'`() {
        withSession { server, conn ->
            conn.startDebugging()
            server.nextCmd()
            server.nextCmd()
            conn.stepReturn()
            assertEquals("step-out", server.nextCmd())
        }
    }

    @Test
    fun `interrupt sends 'interrupt'`() {
        withSession { server, conn ->
            conn.startDebugging()
            server.nextCmd()
            server.nextCmd()
            conn.interrupt()
            assertEquals("interrupt", server.nextCmd())
        }
    }

    @Test
    fun `close sends SETPROP IDE 0 before tearing down sockets`() {
        withSession { server, conn ->
            conn.startDebugging()
            server.nextCmd()
            server.nextCmd()
            conn.close()
            // SETPROP IDE 0 envoyé — éventuelle prochaine commande
            val cmd = server.received.poll(500, TimeUnit.MILLISECONDS)
            assertEquals("SETPROP IDE 0", cmd)
        }
    }

    // ── Scénario complet ──────────────────────────────────────────────────────

    @Test
    fun `full scenario - breakpoint hit fires onStopped and showStack returns the location`() {
        val stopped = CountDownLatch(1)
        var frames: List<OeStackFrame> = emptyList()

        withSession { server, conn ->
            conn.onStopped = {
                Thread {
                    frames = conn.showStack()
                    stopped.countDown()
                }
                    .also { it.isDaemon = true }.start()
            }

            // Handshake
            conn.startDebugging()
            assertEquals("SETPROP IDE 1", server.nextCmd())
            assertEquals("break;", server.nextCmd())

            // Set a breakpoint
            conn.setBreakpoint("D:/ws/Test/test.p", 18)
            val bp = server.nextCmd()
            assertTrue(bp.contains("D:/ws/Test/test.p;18;"))

            // OE hits the breakpoint — sends MSG_ENTER then expects stack request
            server.sendEvent("MSG_ENTER")
            server.nextCmd() // BPs re-sent (OE clears at scope entry)
            assertEquals("show stack-ide", server.nextCmd())

            // Respond with a single-frame stack
            server.sendEvent("STACK-IDE;\nY;1;main;N;D:/ws/Test/test.p;test.p;main;D:/ws/Test/test.p;18;\n")

            assertTrue("onStopped + stack must complete in time", stopped.await(3, TimeUnit.SECONDS))
            assertEquals(1, frames.size)
            assertEquals(18, frames[0].line)
            assertEquals("D:/ws/Test/test.p", frames[0].file)
        }
    }
}

// ── Helpers ───────────────────────────────────────────────────────────────────

private fun findFreePort(): Int = java.net.ServerSocket(0).use { it.localPort }
