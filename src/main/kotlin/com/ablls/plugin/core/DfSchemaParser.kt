package com.ablls.plugin.core

import com.intellij.openapi.diagnostic.Logger
import eu.rssw.pct.elements.DataType
import org.prorefactor.core.schema.Database
import org.prorefactor.core.schema.Field
import org.prorefactor.core.schema.IDatabase
import org.prorefactor.core.schema.Table
import java.io.File

/**
 * Parseur de fichiers .df (OpenEdge dump file) — extrait tables et champs.
 *
 * Format reconnu :
 *   ADD TABLE "Customer"
 *     AREA "Schema Area"  ← ignoré
 *   ADD FIELD "CustNum" OF "Customer" AS integer
 *   ADD INDEX ...         ← ignoré
 *
 * Les lignes ADD TABLE et ADD FIELD suffisent pour alimenter le [org.prorefactor.core.schema.Schema].
 */
object DfSchemaParser {

    private val LOG = Logger.getInstance(DfSchemaParser::class.java)

    private val TABLE_RE = Regex("""^ADD\s+TABLE\s+"([^"]+)"""", RegexOption.IGNORE_CASE)
    private val FIELD_RE = Regex("""^ADD\s+FIELD\s+"([^"]+)"\s+OF\s+"([^"]+)"\s+AS\s+(\S+)""", RegexOption.IGNORE_CASE)

    /**
     * Parse [file] et retourne un [IDatabase] contenant toutes les tables et champs.
     *
     * Si le fichier ne peut pas être lu, retourne une base vide — le caller n'échoue pas.
     */
    fun parse(file: File, logicalName: String): IDatabase {
        val db = Database(logicalName)
        val tables = mutableMapOf<String, Table>()

        try {
            file.forEachLine(Charsets.UTF_8) { raw ->
                val line = raw.trim()

                TABLE_RE.find(line)?.let { m ->
                    val name = m.groupValues[1]
                    val table = Table(name, db)
                    tables[name.uppercase()] = table
                    db.add(table)
                    return@forEachLine
                }

                FIELD_RE.find(line)?.let { m ->
                    val fieldName  = m.groupValues[1]
                    val tableName  = m.groupValues[2]
                    val typeStr    = m.groupValues[3]
                    val table = tables[tableName.uppercase()] ?: return@forEachLine
                    val field = Field(fieldName, table)
                    resolveDataType(typeStr)?.let { dt -> field.setDataType(dt) }
                    table.add(field)
                }
            }
        } catch (e: Exception) {
            LOG.warn("Erreur parsing .df '${file.name}' (db=$logicalName) : ${e.message}")
        }

        LOG.info("Schéma '$logicalName' : ${tables.size} tables depuis '${file.name}'")
        return db
    }

    private fun resolveDataType(raw: String): DataType? {
        // .df utilise des tirets (datetime-tz, int64) ; DataType.get accepte le nom tel quel
        return runCatching { DataType.get(raw.uppercase()) }.getOrNull()
            ?: runCatching { DataType.get(raw.uppercase().replace('-', '_')) }.getOrNull()
    }
}
