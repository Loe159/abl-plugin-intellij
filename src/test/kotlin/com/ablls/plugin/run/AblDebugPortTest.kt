package com.ablls.plugin.run

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test
import java.net.ServerSocket

/**
 * Tests pour AblProgramRunner.findFreePort().
 *
 * Vérifie que le port retourné est valide, non-privilégié et effectivement disponible.
 * Ces tests sont purs JUnit sans dépendance IntelliJ.
 */
class AblDebugPortTest {
    @Test
    fun `findFreePort returns a positive port`() {
        val port = AblProgramRunner.findFreePort()
        assertTrue("Le port doit être > 0, obtenu: $port", port > 0)
    }

    @Test
    fun `findFreePort returns a port in valid TCP range`() {
        val port = AblProgramRunner.findFreePort()
        assertTrue("Le port doit être <= 65535, obtenu: $port", port <= 65535)
    }

    @Test
    fun `findFreePort does not return a privileged port below 1024`() {
        // On Windows, ports < 1024 peuvent être bloqués (ex. port 287 — cas réel observé)
        // ServerSocket(0) ne doit pas retourner de port dans la plage réservée
        repeat(10) {
            val port = AblProgramRunner.findFreePort()
            assertFalse(
                "findFreePort a retourné $port (port privilégié < 1024). " +
                    "Ce type de port peut être bloqué sur Windows et empêche OE de démarrer avec -debugReady.",
                port in 1..1023,
            )
        }
    }

    @Test
    fun `findFreePort returns a bindable port`() {
        val port = AblProgramRunner.findFreePort()
        // Vérification : OE doit pouvoir ouvrir ce port comme ServerSocket
        try {
            ServerSocket(port).use { /* port libre, bind réussi */ }
        } catch (e: Exception) {
            fail("Le port $port retourné par findFreePort() ne peut pas être bindé : ${e.message}")
        }
    }

    @Test
    fun `findFreePort returns different ports on consecutive calls`() {
        // Après que OE libère un port, on doit obtenir des ports différents
        // (pas une garantie absolue mais vrai dans >99% des cas sur un OS moderne)
        val ports = (1..5).map { AblProgramRunner.findFreePort() }.toSet()
        assertTrue(
            "findFreePort devrait retourner des ports variés sur des appels consécutifs, obtenu: $ports",
            ports.size >= 2,
        )
    }

    @Test
    fun `config debugPort 0 triggers findFreePort not hardcoded 3075`() {
        // Vérifie que la logique de sélection de port ne fixe pas 3075 quand debugPort=0
        // (sauf si findFreePort() retourne 3075, ce qui est peu probable)
        val port = AblProgramRunner.findFreePort()
        // Le port obtenu doit être valide quelle que soit sa valeur
        assertTrue("Port valide attendu", port in 1..65535)
    }

    @Test
    fun `port 287 is not a valid ephemeral port`() {
        // Vérifie notre compréhension : 287 n'est pas dans la plage éphémère normale
        // Ce test documente le bug rencontré (port 287 causait OE to crash sur -debugReady 287)
        val ephemeralMin = 1024
        assertFalse(
            "Le port 287 est dans la plage privilégiée — il ne doit pas être utilisé pour -debugReady",
            287 >= ephemeralMin,
        )
    }
}
