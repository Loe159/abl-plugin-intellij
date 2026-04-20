package com.ablls.plugin.completion

import com.intellij.openapi.diagnostic.Logger
import org.antlr.v4.runtime.*
import org.prorefactor.core.ABLNodeType
import org.prorefactor.proparse.ABLLexer
import org.prorefactor.proparse.Lexer
import org.prorefactor.proparse.PostLexer
import org.prorefactor.proparse.TokenList
import org.prorefactor.proparse.antlr4.Proparse
import org.prorefactor.proparse.support.IProparseEnvironment
import java.nio.charset.StandardCharsets

/**
 * Determines contextually valid keywords at the cursor position by parsing the
 * truncated source text and capturing expected tokens from ANTLR4's error recovery.
 *
 * The ANTLR4 ATN (Augmented Transition Network) inside Proparse knows exactly which
 * token types are valid at any parser state. When we parse text truncated at the
 * cursor and the parser hits an unexpected EOF, the RecognitionException carries the
 * set of expected token types for that state — precisely the keywords the grammar
 * allows at that position.
 */
object AblContextualCompletion {

    private val LOG = Logger.getInstance(AblContextualCompletion::class.java)

    /**
     * Returns the set of keyword strings valid at [cursorOffset] in [content],
     * or null if context cannot be determined (caller should fall back to all keywords).
     */
    fun getExpectedKeywords(content: String, cursorOffset: Int, session: IProparseEnvironment): Set<String>? {
        val truncated = content.take(cursorOffset.coerceIn(0, content.length))
        return try {
            parseAndCaptureExpected(truncated, session)
        } catch (e: Exception) {
            LOG.debug("AblContextualCompletion failed: ${e.message}")
            null
        }
    }

    private fun parseAndCaptureExpected(truncated: String, session: IProparseEnvironment): Set<String>? {
        val capturer = ExpectedTokensCapturer()
        val bytes = truncated.toByteArray(StandardCharsets.UTF_8)

        val ablLexer = ABLLexer(session, StandardCharsets.UTF_8, bytes, "completion_probe.p", false)
        val lex = Lexer(ablLexer, bytes, "completion_probe.p")
        val postLexer = PostLexer(ablLexer, lex)
        val tokenList = TokenList(postLexer)
        val tokens = CommonTokenStream(tokenList)

        val parser = Proparse(tokens)
        parser.initialize(session, null)
        parser.removeErrorListeners()
        parser.addErrorListener(capturer)
        parser.errorHandler = SilentErrorStrategy()

        try {
            parser.program()
        } catch (_: Exception) {
            // parse errors are expected on truncated input; we only care about captured tokens
        }

        val expectedTypes = capturer.lastExpectedTokens ?: return null
        if (expectedTypes.intervals.isEmpty()) return null

        return buildSet {
            for (interval in expectedTypes.intervals) {
                for (tokenType in interval.a..interval.b) {
                    val nodeType = runCatching { ABLNodeType.getNodeType(tokenType) }.getOrNull()
                        ?: continue
                    if (!nodeType.isKeyword) continue
                    val text = runCatching { nodeType.text }.getOrNull()?.uppercase() ?: continue
                    if (text.isNotBlank()) add(text)
                }
            }
        }.takeIf { it.isNotEmpty() }
    }

    // ─── Error listener that records the last RecognitionException's expected tokens ──

    private class ExpectedTokensCapturer : BaseErrorListener() {
        var lastExpectedTokens: org.antlr.v4.runtime.misc.IntervalSet? = null

        override fun syntaxError(
            recognizer: Recognizer<*, *>?,
            offendingSymbol: Any?,
            line: Int,
            charPositionInLine: Int,
            msg: String?,
            e: RecognitionException?
        ) {
            // Prefer the exception's expected set; fall back to parser.expectedTokens
            val expected = e?.expectedTokens
                ?: (recognizer as? Parser)?.expectedTokens
            if (expected != null && !expected.intervals.isEmpty()) {
                lastExpectedTokens = expected
            }
        }
    }

    // ─── Error strategy that suppresses recovery side-effects ────────────────────

    private class SilentErrorStrategy : DefaultErrorStrategy() {
        override fun recover(recognizer: Parser, e: RecognitionException) {
            // do nothing — we just want to finish parsing without crashing
        }
        override fun recoverInline(recognizer: Parser): Token {
            throw InputMismatchException(recognizer)
        }
        override fun sync(recognizer: Parser) {
            // no sync — let the parser proceed as far as it can
        }
    }
}
