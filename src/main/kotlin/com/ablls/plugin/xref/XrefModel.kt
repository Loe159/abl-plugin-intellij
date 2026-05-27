package com.ablls.plugin.xref

enum class XrefType {
    ACCESS,
    INCLUDE,
    RUN,
    CLASS,
    CPINTERNAL,
    SEARCH,
    STRING,
    COMPILE,
    CALL,
    CREATE,
    NEW,
    INVOKE,
    PARAMETER,
    SORT_ACCESS,
    UNKNOWN,
}

data class XrefRecord(
    val type: XrefType,
    val objectName: String,
    val line: Int,
    val detail: String = "",
)

data class XrefFile(
    val sourceName: String,
    val records: List<XrefRecord>,
)
