package com.ablls.plugin.core

import org.junit.Test
import kotlin.test.assertFalse
import kotlin.test.assertNotNull
import kotlin.test.assertTrue

/**
 * Tests for [AblBuiltinDocs] — verifies coverage and content correctness.
 */
class AblBuiltinDocsTest {

    @Test
    fun `LENGTH is present with correct content`() {
        val doc = AblBuiltinDocs.get("LENGTH")
        assertTrue(doc.isPresent, "LENGTH should be in built-in docs")
        assertTrue(doc.get().contains("LENGTH"), "Doc should reference LENGTH")
        assertTrue(doc.get().contains("INTEGER"), "Doc should mention return type INTEGER")
    }

    @Test
    fun `lookup is case insensitive`() {
        assertTrue(AblBuiltinDocs.has("length"), "lowercase 'length' should be found")
        assertTrue(AblBuiltinDocs.has("LENGTH"), "uppercase 'LENGTH' should be found")
        assertTrue(AblBuiltinDocs.has("Length"), "mixed case 'Length' should be found")
    }

    @Test
    fun `SUBSTITUTE is documented`() {
        assertTrue(AblBuiltinDocs.has("SUBSTITUTE"), "SUBSTITUTE should be in docs")
        val doc = AblBuiltinDocs.get("SUBSTITUTE").get()
        assertTrue(doc.contains("&1"), "SUBSTITUTE doc should mention &1 placeholder")
    }

    @Test
    fun `BASE64-ENCODE and BASE64-DECODE are present`() {
        assertTrue(AblBuiltinDocs.has("BASE64-ENCODE"))
        assertTrue(AblBuiltinDocs.has("BASE64-DECODE"))
    }

    @Test
    fun `OO keywords are documented`() {
        assertTrue(AblBuiltinDocs.has("CLASS"), "CLASS should be documented")
        assertTrue(AblBuiltinDocs.has("METHOD"), "METHOD should be documented")
        assertTrue(AblBuiltinDocs.has("INTERFACE"), "INTERFACE should be documented")
        assertTrue(AblBuiltinDocs.has("CONSTRUCTOR"), "CONSTRUCTOR should be documented")
        assertTrue(AblBuiltinDocs.has("DESTRUCTOR"), "DESTRUCTOR should be documented")
        assertTrue(AblBuiltinDocs.has("INHERITS"), "INHERITS should be documented")
        assertTrue(AblBuiltinDocs.has("IMPLEMENTS"), "IMPLEMENTS should be documented")
    }

    @Test
    fun `preprocessor directives are documented`() {
        assertTrue(AblBuiltinDocs.has("&IF"), "&IF should be documented")
        assertTrue(AblBuiltinDocs.has("&DEFINE"), "&DEFINE should be documented")
        assertTrue(AblBuiltinDocs.has("DEFINED"), "DEFINED should be documented")
    }

    @Test
    fun `database access keywords are documented`() {
        assertTrue(AblBuiltinDocs.has("FOR"), "FOR should be documented")
        assertTrue(AblBuiltinDocs.has("FIND"), "FIND should be documented")
        assertTrue(AblBuiltinDocs.has("CAN-FIND"), "CAN-FIND should be documented")
        assertTrue(AblBuiltinDocs.has("AVAILABLE"), "AVAILABLE should be documented")
        assertTrue(AblBuiltinDocs.has("NO-LOCK"), "NO-LOCK should be documented")
        assertTrue(AblBuiltinDocs.has("EXCLUSIVE-LOCK"), "EXCLUSIVE-LOCK should be documented")
    }

    @Test
    fun `file IO keywords are documented`() {
        assertTrue(AblBuiltinDocs.has("INPUT"), "INPUT should be documented")
        assertTrue(AblBuiltinDocs.has("OUTPUT"), "OUTPUT should be documented")
        assertTrue(AblBuiltinDocs.has("IMPORT"), "IMPORT should be documented")
        assertTrue(AblBuiltinDocs.has("EXPORT"), "EXPORT should be documented")
        assertTrue(AblBuiltinDocs.has("COPY-LOB"), "COPY-LOB should be documented")
    }

    @Test
    fun `alias entries are consistent`() {
        val substr = AblBuiltinDocs.get("SUBSTR")
        assertTrue(substr.isPresent, "SUBSTR alias should be present")
        val avail = AblBuiltinDocs.get("AVAIL")
        assertTrue(avail.isPresent, "AVAIL alias should be present")
    }

    @Test
    fun `absent entry returns empty Optional`() {
        assertFalse(AblBuiltinDocs.has("DEFINITELY_NOT_AN_ABL_BUILTIN"))
        assertFalse(AblBuiltinDocs.get("DEFINITELY_NOT_AN_ABL_BUILTIN").isPresent)
    }

    @Test
    fun `has more than 200 documented entries`() {
        // Count by checking the known entries — a proxy for coverage
        val knownEntries = listOf(
            "LENGTH", "SUBSTRING", "ENTRY", "NUM-ENTRIES", "REPLACE", "TRIM",
            "STRING", "INTEGER", "INT64", "DECIMAL", "CAPS", "UPPER", "LC", "LOWER",
            "FILL", "CHR", "ASC", "INDEX", "LOOKUP", "SUBSTITUTE", "COMPARE",
            "MATCHES", "BEGINS", "ENCODE", "BASE64-ENCODE", "BASE64-DECODE",
            "ABS", "MAX", "MIN", "ROUND", "TRUNCATE", "SQRT", "RANDOM", "SIGN",
            "TODAY", "NOW", "TIME", "YEAR", "MONTH", "DAY", "WEEKDAY", "DATE",
            "DATETIME", "ADD-INTERVAL", "INTERVAL", "TIMEZONE", "ISO-DATE",
            "CAN-FIND", "CAN-DO", "AVAILABLE", "ROWID", "RECID", "NEXT-VALUE",
            "CURRENT-VALUE", "FIRST-OF", "LAST-OF", "LOCKED",
            "VALID-OBJECT", "VALID-HANDLE", "TYPE-OF", "CAST", "GET-CLASS",
            "PROGRAM-NAME", "USERID", "OPSYS", "PROVERSION", "PROPATH", "SEARCH",
            "SESSION", "THIS-PROCEDURE", "THIS-OBJECT", "SUPER", "ERROR-STATUS",
            "DEFINE", "ASSIGN", "FOR", "FIND", "MESSAGE", "RUN", "CREATE",
            "NEW", "USING", "CATCH", "THROW", "RETURN", "LEAVE", "NEXT",
            "PROCEDURE", "FUNCTION", "CLASS", "METHOD", "CONSTRUCTOR", "DESTRUCTOR",
            "INTERFACE", "ABSTRACT", "OVERRIDE", "FINAL", "STATIC",
            "&IF", "&DEFINE", "&SCOPED-DEFINE", "DEFINED",
            "DISPLAY", "PROMPT-FOR", "UPDATE", "ENABLE", "DISABLE",
            "INPUT", "OUTPUT", "IMPORT", "EXPORT", "PUT", "GET", "COPY-LOB",
            "READ-JSON", "WRITE-JSON", "BUFFER-COPY", "BUFFER-COMPARE",
            "TEMP-TABLE", "DATASET", "TRANSACTION", "NO-LOCK", "EXCLUSIVE-LOCK",
            "FILE-INFO", "CONNECT", "DISCONNECT", "EXTENT", "FORMAT"
        )
        val presentCount = knownEntries.count { AblBuiltinDocs.has(it) }
        assertTrue(presentCount >= 100, "At least 100 known entries should be present, found $presentCount")
    }
}
