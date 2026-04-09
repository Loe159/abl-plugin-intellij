package com.ablls.plugin.highlight

import com.ablls.plugin.language.AblIcons
import com.intellij.openapi.editor.colors.TextAttributesKey
import com.intellij.openapi.fileTypes.SyntaxHighlighter
import com.intellij.openapi.options.colors.*
import javax.swing.Icon

/**
 * Page de configuration des couleurs dans
 * Settings → Editor → Color Scheme → ABL
 *
 * Chaque [AttributesDescriptor] correspond à une ligne configurable
 * dans la page de paramètres.
 */
class AblColorSettingsPage : ColorSettingsPage {

    private val DESCRIPTORS = arrayOf(
        AttributesDescriptor("Keyword",            AblSyntaxHighlighter.KEYWORD),
        AttributesDescriptor("Keyword//Flow control (IF, DO, FOR, END...)",
                                                   AblSyntaxHighlighter.KEYWORD_FLOW),
        AttributesDescriptor("Keyword//Definition (DEFINE, CLASS, METHOD...)",
                                                   AblSyntaxHighlighter.KEYWORD_DEF),
        AttributesDescriptor("Keyword//Database (FIND, FOR EACH, WHERE...)",
                                                   AblSyntaxHighlighter.KEYWORD_DB),
        AttributesDescriptor("Keyword//Access modifier (PUBLIC, PRIVATE, STATIC...)",
                                                   AblSyntaxHighlighter.KEYWORD_MOD),
        AttributesDescriptor("Keyword//Primitive type (CHARACTER, INTEGER...)",
                                                   AblSyntaxHighlighter.KEYWORD_TYPE),
        AttributesDescriptor("String",             AblSyntaxHighlighter.STRING),
        AttributesDescriptor("Number",             AblSyntaxHighlighter.NUMBER),
        AttributesDescriptor("Logical literal (TRUE/FALSE/YES/NO/?)",
                                                   AblSyntaxHighlighter.LOGICAL_LITERAL),
        AttributesDescriptor("Comment//Block comment",
                                                   AblSyntaxHighlighter.BLOCK_COMMENT),
        AttributesDescriptor("Comment//Line comment",
                                                   AblSyntaxHighlighter.LINE_COMMENT),
        AttributesDescriptor("Preprocessor (&DEFINE, {include})",
                                                   AblSyntaxHighlighter.PREPROCESSOR),
        AttributesDescriptor("Operator",           AblSyntaxHighlighter.OPERATOR),
        AttributesDescriptor("Punctuation//Dot (.)",
                                                   AblSyntaxHighlighter.DOT),
        AttributesDescriptor("Punctuation//Colon (:)",
                                                   AblSyntaxHighlighter.COLON),
        AttributesDescriptor("Punctuation//Comma (,)",
                                                   AblSyntaxHighlighter.COMMA),
        AttributesDescriptor("Punctuation//Parentheses",
                                                   AblSyntaxHighlighter.PARENTHESES),
        AttributesDescriptor("Identifier",         AblSyntaxHighlighter.IDENTIFIER),
        AttributesDescriptor("Annotation (@...)",  AblSyntaxHighlighter.ANNOTATION),
        AttributesDescriptor("Bad character",      AblSyntaxHighlighter.BAD_CHARACTER),
    )

    // Tags personnalisés pour le texte d'exemple (optionnel)
    // Permet de colorier les éléments de l'exemple de façon indépendante
    private val ADDITIONAL_TAGS = mapOf(
        "kw"   to AblSyntaxHighlighter.KEYWORD,
        "kdef" to AblSyntaxHighlighter.KEYWORD_DEF,
        "kflow" to AblSyntaxHighlighter.KEYWORD_FLOW,
        "ktype" to AblSyntaxHighlighter.KEYWORD_TYPE,
        "kmod" to AblSyntaxHighlighter.KEYWORD_MOD,
        "kdb"  to AblSyntaxHighlighter.KEYWORD_DB,
        "str"  to AblSyntaxHighlighter.STRING,
        "num"  to AblSyntaxHighlighter.NUMBER,
        "log"  to AblSyntaxHighlighter.LOGICAL_LITERAL,
        "cmt"  to AblSyntaxHighlighter.BLOCK_COMMENT,
        "pp"   to AblSyntaxHighlighter.PREPROCESSOR,
        "ann"  to AblSyntaxHighlighter.ANNOTATION,
    )

    override fun getIcon(): Icon = AblIcons.FILE
    override fun getHighlighter(): SyntaxHighlighter = AblSyntaxHighlighter()
    override fun getDisplayName(): String = "ABL (Progress OpenEdge)"
    override fun getAttributeDescriptors(): Array<AttributesDescriptor> = DESCRIPTORS
    override fun getColorDescriptors(): Array<ColorDescriptor> = ColorDescriptor.EMPTY_ARRAY
    override fun getAdditionalHighlightingTagToDescriptorMap() = ADDITIONAL_TAGS

    override fun getDemoText(): String = """
<pp>&GLOBAL-DEFINE MyFlag TRUE</pp>
<cmt>/* Exemple de code ABL — coloration syntaxique */</cmt>
<kw>USING</kw> Progress.Lang.*.

<kdef>CLASS</kdef> com.myapp.CustomerService
  <kmod>IMPLEMENTS</kmod> Progress.Lang.Disposable:

  <cmt>/* Variable de classe */</cmt>
  <kdef>DEFINE</kdef> <kmod>PRIVATE</kmod> <kdef>VARIABLE</kdef> cHost <kw>AS</kw> <ktype>CHARACTER</ktype> <kw>NO-UNDO</kw>
    <kw>INITIAL</kw> <str>"localhost"</str>.

  <kdef>DEFINE</kdef> <kmod>PUBLIC</kmod> <kdef>PROPERTY</kdef> CustomerCount <kw>AS</kw> <ktype>INTEGER</ktype>
    <kw>NO-UNDO</kw> <kw>GET</kw>. <kw>SET</kw>.

  <kdef>DEFINE</kdef> <kdef>TEMP-TABLE</kdef> ttResult <kw>NO-UNDO</kw>
    <kdef>FIELD</kdef> CustId   <kw>AS</kw> <ktype>INTEGER</ktype>
    <kdef>FIELD</kdef> CustName <kw>AS</kw> <ktype>CHARACTER</ktype> <kw>FORMAT</kw> <str>"x(30)"</str>
    <kdef>FIELD</kdef> Balance  <kw>AS</kw> <ktype>DECIMAL</ktype> <kw>INITIAL</kw> <num>0</num>
    <kdef>INDEX</kdef> idx <kw>IS</kw> <kw>PRIMARY</kw> CustId.

  <kdef>METHOD</kdef> <kmod>PUBLIC</kmod> <ktype>VOID</ktype> LoadData(<kw>INPUT</kw> pMin <kw>AS</kw> <ktype>DECIMAL</ktype>):
    <kdef>DEFINE</kdef> <kdef>VARIABLE</kdef> dResult <kw>AS</kw> <ktype>DECIMAL</ktype> <kw>NO-UNDO</kw>.

    <kflow>FOR</kflow> <kdb>EACH</kdb> ttResult <kdb>WHERE</kdb> ttResult.Balance > pMin
        <kdb>NO-LOCK</kdb> <kflow>BY</kflow> ttResult.CustName:

      <kflow>IF</kflow> ttResult.Balance > <num>1000</num> <kflow>THEN</kflow>
        dResult = ttResult.Balance * <num>1.10</num>.
    <kflow>END</kflow>.

    <kflow>CATCH</kflow> e <kw>AS</kw> Progress.Lang.AppError:
      <kw>MESSAGE</kw> <str>"Error: "</str> e:Message <kw>VIEW-AS</kw> <kw>ALERT-BOX</kw>.
    <kflow>END CATCH</kflow>.
  <kflow>END</kflow> <kdef>METHOD</kdef>.

<kflow>END</kflow> <kdef>CLASS</kdef>.
""".trimIndent()
}
