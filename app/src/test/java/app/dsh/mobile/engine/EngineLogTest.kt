package app.dsh.mobile.engine

import org.junit.Assert.*
import org.junit.Test
import java.io.ByteArrayInputStream
import java.io.InputStreamReader
import java.io.Reader
import java.io.StringReader
import java.nio.ByteBuffer
import java.nio.charset.CodingErrorAction
import java.nio.file.Files
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit

class EngineLogTest {
    private fun cleanup(directory: java.nio.file.Path) {
        val expectedParent = java.nio.file.Paths.get(System.getProperty("java.io.tmpdir")).toRealPath()
        val resolved = directory.toRealPath()
        check(resolved.parent == expectedParent && resolved.fileName.toString().startsWith("pocket-log-test-"))
        resolved.toFile().deleteRecursively()
    }
    private fun lines(reader: Reader, limit: Int = 32768): List<String> {
        val output = ArrayList<String>()
        LogLinePump.read(reader, maxChars = limit, emit = { output.add(it) })
        return output
    }

    @Test fun crLfAndPartialFinalLineArePreserved() {
        assertEquals(listOf("one", "two", "", "three"), lines(StringReader("one\r\ntwo\n\nthree")))
    }

    @Test fun splitUtf8CjkAndEmojiRemainIntact() {
        val value = "中文😀🚀".repeat(50)
        val bytes = value.toByteArray(Charsets.UTF_8)
        val input = object : ByteArrayInputStream(bytes) {
            override fun read(buffer: ByteArray, offset: Int, length: Int): Int =
                super.read(buffer, offset, minOf(length, 1))
        }
        assertEquals(listOf(value), lines(InputStreamReader(input, Charsets.UTF_8)))
    }

    @Test fun overlongPhysicalLineHasABoundedPrefix() {
        val reader = object : Reader() {
            var remaining = 1_000_000
            override fun read(buffer: CharArray, offset: Int, length: Int): Int {
                if (remaining == 0) return -1
                val count = minOf(length, remaining)
                java.util.Arrays.fill(buffer, offset, offset + count, 'x')
                remaining -= count
                return count
            }
            override fun close() {}
        }
        val output = lines(reader, 32)
        assertEquals(1, output.size)
        assertEquals(32 + "...[line truncated]".length, output[0].length)
        assertTrue(output[0].endsWith("[line truncated]"))
    }

    @Test fun logPolicySeesCredentialsAcrossTransportChunks() {
        val value = "x".repeat(4091) + " apiKey=sk-private-fixture-value\n"
        val output = lines(StringReader(value))
        val safe = LogPolicy(LogPolicyConfig(8192, 32768)).sanitize(output.single()).text
        assertFalse(safe.contains("private-fixture-value"))
        assertTrue(safe.contains("[redacted]"))
    }

    @Test fun hugeSingleEntryCannotExceedEightKiBOrDiskLimit() {
        val directory = Files.createTempDirectory("pocket-log-test-")
        try {
            val file = directory.resolve("engine.log").toFile()
            EngineLog.append(file, "中文😀".repeat(500_000))
            assertTrue(file.length() <= EngineLog.MAX_ENTRY_BYTES)
            assertTrue(file.length() <= EngineLog.MAX_BYTES)
            val decoder = Charsets.UTF_8.newDecoder().onMalformedInput(CodingErrorAction.REPORT)
            decoder.decode(ByteBuffer.wrap(file.readBytes()))
        } finally {
            cleanup(directory)
        }
    }

    @Test fun diskRotationRetainsValidUtf8AndRecentOutput() {
        val directory = Files.createTempDirectory("pocket-log-test-")
        try {
            val file = directory.resolve("engine.log").toFile()
            repeat(600) { EngineLog.append(file, "中文😀".repeat(700)) }
            EngineLog.append(file, "last-record")
            assertTrue(file.length() <= EngineLog.MAX_BYTES)
            val decoder = Charsets.UTF_8.newDecoder().onMalformedInput(CodingErrorAction.REPORT)
            val text = decoder.decode(ByteBuffer.wrap(file.readBytes())).toString()
            assertTrue(text.endsWith("last-record\n"))
        } finally {
            cleanup(directory)
        }
    }

    @Test fun saturatedUiQueueRemainsBoundedAndCanDrain() {
        val directory = Files.createTempDirectory("pocket-log-test-")
        try {
            val file = directory.resolve("engine.log").toFile()
            val large = "apiKey=sk-secret-fixture " + "a".repeat(100_000)
            repeat(1500) {
                EngineLog.appendAsync(file, large)
                assertTrue(EngineLog.pendingAsyncCountForTests() <= EngineLog.MAX_ASYNC_WRITES)
            }
            assertTrue(EngineLog.drainAsyncForTests(10000))
            assertTrue(file.length() <= EngineLog.MAX_BYTES)
            assertFalse(file.readText().contains("secret-fixture"))
        } finally {
            cleanup(directory)
        }
    }

    @Test fun concurrentWritersKeepCompleteRecords() {
        val directory = Files.createTempDirectory("pocket-log-test-")
        val workers = Executors.newFixedThreadPool(4)
        try {
            val file = directory.resolve("engine.log").toFile()
            val jobs = (0 until 4).map { id ->
                workers.submit { repeat(200) { EngineLog.append(file, "writer-$id-row-$it") } }
            }
            jobs.forEach { it.get(15, TimeUnit.SECONDS) }
            assertEquals(800, file.readLines().size)
            assertTrue(file.readLines().all { it.matches(Regex("writer-[0-3]-row-[0-9]+")) })
        } finally {
            workers.shutdownNow()
            cleanup(directory)
        }
    }
}
