package com.ablls.plugin.project

import com.intellij.openapi.components.service
import com.intellij.openapi.fileEditor.FileEditorManager
import com.intellij.openapi.options.Configurable
import com.intellij.openapi.project.Project
import com.intellij.openapi.vfs.LocalFileSystem
import java.awt.BorderLayout
import java.awt.FlowLayout
import java.awt.GridBagConstraints
import java.awt.GridBagLayout
import java.awt.Insets
import javax.swing.*

/**
 * Panneau Settings → OpenEdge ABL.
 *
 * Affiche la configuration du projet ABL lue depuis openedge-project.json :
 *  - Nom, version, charset
 *  - DLC path et PROPATH
 *  - Bases de données configurées
 *
 * Propose un bouton "Open openedge-project.json" pour éditer directement.
 * Les modifications se font dans le fichier JSON — pas dans ce panneau.
 */
class AblProjectSettingsConfigurable(private val project: Project) : Configurable {

    private var panel: JPanel? = null

    override fun getDisplayName(): String = "OpenEdge ABL"

    override fun createComponent(): JComponent {
        val config = project.service<OpenEdgeProjectService>().config

        val root = JPanel(BorderLayout(8, 8))

        // ── En-tête ───────────────────────────────────────────────────────────
        val header = JLabel("<html><b>OpenEdge ABL Project Configuration</b><br/>" +
            "Edit <code>openedge-project.json</code> in the project root to change settings.</html>")
        root.add(header, BorderLayout.NORTH)

        // ── Tableau de propriétés ─────────────────────────────────────────────
        val props = JPanel(GridBagLayout())
        val gc = GridBagConstraints().apply {
            insets = Insets(2, 4, 2, 4)
            anchor = GridBagConstraints.WEST
        }

        var row = 0
        fun addRow(label: String, value: String) {
            gc.gridx = 0; gc.gridy = row; gc.weightx = 0.0; gc.fill = GridBagConstraints.NONE
            props.add(JLabel("<html><b>$label</b></html>"), gc)
            gc.gridx = 1; gc.weightx = 1.0; gc.fill = GridBagConstraints.HORIZONTAL
            props.add(JLabel(value.ifBlank { "(not set)" }), gc)
            row++
        }

        addRow("Project name:",  config.name)
        addRow("OE version:",    config.version)
        addRow("Charset:",       config.charset)
        addRow("DLC path:",      config.dlcPath ?: "(not set)")
        addRow("Build path:",    config.buildPath)
        addRow("PROPATH:",       config.propath.joinToString(", ").ifBlank { "(empty)" })
        addRow("Databases:",     config.databases.joinToString(", ") { it.logicalName }.ifBlank { "(none)" })

        // Filler
        gc.gridx = 0; gc.gridy = row; gc.gridwidth = 2; gc.weighty = 1.0; gc.fill = GridBagConstraints.BOTH
        props.add(JPanel(), gc)

        root.add(JScrollPane(props), BorderLayout.CENTER)

        // ── Boutons ───────────────────────────────────────────────────────────
        val btnPanel = JPanel(FlowLayout(FlowLayout.LEFT))

        val openBtn = JButton("Open openedge-project.json")
        openBtn.addActionListener {
            val configPath = project.service<OpenEdgeProjectService>().getConfigFilePath()
            if (configPath != null) {
                val vf = LocalFileSystem.getInstance().findFileByPath(configPath)
                if (vf != null) FileEditorManager.getInstance(project).openFile(vf, true)
            } else {
                JOptionPane.showMessageDialog(
                    panel, "openedge-project.json not found in project root.",
                    "ABL Project", JOptionPane.WARNING_MESSAGE
                )
            }
        }
        btnPanel.add(openBtn)

        val reloadBtn = JButton("Reload")
        reloadBtn.addActionListener {
            project.service<OpenEdgeProjectService>().reload()
            JOptionPane.showMessageDialog(panel, "Configuration reloaded.", "ABL Project", JOptionPane.INFORMATION_MESSAGE)
        }
        btnPanel.add(reloadBtn)

        root.add(btnPanel, BorderLayout.SOUTH)

        panel = root
        return root
    }

    override fun isModified(): Boolean = false  // lecture seule — les modifs se font dans le JSON

    override fun apply() { /* no-op */ }

    override fun reset() { /* no-op */ }
}
