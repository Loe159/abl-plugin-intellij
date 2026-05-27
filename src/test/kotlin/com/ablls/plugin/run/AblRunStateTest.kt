package com.ablls.plugin.run

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Tests pour la logique de construction des arguments OE dans AblRunState.buildArgList().
 *
 * Ces tests sont purement unitaires — aucune dépendance IntelliJ.
 * Ils vérifient notamment les règles sur le flag -b et -debugReady.
 */
class AblRunStateTest {
    private val exe = "D:/dlc/bin/_progres.exe"
    private val prog = "D:/ws/test.p"

    // ── Règles sur -b ──────────────────────────────────────────────────────────
    // Proxy PDSOE↔OE confirme : `_progres.exe -b -p prog.p -debugReady PORT`
    // -b est TOUJOURS présent quand batchMode=true, y compris en debug mode.
    // Sans -b, _progres.exe essaie d'ouvrir un terminal et termine si aucun n'est disponible.

    @Test
    fun `batch mode adds -b in normal run`() {
        val args = AblRunState.buildArgList(exe, prog, batchMode = true, forDebug = false, debugPort = 0)
        assertTrue("-b doit être présent en run normal avec batchMode=true", args.contains("-b"))
    }

    @Test
    fun `no batch mode does not add -b`() {
        val args = AblRunState.buildArgList(exe, prog, batchMode = false, forDebug = false, debugPort = 0)
        assertFalse("-b ne doit pas être présent quand batchMode=false", args.contains("-b"))
    }

    @Test
    fun `batch mode adds -b in debug mode too`() {
        // Proxy PDSOE↔OE : -b est utilisé avec -debugReady, requis pour headless
        val args = AblRunState.buildArgList(exe, prog, batchMode = true, forDebug = true, debugPort = 0)
        assertTrue("-b doit être présent en debug avec batchMode=true", args.contains("-b"))
    }

    @Test
    fun `batch mode adds -b when debugPort is set`() {
        val args = AblRunState.buildArgList(exe, prog, batchMode = true, forDebug = false, debugPort = 3075)
        assertTrue("-b doit être présent quand debugPort > 0 et batchMode=true", args.contains("-b"))
    }

    @Test
    fun `batch mode adds -b with both forDebug and debugPort`() {
        val args = AblRunState.buildArgList(exe, prog, batchMode = true, forDebug = true, debugPort = 3075)
        assertTrue("-b doit être présent en debug complet", args.contains("-b"))
    }

    @Test
    fun `no batch mode does not add -b in debug mode`() {
        val args = AblRunState.buildArgList(exe, prog, batchMode = false, forDebug = true, debugPort = 3075)
        assertFalse("-b absent quand batchMode=false, même en debug", args.contains("-b"))
    }

    // ── Position de -b dans la liste ──────────────────────────────────────────

    @Test
    fun `-b is inserted at index 1 (before -p) in normal mode`() {
        val args = AblRunState.buildArgList(exe, prog, batchMode = true, forDebug = false, debugPort = 0)
        // Ordre attendu : [exe, -b, -p, file]
        assertEquals(exe, args[0])
        assertEquals("-b", args[1])
        assertEquals("-p", args[2])
        assertEquals(prog, args[3])
    }

    @Test
    fun `-b is inserted at index 1 (before -p) in debug mode`() {
        val args = AblRunState.buildArgList(exe, prog, batchMode = true, forDebug = true, debugPort = 3075)
        // Ordre attendu : [exe, -b, -p, file, -debugReady, 3075]
        assertEquals(exe, args[0])
        assertEquals("-b", args[1])
        assertEquals("-p", args[2])
        assertEquals(prog, args[3])
    }

    // ── Règles sur -debugReady ─────────────────────────────────────────────────

    @Test
    fun `debugPort 0 does not add -debugReady`() {
        val args = AblRunState.buildArgList(exe, prog, batchMode = true, forDebug = false, debugPort = 0)
        assertFalse("-debugReady ne doit pas être présent si debugPort=0", args.contains("-debugReady"))
    }

    @Test
    fun `debugPort positive adds -debugReady with port`() {
        val port = 3075
        val args = AblRunState.buildArgList(exe, prog, batchMode = false, forDebug = true, debugPort = port)
        val idx = args.indexOf("-debugReady")
        assertTrue("-debugReady doit être présent quand debugPort=$port", idx >= 0)
        assertEquals("Le port doit suivre -debugReady", port.toString(), args[idx + 1])
    }

    @Test
    fun `debugReady uses exact port value`() {
        val port = 49152
        val args = AblRunState.buildArgList(exe, prog, batchMode = false, forDebug = true, debugPort = port)
        val idx = args.indexOf("-debugReady")
        assertEquals("Le port exact doit être dans les args", port.toString(), args[idx + 1])
    }

    // ── Règles sur -param ─────────────────────────────────────────────────────

    @Test
    fun `programParam adds -param flag`() {
        val args = AblRunState.buildArgList(exe, prog, batchMode = false, forDebug = false, debugPort = 0, programParam = "foo")
        val idx = args.indexOf("-param")
        assertTrue("-param doit être présent", idx >= 0)
        assertEquals("La valeur doit suivre -param", "foo", args[idx + 1])
    }

    @Test
    fun `blank programParam does not add -param`() {
        val args = AblRunState.buildArgList(exe, prog, batchMode = false, forDebug = false, debugPort = 0, programParam = "")
        assertFalse("-param ne doit pas être présent si vide", args.contains("-param"))
    }

    // ── Structure de base ─────────────────────────────────────────────────────

    @Test
    fun `executable is always first arg`() {
        val args = AblRunState.buildArgList(exe, prog, batchMode = false, forDebug = true, debugPort = 3075)
        assertEquals("L'exécutable doit être en index 0", exe, args[0])
    }

    @Test
    fun `-p and programFile are always present`() {
        val args = AblRunState.buildArgList(exe, prog, batchMode = false, forDebug = false, debugPort = 0)
        val idx = args.indexOf("-p")
        assertTrue("-p doit être présent", idx >= 0)
        assertEquals("Le fichier programme doit suivre -p", prog, args[idx + 1])
    }

    // ── Cas intégration debug complet ─────────────────────────────────────────

    @Test
    fun `full debug invocation has correct args`() {
        val args =
            AblRunState.buildArgList(
                executable = exe,
                programFile = prog,
                // -b présent même en debug (requis pour headless)
                batchMode = true,
                forDebug = true,
                debugPort = 3075,
                programParam = "",
            )
        // exe -b -p prog -debugReady 3075
        assertEquals(exe, args[0])
        assertTrue("-b présent en debug headless", args.contains("-b"))
        assertTrue("-p présent", args.contains("-p"))
        val drIdx = args.indexOf("-debugReady")
        assertTrue("-debugReady présent", drIdx >= 0)
        assertEquals("3075", args[drIdx + 1])
    }

    @Test
    fun `full run invocation has correct args`() {
        val args =
            AblRunState.buildArgList(
                executable = exe,
                programFile = prog,
                batchMode = true,
                forDebug = false,
                debugPort = 0,
                programParam = "param1",
            )
        // exe -b -p prog -param param1
        assertTrue("-b présent", args.contains("-b"))
        assertFalse("-debugReady absent", args.contains("-debugReady"))
        val pIdx = args.indexOf("-param")
        assertTrue("-param présent", pIdx >= 0)
        assertEquals("param1", args[pIdx + 1])
    }
}
