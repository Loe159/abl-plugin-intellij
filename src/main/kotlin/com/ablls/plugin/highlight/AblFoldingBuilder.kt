package com.ablls.plugin.highlight

import com.ablls.plugin.parser.AblTokenTypes
import com.intellij.lang.ASTNode
import com.intellij.lang.BracePair
import com.intellij.lang.Commenter
import com.intellij.lang.PairedBraceMatcher
import com.intellij.lang.folding.FoldingBuilderEx
import com.intellij.lang.folding.FoldingDescriptor
import com.intellij.openapi.editor.Document
import com.intellij.openapi.util.TextRange
import com.intellij.psi.PsiElement
import com.intellij.psi.PsiFile
import com.intellij.psi.tree.IElementType

// ─── AblFoldingBuilder ───────────────────────────────────────────────────────

/**
 * Code folding for ABL.
 *
 * Folds:
 *   - PROCEDURE name: ... END [PROCEDURE].
 *   - FUNCTION name ...: ... END [FUNCTION].
 *   - CLASS name: ... END [CLASS].
 *   - INTERFACE name: ... END [INTERFACE].
 *   - METHOD name ...: ... END [METHOD].
 *   - CONSTRUCTOR ...: ... END [CONSTRUCTOR].
 *   - DESTRUCTOR ...: ... END [DESTRUCTOR].
 *   - DO: ... END. / DO WHILE ...: ... END. / DO x = TO:  ... END.
 *   - FOR EACH/FIRST/LAST ...: ... END.
 *   - REPEAT: ... END.
 *   - CASE expr: ... END CASE.
 *   - TRY: ... END. / TRY: ... CATCH ...: ... END CATCH. / ... FINALLY: ... END FINALLY.
 *   - CATCH ...: ... END [CATCH].
 *   - FINALLY: ... END [FINALLY].
 *   - /* multi-line block comments */
 *
 * Strategy: flat PSI → collect all leaf tokens, then use a stack to match
 * block-opening keywords (those followed by ':' before any 'END') with 'END'.
 */
class AblFoldingBuilder : FoldingBuilderEx() {

    private data class Tok(val node: ASTNode, val upper: String, val start: Int, val end: Int)
    private data class BlockStart(val openerNode: ASTNode, val startOffset: Int, val placeholder: String, val keyword: String = "")

    override fun buildFoldRegions(root: PsiElement, document: Document, quick: Boolean): Array<FoldingDescriptor> {
        val descriptors = mutableListOf<FoldingDescriptor>()
        val tokens = collectLeaves(root.node)

        for (tok in tokens) {
            if (tok.node.elementType == AblTokenTypes.BLOCK_COMMENT && tok.node.text.contains('\n')) {
                descriptors.add(FoldingDescriptor(tok.node, tok.node.textRange, null, "/* ... */"))
            }
        }

        detectBlocks(tokens, descriptors)
        return descriptors.toTypedArray()
    }

    private fun collectLeaves(root: ASTNode): List<Tok> {
        val result = mutableListOf<Tok>()
        fun walk(n: ASTNode) {
            if (n.firstChildNode == null) {
                if (n.elementType != AblTokenTypes.WHITE_SPACE) {
                    result.add(Tok(n, n.text.uppercase(), n.startOffset, n.startOffset + n.textLength))
                }
            } else {
                var c = n.firstChildNode
                while (c != null) { walk(c); c = c.treeNext }
            }
        }
        walk(root)
        return result
    }

    private fun detectBlocks(tokens: List<Tok>, descriptors: MutableList<FoldingDescriptor>) {
        val stack = ArrayDeque<BlockStart>()
        var i = 0
        while (i < tokens.size) {
            val tok = tokens[i]
            when (tok.upper) {
                "DO", "REPEAT" -> {
                    if (hasBlockColon(tokens, i)) {
                        stack.addLast(BlockStart(tok.node, tok.start, "${tok.upper}: ...", tok.upper))
                    }
                }
                "FOR" -> {
                    val next = tokens.getOrNull(i + 1)?.upper
                    if (next in setOf("EACH", "FIRST", "LAST") && hasBlockColon(tokens, i)) {
                        stack.addLast(BlockStart(tok.node, tok.start, "FOR $next: ...", "FOR"))
                    }
                }
                "PROCEDURE", "PROC" -> {
                    if (hasBlockColon(tokens, i)) {
                        val name = nameAfter(tokens, i)
                        stack.addLast(BlockStart(tok.node, tok.start, "PROCEDURE $name...", "PROCEDURE"))
                    }
                }
                "FUNCTION" -> {
                    if (hasBlockColon(tokens, i)) {
                        val name = nameAfter(tokens, i)
                        stack.addLast(BlockStart(tok.node, tok.start, "FUNCTION $name...", "FUNCTION"))
                    }
                }
                "CLASS" -> {
                    if (hasBlockColon(tokens, i)) {
                        val name = nameAfter(tokens, i)
                        stack.addLast(BlockStart(tok.node, tok.start, "CLASS $name...", "CLASS"))
                    }
                }
                "INTERFACE" -> {
                    if (hasBlockColon(tokens, i)) {
                        val name = nameAfter(tokens, i)
                        stack.addLast(BlockStart(tok.node, tok.start, "INTERFACE $name...", "INTERFACE"))
                    }
                }
                "METHOD" -> {
                    if (hasBlockColon(tokens, i)) {
                        val name = nameAfter(tokens, i)
                        stack.addLast(BlockStart(tok.node, tok.start, "METHOD $name...", "METHOD"))
                    }
                }
                "CONSTRUCTOR" -> {
                    if (hasBlockColon(tokens, i)) {
                        stack.addLast(BlockStart(tok.node, tok.start, "CONSTRUCTOR ...", "CONSTRUCTOR"))
                    }
                }
                "DESTRUCTOR" -> {
                    if (hasBlockColon(tokens, i)) {
                        stack.addLast(BlockStart(tok.node, tok.start, "DESTRUCTOR ...", "DESTRUCTOR"))
                    }
                }
                "CASE" -> {
                    if (hasBlockColon(tokens, i)) {
                        stack.addLast(BlockStart(tok.node, tok.start, "CASE ...", "CASE"))
                    }
                }
                "TRY" -> {
                    if (hasBlockColon(tokens, i)) {
                        stack.addLast(BlockStart(tok.node, tok.start, "TRY: ...", "TRY"))
                    }
                }
                "CATCH" -> {
                    if (hasBlockColon(tokens, i)) {
                        stack.addLast(BlockStart(tok.node, tok.start, "CATCH ...", "CATCH"))
                    }
                }
                "FINALLY" -> {
                    if (hasBlockColon(tokens, i)) {
                        stack.addLast(BlockStart(tok.node, tok.start, "FINALLY: ...", "FINALLY"))
                    }
                }
                "END" -> {
                    if (stack.isNotEmpty()) {
                        val block = stack.removeLast()
                        var endPos = tok.end
                        var j = i + 1
                        // optional qualifier: END PROCEDURE / END CLASS / etc.
                        if (j < tokens.size && tokens[j].upper in END_QUALIFIERS) {
                            endPos = tokens[j].end
                            j++
                        }
                        // trailing dot
                        if (j < tokens.size && tokens[j].upper == ".") {
                            endPos = tokens[j].end
                            i = j
                        }
                        if (endPos > block.startOffset) {
                            descriptors.add(
                                FoldingDescriptor(block.openerNode, TextRange(block.startOffset, endPos), null, block.placeholder)
                            )
                        }
                        // When CATCH or FINALLY closes, also close a pending TRY if no more
                        // CATCH/FINALLY follows — TRY has no dedicated END keyword of its own.
                        if (block.keyword in setOf("CATCH", "FINALLY") && stack.isNotEmpty() && stack.last().keyword == "TRY") {
                            val lookahead = tokens.getOrNull(i + 1)?.upper
                            if (lookahead != "CATCH" && lookahead != "FINALLY") {
                                val tryBlock = stack.removeLast()
                                if (endPos > tryBlock.startOffset) {
                                    descriptors.add(
                                        FoldingDescriptor(tryBlock.openerNode, TextRange(tryBlock.startOffset, endPos), null, tryBlock.placeholder)
                                    )
                                }
                            }
                        }
                    }
                }
            }
            i++
        }
    }

    // Returns true if there is a ':' (outside parentheses) before the next END keyword,
    // scanning up to 50 tokens ahead. This identifies block-opening statements.
    private fun hasBlockColon(tokens: List<Tok>, startIdx: Int): Boolean {
        var depth = 0
        val limit = minOf(tokens.size, startIdx + 50)
        for (i in startIdx + 1 until limit) {
            when (tokens[i].upper) {
                "(" -> depth++
                ")" -> if (depth > 0) depth--
                ":" -> if (depth == 0) return true
                "END" -> if (depth == 0) return false
            }
        }
        return false
    }

    private fun nameAfter(tokens: List<Tok>, startIdx: Int): String {
        val text = tokens.getOrNull(startIdx + 1)?.upper ?: return ""
        return if (text.isNotEmpty() && text[0].isLetter()) "$text " else ""
    }

    override fun getPlaceholderText(node: ASTNode): String? = when (node.elementType) {
        AblTokenTypes.BLOCK_COMMENT -> "/* ... */"
        else -> "..."
    }

    override fun isCollapsedByDefault(node: ASTNode): Boolean = false

    companion object {
        private val END_QUALIFIERS = setOf(
            "PROCEDURE", "PROC", "FUNCTION", "CLASS", "INTERFACE",
            "METHOD", "CONSTRUCTOR", "DESTRUCTOR", "CATCH", "FINALLY", "CASE"
        )
    }
}

// ─── AblCommenter ────────────────────────────────────────────────────────────

class AblCommenter : Commenter {
    override fun getLineCommentPrefix(): String = "// "
    override fun getBlockCommentPrefix(): String = "/* "
    override fun getBlockCommentSuffix(): String = " */"
    override fun getCommentedBlockCommentPrefix(): String? = null
    override fun getCommentedBlockCommentSuffix(): String? = null
}

// ─── AblBracketMatcher ───────────────────────────────────────────────────────

class AblBracketMatcher : PairedBraceMatcher {

    private val PAIRS = arrayOf(
        BracePair(AblTokenTypes.LPAREN, AblTokenTypes.RPAREN, false)
    )

    override fun getPairs(): Array<BracePair> = PAIRS
    override fun isPairedBracesAllowedBeforeType(lbraceType: IElementType, contextType: IElementType?): Boolean = true
    override fun getCodeConstructStart(file: PsiFile, openingBracketOffset: Int): Int = openingBracketOffset
}
