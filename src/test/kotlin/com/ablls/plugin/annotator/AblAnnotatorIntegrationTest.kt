package com.ablls.plugin.annotator

import com.ablls.plugin.core.AblParserFacade
import com.ablls.plugin.core.AblProjectAnalysisService
import com.intellij.lang.annotation.AnnotationHolder
import com.intellij.lang.annotation.HighlightSeverity
import com.intellij.openapi.project.Project
import com.intellij.openapi.util.TextRange
import com.intellij.psi.PsiDocumentManager
import com.intellij.psi.PsiFile
import com.intellij.testFramework.LightVirtualFile
import org.junit.Assert.assertEquals
import org.junit.Before
import org.junit.Ignore
import org.junit.Test
import org.mockito.ArgumentCaptor
import org.mockito.Mockito.any
import org.mockito.Mockito.anyString
import org.mockito.Mockito.eq
import org.mockito.Mockito.mock
import org.mockito.Mockito.times
import org.mockito.Mockito.verify
import org.mockito.Mockito.`when`

class AblAnnotatorIntegrationTest {
    private lateinit var mockProject: Project
    private lateinit var mockPsiFile: PsiFile
    private lateinit var mockAnnotationHolder: AnnotationHolder
    private lateinit var annotator: AblAnnotator
    private lateinit var parserFacade: AblParserFacade

    @Before
    fun setUp() {
        mockProject = mock(Project::class.java)
        mockPsiFile = mock(PsiFile::class.java)
        mockAnnotationHolder = mock(AnnotationHolder::class.java)
        annotator = AblAnnotator()
        parserFacade = AblParserFacade()

        // Mock the AblProjectAnalysisService
        val mockAnalysisService = mock(AblProjectAnalysisService::class.java)
        `when`(mockProject.getService(eq(AblProjectAnalysisService::class.java))).thenReturn(mockAnalysisService)

        // Mock AnnotationBuilder
        val mockAnnotationBuilder = mock(com.intellij.lang.annotation.AnnotationBuilder::class.java)
        `when`(mockAnnotationHolder.newAnnotation(any(HighlightSeverity::class.java), anyString()))
            .thenReturn(mockAnnotationBuilder)
        `when`(mockAnnotationBuilder.range(any(TextRange::class.java))).thenReturn(mockAnnotationBuilder)
        `when`(mockAnnotationBuilder.create()).thenReturn(null)
    }

    @Ignore("Requires mockStatic(PsiDocumentManager) + verify-after-apply rewrite — migrate to BasePlatformTestCase")
    @Test
    fun testErrorHighlightLength() {
        val code = "DEFINE VARIABLE i AS INTEGER NO"
        val uri = "test.p"

        // Mock the PsiDocumentManager and Document (moved from setUp)
        val mockPsiDocumentManager = mock(PsiDocumentManager::class.java)
        val mockDocument = mock(com.intellij.openapi.editor.Document::class.java)
        `when`(mockPsiFile.project).thenReturn(mockProject)
        `when`(mockPsiDocumentManager.getDocument(mockPsiFile)).thenReturn(mockDocument)
        `when`(mockDocument.textLength).thenReturn(code.length)
        `when`(mockDocument.getLineStartOffset(0)).thenReturn(0)
        `when`(mockDocument.getLineEndOffset(0)).thenReturn(code.length)
        `when`(mockDocument.lineCount).thenReturn(1)
        `when`(mockDocument.charsSequence).thenReturn(code)

        // Mock the file content and virtual file for collectInformation
        `when`(mockPsiFile.text).thenReturn(code)
        `when`(mockPsiFile.virtualFile).thenReturn(LightVirtualFile(uri, code))

        val input = annotator.collectInformation(mockPsiFile, mock(com.intellij.openapi.editor.Editor::class.java), false)
        val syntaxErrors = parserFacade.parse(code, uri).syntaxErrors

        // Inject the syntaxErrors into the mockAnalysisService for doAnnotate
        val mockAnalysisService = mockProject.getService(AblProjectAnalysisService::class.java) as AblProjectAnalysisService
        `when`(mockAnalysisService.analyzeFile(code, uri)).thenReturn(com.ablls.plugin.core.AblParseResult(null, null, syntaxErrors, uri))

        val errors = annotator.doAnnotate(input)

        // Capture the TextRange created by the annotator
        val capturedRange = ArgumentCaptor.forClass(TextRange::class.java)
        verify(mockAnnotationHolder, times(1)).newAnnotation(any(HighlightSeverity::class.java), anyString())
            .range(capturedRange.capture())
            .create()

        annotator.apply(mockPsiFile, errors, mockAnnotationHolder)

        // Verify the captured TextRange
        val expectedStartOffset = code.indexOf("NO")
        val expectedEndOffset = expectedStartOffset + "NO".length

        assertEquals("Start offset should match", expectedStartOffset, capturedRange.value.startOffset)
        assertEquals("End offset should match", expectedEndOffset, capturedRange.value.endOffset)
    }
}
