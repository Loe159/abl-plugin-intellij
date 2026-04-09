package com.ablls.plugin.xref

import java.io.File
import javax.xml.parsers.DocumentBuilderFactory
import org.w3c.dom.Element

/**
 * Parse les fichiers .xref.xml générés par le compilateur OpenEdge.
 *
 * Format XML Progress :
 *   <XREF ...>
 *     <Source File="...">
 *       <Reference ReferenceType="ACCESS" ObjectIdentifier="table.field" LineNumber="42" Detail="..."/>
 *     </Source>
 *   </XREF>
 */
object XrefParser {

    fun parse(file: File): XrefFile {
        val doc = DocumentBuilderFactory.newInstance().newDocumentBuilder().parse(file)
        val root = doc.documentElement
        val sourceName = root.getAttribute("FileName").ifEmpty { file.nameWithoutExtension }

        val records = mutableListOf<XrefRecord>()
        val refs = root.getElementsByTagName("Reference")
        for (i in 0 until refs.length) {
            val el = refs.item(i) as? Element ?: continue
            val typeStr = el.getAttribute("ReferenceType").uppercase()
            val type = runCatching { XrefType.valueOf(typeStr) }.getOrDefault(XrefType.UNKNOWN)
            if (type == XrefType.UNKNOWN) continue

            records += XrefRecord(
                type       = type,
                objectName = el.getAttribute("ObjectIdentifier"),
                line       = el.getAttribute("LineNumber").toIntOrNull() ?: 0,
                detail     = el.getAttribute("Detail")
            )
        }

        // Essayer aussi le format Source/Reference imbriqué
        if (records.isEmpty()) {
            val sources = root.getElementsByTagName("Source")
            for (s in 0 until sources.length) {
                val src = sources.item(s) as? Element ?: continue
                val srcRefs = src.getElementsByTagName("Reference")
                for (r in 0 until srcRefs.length) {
                    val el = srcRefs.item(r) as? Element ?: continue
                    val typeStr = el.getAttribute("ReferenceType").uppercase()
                    val type = runCatching { XrefType.valueOf(typeStr) }.getOrDefault(XrefType.UNKNOWN)
                    if (type == XrefType.UNKNOWN) continue
                    records += XrefRecord(
                        type       = type,
                        objectName = el.getAttribute("ObjectIdentifier"),
                        line       = el.getAttribute("LineNumber").toIntOrNull() ?: 0,
                        detail     = el.getAttribute("Detail")
                    )
                }
            }
        }

        return XrefFile(sourceName, records)
    }
}
