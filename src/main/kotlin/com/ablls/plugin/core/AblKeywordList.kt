package com.ablls.plugin.core

/**
 * Liste des mots-clés ABL pour l'autocomplétion.
 *
 * Organisés par catégorie pour faciliter la maintenance.
 * Complétée par les entrées de [AblBuiltinDocs] (fonctions built-in).
 */
object AblKeywordList {

    val KEYWORDS: Set<String> = buildSet {

        // ── Flux de contrôle ──────────────────────────────────────────────────
        addAll(listOf(
            "IF", "THEN", "ELSE", "DO", "END", "REPEAT", "BLOCK-LEVEL",
            "FOR", "EACH", "FIRST", "LAST", "NEXT-PROMPT",
            "CASE", "WHEN", "OTHERWISE",
            "RETURN", "LEAVE", "NEXT", "UNDO", "RETRY",
            "CATCH", "FINALLY", "THROW",
            "BY", "WHILE", "TO", "FROM",
            "BREAK"
        ))

        // ── Définitions / structure ───────────────────────────────────────────
        addAll(listOf(
            "DEFINE", "DEF",
            "VARIABLE", "VAR",
            "PARAMETER", "PARAM",
            "TEMP-TABLE", "WORKFILE",
            "PROCEDURE", "PROC",
            "FUNCTION", "RETURNS",
            "CLASS", "INTERFACE", "ENUM",
            "METHOD", "PROPERTY", "EVENT",
            "CONSTRUCTOR", "DESTRUCTOR",
            "DATASET", "QUERY", "BUFFER",
            "USING", "FIELD", "FIELDS", "INDEX",
            "INHERITS", "IMPLEMENTS",
            "NAMESPACE-URI", "NAMESPACE-PREFIX",
            "STREAM", "FRAME", "BROWSE",
            "TRIGGER", "ON", "PERSISTENT"
        ))

        // ── Types de données primitifs ────────────────────────────────────────
        addAll(listOf(
            "CHARACTER", "CHAR",
            "INTEGER", "INT",
            "INT64",
            "DECIMAL", "DEC",
            "LOGICAL",
            "DATE", "DATETIME", "DATETIME-TZ",
            "HANDLE",
            "LONGCHAR",
            "MEMPTR",
            "RAW",
            "ROWID", "RECID",
            "VOID", "OBJECT",
            "BLOB", "CLOB",
            "PROGRESS.LANG.OBJECT"
        ))

        // ── Modificateurs d'accès / qualificateurs ────────────────────────────
        addAll(listOf(
            "PUBLIC", "PRIVATE", "PROTECTED", "PACKAGE-PRIVATE",
            "STATIC", "ABSTRACT", "OVERRIDE", "FINAL",
            "NEW", "EXTENT",
            "NO-UNDO",
            "INPUT", "OUTPUT", "INPUT-OUTPUT",
            "BY-VALUE", "BY-REFERENCE", "TABLE", "TABLE-HANDLE",
            "DATASET-HANDLE"
        ))

        // ── Accès base de données ─────────────────────────────────────────────
        addAll(listOf(
            "FIND", "CREATE", "DELETE",
            "WHERE", "AND", "OR", "NOT",
            "EXCLUSIVE-LOCK", "SHARE-LOCK", "NO-LOCK",
            "AVAILABLE", "AVAIL",
            "TRANSACTION", "BEGIN", "COMMIT", "ROLLBACK",
            "OPEN", "CLOSE", "GET",
            "OF", "USE-INDEX", "PRESELECT",
            "RELEASE", "VALIDATE",
            "AMBIGUOUS", "LOCKED",
            "FIRST-OF", "LAST-OF"
        ))

        // ── OO ────────────────────────────────────────────────────────────────
        addAll(listOf(
            "THIS-OBJECT", "THIS-PROCEDURE", "SUPER",
            "CAST", "TYPE-OF", "VALID-OBJECT", "VALID-HANDLE",
            "DYNAMIC-FUNCTION", "DYNAMIC-INVOKE", "DYNAMIC-NEW",
            "GET-CLASS", "NEW"
        ))

        // ── UI / Affichage ────────────────────────────────────────────────────
        addAll(listOf(
            "DISPLAY", "VIEW", "ENABLE", "DISABLE", "HIDE",
            "PROMPT-FOR", "UPDATE", "SET",
            "VIEW-AS", "ALERT-BOX", "MESSAGE",
            "FORM", "FORMAT", "LABEL", "TITLE",
            "WAIT-FOR", "APPLY",
            "TRIGGER", "TRIGGERS"
        ))

        // ── Système ───────────────────────────────────────────────────────────
        addAll(listOf(
            "RUN", "QUIT", "STOP",
            "OUTPUT", "INPUT", "EXPORT", "IMPORT",
            "PUT", "PUT-BYTE", "GET-BYTE",
            "OS-COMMAND", "OS-COPY", "OS-DELETE", "OS-RENAME",
            "COMPILE", "XCODE",
            "LOG-MANAGER", "AUDIT-POLICY",
            "SESSION", "PROFILER", "DEBUGGER",
            "ASSIGN", "ACCUMULATE", "AGGREGATE"
        ))

        // ── Modificateurs fréquents ───────────────────────────────────────────
        addAll(listOf(
            "NO-ERROR", "NO-WAIT", "NO-LOCK",
            "SKIP", "SPACE", "COLUMN-LABEL",
            "INITIAL", "LIKE",
            "BEFORE-TABLE", "AFTER-TABLE",
            "NAMESPACE-URI", "SERIALIZABLE",
            "CLASS-TYPE", "GENERIC",
            "FORWARD", "EXTERNAL"
        ))

        // ── Littéraux ─────────────────────────────────────────────────────────
        addAll(listOf(
            "TRUE", "FALSE", "YES", "NO",
            "YES-NO", "YES-NO-CANCEL",
            "UNKNOWN", "TODAY", "NOW", "TIME"
        ))
    }
}
