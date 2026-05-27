package com.ablls.plugin.project

import com.ablls.plugin.language.AblIcons
import com.intellij.openapi.projectRoots.AdditionalDataConfigurable
import com.intellij.openapi.projectRoots.Sdk
import com.intellij.openapi.projectRoots.SdkAdditionalData
import com.intellij.openapi.projectRoots.SdkModel
import com.intellij.openapi.projectRoots.SdkModificator
import com.intellij.openapi.projectRoots.SdkType
import org.jdom.Element
import java.io.File

/**
 * Type de SDK "OpenEdge ABL" — apparaît dans File → Project Structure → SDKs.
 *
 * L'utilisateur sélectionne le répertoire d'installation OpenEdge ($DLC).
 * Le plugin valide la présence du binaire client OE et extrait la version.
 */
class OpenEdgeSdkType : SdkType("OpenEdge ABL") {
    companion object {
        const val ID = "OpenEdge ABL"

        @JvmStatic
        fun getInstance(): OpenEdgeSdkType = SdkType.findInstance(OpenEdgeSdkType::class.java)

        private val OE_BINARIES =
            listOf(
                // Windows, client caractère (debug)
                "bin/_progres.exe",
                // Windows, client GUI
                "bin/prowin.exe",
                // Windows, client GUI 32-bit
                "bin/prowin32.exe",
                // Unix/Linux/macOS
                "bin/_progres",
                // Unix, client batch
                "bin/mpro",
            )
    }

    // ── Validation ────────────────────────────────────────────────────────────

    override fun isValidSdkHome(path: String): Boolean {
        val home = File(path)
        return home.isDirectory && OE_BINARIES.any { File(home, it).exists() }
    }

    // ── Version ───────────────────────────────────────────────────────────────

    override fun getVersionString(sdkHome: String): String? {
        return parseVersionFile(sdkHome) ?: detectVersionFromBinary(sdkHome)
    }

    /**
     * Lit `$DLC/version` — fichier texte présent dans toutes les installations OE.
     * Format : "OpenEdge Release 12.7 as of Thu Oct  5 17:18:45 EDT 2023"
     */
    private fun parseVersionFile(sdkHome: String): String? {
        val versionFile = File(sdkHome, "version")
        if (!versionFile.exists()) return null
        return versionFile.readLines().firstOrNull()
            ?.let { Regex("""Release\s+([\d.]+)""").find(it)?.groupValues?.get(1) }
            ?.let { "OpenEdge $it" }
    }

    /**
     * Fallback : shell out `_progres -version` si le fichier version est absent.
     * Lent — utilisé seulement en dernier recours.
     */
    private fun detectVersionFromBinary(sdkHome: String): String? {
        val binary =
            OE_BINARIES
                .map { File(sdkHome, it) }
                .firstOrNull { it.exists() }
                ?: return null
        return try {
            val output =
                ProcessBuilder(binary.absolutePath, "-version")
                    .redirectErrorStream(true)
                    .start()
                    .inputStream
                    .bufferedReader()
                    .readText()
            Regex("""[\d]+\.[\d]+""").find(output)?.value?.let { "OpenEdge $it" }
        } catch (_: Exception) {
            null
        }
    }

    // ── Suggestions ───────────────────────────────────────────────────────────

    override fun suggestHomePath(): String? {
        val isWindows = System.getProperty("os.name").lowercase().contains("win")
        val candidates =
            if (isWindows) {
                listOf(
                    "C:\\Progress\\OpenEdge",
                    "C:\\OpenEdge",
                    System.getenv("DLC") ?: "",
                )
            } else {
                listOf(
                    "/usr/dlc",
                    "/opt/openedge",
                    System.getenv("DLC") ?: "",
                )
            }
        return candidates.firstOrNull { it.isNotBlank() && File(it).exists() }
            ?: if (isWindows) "C:\\Progress\\OpenEdge" else "/usr/dlc"
    }

    override fun suggestSdkName(
        currentName: String?,
        sdkHome: String,
    ): String {
        val version = getVersionString(sdkHome) ?: "OpenEdge"
        return version
    }

    // ── Présentation ──────────────────────────────────────────────────────────

    override fun getPresentableName(): String = "OpenEdge ABL"

    override fun getIcon() = AblIcons.FILE

    // ── Données additionnelles (non utilisées en v1) ──────────────────────────

    override fun createAdditionalDataConfigurable(
        sdkModel: SdkModel,
        sdkModificator: SdkModificator,
    ): AdditionalDataConfigurable? = null

    override fun saveAdditionalData(
        additionalData: SdkAdditionalData,
        additional: Element,
    ) {}

    // ── Racines (pas de sources/classes OE à indexer) ─────────────────────────

    override fun setupSdkPaths(sdk: Sdk) {}

    override fun getDefaultDocumentationUrl(sdk: Sdk): String = "https://docs.progress.com/"
}

// ── Utilitaire : résoudre le DLC depuis le SDK projet ────────────────────────

/**
 * Retourne le homePath du SDK OpenEdge configuré pour le projet, ou null.
 * Utilisé par [AblRunState.resolveDlc] comme source de DLC de plus haute priorité.
 */
fun resolveOpenEdgeSdkHome(project: com.intellij.openapi.project.Project): String? {
    val sdk =
        com.intellij.openapi.roots.ProjectRootManager.getInstance(project).projectSdk
            ?: return null
    if (sdk.sdkType !is OpenEdgeSdkType) return null
    return sdk.homePath?.takeIf { it.isNotBlank() }
}
