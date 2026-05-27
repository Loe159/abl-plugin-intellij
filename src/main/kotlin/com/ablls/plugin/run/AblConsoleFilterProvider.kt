package com.ablls.plugin.run

import com.intellij.execution.filters.ConsoleFilterProvider
import com.intellij.execution.filters.Filter
import com.intellij.execution.filters.HyperlinkInfo
import com.intellij.execution.filters.OpenFileHyperlinkInfo
import com.intellij.openapi.project.Project
import com.intellij.openapi.vfs.LocalFileSystem

/**
 * Transforme les messages d'erreur du runtime Progress en hyperliens cliquables.
 *
 * Formats reconnus :
 *   ** Customer.p (line 42)
 *   ** ERROR Customer.p (line 42, column 10)
 */
class AblConsoleFilterProvider : ConsoleFilterProvider {
    override fun getDefaultFilters(project: Project): Array<Filter> = arrayOf(AblErrorConsoleFilter(project))
}

class AblErrorConsoleFilter(private val project: Project) : Filter {
    // ** <optional words> <file.ext> (line N) ou (line N, col M)
    private val pattern =
        Regex(
            """\*\*\s+(?:\w+\s+)?([^\s(]+\.[a-zA-Z]+)\s+\(line\s+(\d+)""",
            RegexOption.IGNORE_CASE,
        )

    override fun applyFilter(
        line: String,
        entireLength: Int,
    ): Filter.Result? {
        val m = pattern.find(line) ?: return null

        val fileName = m.groupValues[1]
        val lineNum = m.groupValues[2].toIntOrNull()?.minus(1) ?: return null

        val lineStart = entireLength - line.length
        val start = lineStart + m.range.first
        val end = lineStart + m.range.last + 1

        val vFile = resolveFile(fileName) ?: return null
        val info: HyperlinkInfo = OpenFileHyperlinkInfo(project, vFile, lineNum)
        return Filter.Result(start, end, info)
    }

    private fun resolveFile(fileName: String): com.intellij.openapi.vfs.VirtualFile? {
        val lfs = LocalFileSystem.getInstance()
        // Essai absolu
        lfs.findFileByPath(fileName)?.let { return it }
        // Essai relatif au projet
        val basePath = project.basePath ?: return null
        val normalised = fileName.replace('\\', '/')
        lfs.findFileByPath("$basePath/$normalised")?.let { return it }
        // Chercher dans l'arbre du projet
        return lfs.findFileByPath(basePath)
            ?.let { root -> findRecursive(root, normalised.substringAfterLast('/')) }
    }

    private fun findRecursive(
        dir: com.intellij.openapi.vfs.VirtualFile,
        name: String,
    ): com.intellij.openapi.vfs.VirtualFile? {
        for (child in dir.children) {
            if (child.isDirectory) {
                findRecursive(child, name)?.let { return it }
            } else if (child.name.equals(name, ignoreCase = true)) {
                return child
            }
        }
        return null
    }
}
