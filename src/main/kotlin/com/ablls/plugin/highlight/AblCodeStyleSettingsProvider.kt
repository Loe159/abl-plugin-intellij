package com.ablls.plugin.highlight

import com.ablls.plugin.language.AblLanguage
import com.intellij.application.options.CodeStyleAbstractConfigurable
import com.intellij.application.options.CodeStyleAbstractPanel
import com.intellij.application.options.TabbedLanguageCodeStylePanel
import com.intellij.psi.codeStyle.CodeStyleConfigurable
import com.intellij.psi.codeStyle.CodeStyleSettings
import com.intellij.psi.codeStyle.CodeStyleSettingsProvider
import com.intellij.psi.codeStyle.CustomCodeStyleSettings
import com.intellij.psi.codeStyle.LanguageCodeStyleSettingsProvider
import com.intellij.psi.codeStyle.CommonCodeStyleSettings

/**
 * Fournisseur de paramètres de style de code ABL.
 *
 * Expose un panneau dans Settings → Editor → Code Style → OpenEdge ABL
 * avec les onglets standard IntelliJ (Tabs and Indents, Spaces, Wrapping).
 *
 * Deux classes complémentaires :
 *   - [AblCodeStyleSettingsProvider]         → enregistre le panneau dans Settings
 *   - [AblLanguageCodeStyleSettingsProvider] → définit les options disponibles
 */
class AblCodeStyleSettingsProvider : CodeStyleSettingsProvider() {

    override fun getLanguage() = AblLanguage

    override fun createConfigurable(
        settings: CodeStyleSettings,
        modelSettings: CodeStyleSettings
    ): CodeStyleConfigurable =
        object : CodeStyleAbstractConfigurable(settings, modelSettings, "OpenEdge ABL") {
            override fun createPanel(settings: CodeStyleSettings): CodeStyleAbstractPanel =
                AblCodeStyleMainPanel(currentSettings, settings)
        }

    override fun createCustomSettings(settings: CodeStyleSettings): CustomCodeStyleSettings? = null
}

/**
 * Panel principal Code Style ABL — hérite du TabbedPanel standard IntelliJ.
 * Affiche les onglets Tabs and Indents + Spaces hérités de CommonCodeStyleSettings.
 */
private class AblCodeStyleMainPanel(
    currentSettings: CodeStyleSettings,
    settings: CodeStyleSettings
) : TabbedLanguageCodeStylePanel(AblLanguage, currentSettings, settings) {

    override fun initTabs(settings: CodeStyleSettings) {
        addIndentOptionsTab(settings)
        addSpacesTab(settings)
        addWrappingAndBracesTab(settings)
    }
}

/**
 * Provider de paramètres de langage ABL pour le code style.
 *
 * Déclare les options disponibles et fournit un extrait de code de prévisualisation.
 */
class AblLanguageCodeStyleSettingsProvider : LanguageCodeStyleSettingsProvider() {

    override fun getLanguage() = AblLanguage

    override fun getCodeSample(settingsType: SettingsType): String = """
        CLASS com.example.MyClass:

            DEFINE VARIABLE iCount AS INTEGER NO-UNDO.
            DEFINE VARIABLE cName  AS CHARACTER NO-UNDO.

            METHOD PUBLIC VOID doSomething(INPUT iMax AS INTEGER):
                DEFINE VARIABLE i AS INTEGER NO-UNDO.
                DO i = 1 TO iMax:
                    IF i > 10 THEN DO:
                        cName = "big".
                    END.
                    ELSE DO:
                        cName = "small".
                    END.
                END.
            END METHOD.

        END CLASS.
    """.trimIndent()

    override fun customizeSettings(
        consumer: com.intellij.psi.codeStyle.CodeStyleSettingsCustomizable,
        settingsType: SettingsType
    ) {
        when (settingsType) {
            SettingsType.INDENT_SETTINGS -> {
                consumer.showStandardOptions(
                    "USE_TAB_CHARACTER",
                    "INDENT_SIZE",
                    "CONTINUATION_INDENT_SIZE",
                    "TAB_SIZE"
                )
            }
            SettingsType.SPACING_SETTINGS -> {
                consumer.showStandardOptions(
                    "SPACE_AFTER_COMMA",
                    "SPACE_BEFORE_COMMA",
                    "SPACE_AROUND_ASSIGNMENT_OPERATORS",
                    "SPACE_AROUND_EQUALITY_OPERATORS",
                    "SPACE_AROUND_RELATIONAL_OPERATORS",
                    "SPACE_AROUND_ADDITIVE_OPERATORS",
                    "SPACE_AROUND_MULTIPLICATIVE_OPERATORS"
                )
            }
            SettingsType.WRAPPING_AND_BRACES_SETTINGS -> {
                consumer.showStandardOptions("RIGHT_MARGIN")
            }
            else -> {}
        }
    }

    @Suppress("OVERRIDE_DEPRECATION")
    override fun getDefaultCommonSettings(): CommonCodeStyleSettings =
        CommonCodeStyleSettings(AblLanguage).apply {
            val opts = initIndentOptions()
            opts.INDENT_SIZE             = 4
            opts.TAB_SIZE                = 4
            opts.CONTINUATION_INDENT_SIZE = 8
            opts.USE_TAB_CHARACTER       = false
        }
}
