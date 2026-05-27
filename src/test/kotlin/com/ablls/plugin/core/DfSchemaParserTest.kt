package com.ablls.plugin.core

import junit.framework.TestCase
import java.io.File

class DfSchemaParserTest : TestCase() {
    private val dfFile: File get() =
        File("src/test/testData/schema/sports2020.df")

    fun testParsesCorrectNumberOfTables() {
        val db = DfSchemaParser.parse(dfFile, "sports2020")
        assertEquals(2, db.tableSet.size)
    }

    fun testTableNamesAreCorrect() {
        val db = DfSchemaParser.parse(dfFile, "sports2020")
        val names = db.tableSet.map { it.name }
        assertTrue("Customer manquant", names.any { it.equals("Customer", ignoreCase = true) })
        assertTrue("Order manquant", names.any { it.equals("Order", ignoreCase = true) })
    }

    fun testLogicalNameIsSet() {
        val db = DfSchemaParser.parse(dfFile, "sports2020")
        assertEquals("sports2020", db.name)
    }

    fun testFieldsAreAttachedToTable() {
        val db = DfSchemaParser.parse(dfFile, "sports2020")
        val customer = db.tableSet.first { it.name.equals("Customer", ignoreCase = true) }
        val fieldNames = customer.fieldSet.map { it.name }
        assertTrue("CustNum manquant", fieldNames.any { it.equals("CustNum", ignoreCase = true) })
        assertTrue("Name manquant", fieldNames.any { it.equals("Name", ignoreCase = true) })
        assertTrue("CreditLimit manquant", fieldNames.any { it.equals("CreditLimit", ignoreCase = true) })
        assertTrue("Active manquant", fieldNames.any { it.equals("Active", ignoreCase = true) })
    }

    fun testOrderFieldCount() {
        val db = DfSchemaParser.parse(dfFile, "sports2020")
        val order = db.tableSet.first { it.name.equals("Order", ignoreCase = true) }
        assertEquals(4, order.fieldSet.size)
    }

    fun testDataTypeIsResolvedForIntegerField() {
        val db = DfSchemaParser.parse(dfFile, "sports2020")
        val customer = db.tableSet.first { it.name.equals("Customer", ignoreCase = true) }
        val custNum = customer.fieldSet.first { it.name.equals("CustNum", ignoreCase = true) }
        assertNotNull("DataType de CustNum ne doit pas être null", custNum.dataType)
    }

    fun testMissingFileReturnsEmptyDatabase() {
        val db = DfSchemaParser.parse(File("nonexistent.df"), "empty")
        assertEquals("empty", db.name)
        assertTrue(db.tableSet.isEmpty())
    }

    fun testCollectFromSchemaProducesSymbols() {
        val db = DfSchemaParser.parse(dfFile, "sports2020")
        val schema = org.prorefactor.core.schema.Schema(db)
        val symbols = AblSymbolCollector.collectFromSchema(schema)

        val tables = symbols.filter { it.kind == AblSymbol.Kind.TABLE }
        val fields = symbols.filter { it.kind == AblSymbol.Kind.FIELD }

        assertEquals(2, tables.size)
        assertTrue("Champs Customer absents", fields.any { it.name.startsWith("Customer.", ignoreCase = true) })
        assertTrue("Champs Order absents", fields.any { it.name.startsWith("Order.", ignoreCase = true) })
    }

    fun testFieldSymbolNamesAreQualified() {
        val db = DfSchemaParser.parse(dfFile, "sports2020")
        val schema = org.prorefactor.core.schema.Schema(db)
        val symbols = AblSymbolCollector.collectFromSchema(schema)
        val custNum =
            symbols.firstOrNull {
                it.kind == AblSymbol.Kind.FIELD && it.name.equals("Customer.CustNum", ignoreCase = true)
            }
        assertNotNull("Customer.CustNum doit être indexé", custNum)
    }
}
