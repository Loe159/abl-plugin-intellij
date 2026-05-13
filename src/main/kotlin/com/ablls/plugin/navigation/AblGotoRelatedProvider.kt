package com.ablls.plugin.navigation

import com.ablls.plugin.language.AblLanguage
import com.intellij.navigation.GotoRelatedItem
import com.intellij.navigation.GotoRelatedProvider
import com.intellij.openapi.actionSystem.CommonDataKeys
import com.intellij.openapi.actionSystem.DataContext
import com.intellij.openapi.project.Project
import com.intellij.openapi.vfs.LocalFileSystem
import com.intellij.openapi.vfs.VirtualFile
import com.intellij.psi.PsiFile
import com.intellij.psi.PsiManager

/**
 * Go to Related Symbol (Ctrl+Alt+Home) pour ABL.
 *
 * Navigation entre fichiers ABL liés :
 *  - D'un fichier `.cls` → vers le fichier `.i` d'interface (même nom de base)
 *  - D'un fichier `.i`   → vers le fichier `.cls` implémentation (même nom de base)
 *  - D'un fichier `.p`   → vers les fichiers `.i` portant le même nom de base
 *
 * Recherche dans le dossier du fichier courant et dans le projet entier.
 */
class AblGotoRelatedProvider : GotoRelatedProvider() {

    override fun getItems(dataContext: DataContext): List<GotoRelatedItem> {
        val psiFile = dataContext.getData(CommonDataKeys.PSI_FILE) ?: return emptyList()
        if (psiFile.language != AblLanguage) return emptyList()

        val vf = psiFile.virtualFile ?: return emptyList()
        val name = vf.nameWithoutExtension
        val ext  = vf.extension?.lowercase() ?: return emptyList()

        val project = psiFile.project
        val result  = mutableListOf<GotoRelatedItem>()

        // Extensions candidates selon le type de fichier courant
        val candidates = when (ext) {
            "cls" -> listOf("$name.i", "$name.p")
            "i"   -> listOf("$name.cls", "$name.p")
            "p"   -> listOf("$name.cls", "$name.i")
            else  -> return emptyList()
        }

        // Chercher dans le dossier du fichier courant
        val parent = vf.parent
        for (candidate in candidates) {
            val related = parent?.findChild(candidate) ?: continue
            val relPsi  = PsiManager.getInstance(project).findFile(related) ?: continue
            result.add(GotoRelatedItem(relPsi, "Related ABL file"))
        }

        // Si rien trouvé localement, chercher dans le projet
        if (result.isEmpty()) {
            val basePath = project.basePath ?: return result
            for (candidate in candidates) {
                val found = findInProject(basePath, candidate, project)
                if (found != null) result.add(GotoRelatedItem(found, "Related ABL file"))
            }
        }

        return result
    }

    private fun findInProject(basePath: String, fileName: String, project: Project): PsiFile? {
        val baseDir = LocalFileSystem.getInstance().findFileByPath(basePath) ?: return null
        return findRecursive(baseDir, fileName, project, depth = 0)
    }

    private fun findRecursive(dir: VirtualFile, fileName: String, project: Project, depth: Int): PsiFile? {
        if (depth > 5) return null
        for (child in dir.children ?: emptyArray()) {
            if (child.isDirectory) {
                val found = findRecursive(child, fileName, project, depth + 1)
                if (found != null) return found
            } else if (child.name.equals(fileName, ignoreCase = true)) {
                return PsiManager.getInstance(project).findFile(child)
            }
        }
        return null
    }
}
