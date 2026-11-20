package app.dsh.mobile.engine

import java.io.IOException
import java.util.concurrent.ConcurrentLinkedQueue
import java.util.concurrent.CountDownLatch

/** No JUnit, Android, or other test dependency is needed to run this entry point. */
object LogPolicyJvmTest {
    private data class Case(val name: String, val body: () -> Unit)

    @JvmStatic
    fun main(args: Array<String>) {
        val passed = runAll()
        println("KOTLIN JVM TESTS: $passed/${cases.size} PASS")
    }

    fun runAll(): Int {
        var passed = 0
        for (case in cases) {
            case.body()
            passed++
            println("PASS ${case.name}")
        }
        return passed
    }

    /** Used by the optional JUnit4 adapter; cases and assertions are not duplicated. */
    fun runCase(name: String) {
        val case = cases.singleOrNull { it.name == name }
            ?: throw IllegalArgumentException("Unknown test case")
        case.body()
    }

    private val cases = listOf(
        Case("bearer") {
            val line = LogPolicy().sanitize("prefix Bearer TOP_SECRET_123 suffix")
            equal("prefix Bearer [redacted] suffix", line.text)
            valid(line, 4096)
            val mixed = LogPolicy().sanitize("bEaReR\tTOP_SECRET_123")
            absent(mixed.text, "TOP_SECRET_123")
        },
        Case("api_key_headers") {
            for (label in listOf("API Key", "api_key", "apiKey", "API-KEY", "X-API-Key")) {
                val line = LogPolicy().sanitize("$label: TOP_SECRET_123")
                absent(line.text, "TOP_SECRET_123")
                check(line.text.endsWith("[redacted]"))
                valid(line, 4096)
            }
        },
        Case("json_fields") {
            val input = """{"api_key":"SECRET_A","accessToken":"SECRET_B","refresh_token":"SECRET_C","ok":"中文😀"}"""
            val line = LogPolicy().sanitize(input)
            for (secret in listOf("SECRET_A", "SECRET_B", "SECRET_C")) absent(line.text, secret)
            check(line.text.contains("\"ok\":\"中文😀\""))
            check(line.text.count { it == '[' } == 3)
            valid(line, 4096)
        },
        Case("authorization_header") {
            val line = LogPolicy().sanitize("Authorization: Bearer TOP_SECRET_123\nready")
            equal("Authorization: [redacted]\nready", line.text)
            val basic = LogPolicy().sanitize("Proxy-Authorization: Basic TOP_SECRET_123")
            absent(basic.text, "TOP_SECRET_123")
        },
        Case("url_tokens") {
            val line = LogPolicy().sanitize("retry https://user:PASS@example.invalid/v1?token=SECRET_A&x=1#SECRET_B next")
            equal("retry [url] next", line.text)
            for (secret in listOf("PASS", "SECRET_A", "SECRET_B", "example.invalid", "https://")) absent(line.text, secret)
            for (url in listOf("wss://example.invalid/?access_token=SECRET_A", "file:///private/SECRET_A", "www.example.invalid/?token=SECRET_A")) {
                equal("[url]", LogPolicy().sanitize(url).text)
            }
        },
        Case("token_fields") {
            val line = LogPolicy().sanitize("token=SECRET_A&ok=1 access_token : SECRET_B;done")
            equal("token=[redacted]&ok=1 access_token : [redacted];done", line.text)
            valid(line, 4096)
        },
        Case("sk_keys") {
            val line = LogPolicy().sanitize("key sk-proj-SECRET_A and sk_SECRET_B done")
            equal("key [redacted] and [redacted] done", line.text)
            valid(line, 4096)
        },
        Case("ordinary_text") {
            val input = "ready 中文😀; tokenization works; the word token is plain; monkey=banana; keyboard enabled; port=51213"
            equal(input, LogPolicy().sanitize(input).text)
        },
        Case("very_long_line") {
            val line = LogPolicy(LogPolicyConfig(64, 4096)).sanitize("a".repeat(200_000))
            check(line.truncated && line.text.endsWith("...[truncated]"))
            equal(64, line.utf8Bytes)
            valid(line, 64)
        },
        Case("cjk_emoji_byte_limit") {
            val line = LogPolicy(LogPolicyConfig(65, 4096)).sanitize("中文😀🚀".repeat(2000))
            check(line.truncated && line.text.endsWith("...[truncated]"))
            check(line.text.contains("中文😀🚀"))
            absent(line.text, "\uFFFD")
            valid(line, 65)
        },
        Case("utf8_boundary_matrix") {
            for (bytes in 32..100) {
                for (piece in listOf("中", "😀", "a😀中", "é")) {
                    val line = LogPolicy(LogPolicyConfig(bytes, 4096)).sanitize(piece.repeat(100))
                    check(line.truncated)
                    absent(line.text, "\uFFFD")
                    valid(line, bytes)
                }
            }
        },
        Case("exact_fit") {
            val input = "中".repeat(8) + "😀".repeat(2) // Exactly 32 UTF-8 bytes.
            val line = LogPolicy(LogPolicyConfig(32, 1024)).sanitize(input)
            equal(input, line.text)
            equal(32, line.utf8Bytes)
            check(!line.truncated)
            valid(line, 32)
        },
        Case("scan_boundary_surrogate") {
            val input = "x".repeat(32) + "😀" + "tail"
            val line = LogPolicy(LogPolicyConfig(128, 33)).sanitize(input)
            equal("x".repeat(32) + "...[truncated]", line.text)
            check(line.truncated)
            absent(line.text, "\uFFFD")
            valid(line, 128)
        },
        Case("invalid_surrogates_controls") {
            val input = "a\uD800b\uDC00c\u001B\u0000\t\n"
            val line = LogPolicy().sanitize(input)
            equal("a\uFFFDb\uFFFDc\uFFFD\uFFFD\t\n", line.text)
            valid(line, 4096)
        },
        Case("huge_virtual_input") {
            val input = CountingInput(Int.MAX_VALUE, "", 'x')
            val line = LogPolicy(LogPolicyConfig(128, 1024)).sanitize(input)
            check(line.truncated)
            check(input.highestIndex < 1024)
            check(input.reads in 1..10_000)
            valid(line, 128)
        },
        Case("huge_virtual_secret") {
            val input = CountingInput(Int.MAX_VALUE, "Authorization: Bearer ", 'Z')
            val line = LogPolicy(LogPolicyConfig(128, 1024)).sanitize(input)
            check(line.text.startsWith("Authorization: [redacted]"))
            check(line.truncated)
            absent(line.text, "ZZZZ")
            check(input.highestIndex < 1024 && input.reads < 10_000)
            valid(line, 128)
        },
        Case("total_buffer_bytes") {
            val buffer = BoundedLogBuffer(LogPolicy(LogPolicyConfig(64, 1024)), 128, 100)
            val appended = (1..30).map { buffer.append("item=$it " + "a".repeat(45)) }
            val snapshot = buffer.snapshot()
            check(snapshot.evictedEntries > 0)
            equal(appended.takeLast(snapshot.entries.size), snapshot.entries)
            validSnapshot(snapshot, 128, 100, 64)
        },
        Case("empty_entry_count_limit") {
            val buffer = BoundedLogBuffer(LogPolicy(LogPolicyConfig(32, 1024)), 128, 3)
            repeat(20) { buffer.append("") }
            val snapshot = buffer.snapshot()
            equal(3, snapshot.entries.size)
            equal(0, snapshot.utf8Bytes)
            equal(17L, snapshot.evictedEntries)
            validSnapshot(snapshot, 128, 3, 32)
        },
        Case("concurrent_writers_snapshots") {
            val buffer = BoundedLogBuffer(LogPolicy(LogPolicyConfig(128, 1024)), 8192, 64)
            val start = CountDownLatch(1)
            val failures = ConcurrentLinkedQueue<Throwable>()
            val threads = (0 until 8).map { worker ->
                Thread {
                    try {
                        start.await()
                        repeat(200) { item ->
                            buffer.append("worker=$worker item=$item token=HIDDEN_$worker-$item 😀")
                            if (item % 10 == 0) validSnapshot(buffer.snapshot(), 8192, 64, 128)
                        }
                    } catch (failure: Throwable) {
                        failures.add(failure)
                    }
                }
            }
            threads.forEach { it.start() }
            start.countDown()
            threads.forEach { it.join() }
            check(failures.isEmpty()) { "concurrent validation failed (raw exceptions suppressed)" }
            val snapshot = buffer.snapshot()
            validSnapshot(snapshot, 8192, 64, 128)
            snapshot.entries.forEach { absent(it.text, "HIDDEN_") }
            equal(1600L, snapshot.entries.last().sequence)
            equal(1600L - snapshot.entries.size, snapshot.evictedEntries)
        },
        Case("deterministic_output") {
            val policy = LogPolicy(LogPolicyConfig(128, 1024))
            val input = "ready 中文😀 token=SECRET_A https://example.invalid/?token=SECRET_B"
            val expected = policy.sanitize(input)
            repeat(100) { equal(expected, policy.sanitize(input)) }
        },
        Case("clear_detached_snapshot") {
            val buffer = BoundedLogBuffer(LogPolicy(LogPolicyConfig(64, 1024)), 128, 2)
            buffer.append("one")
            buffer.append("two")
            val before = buffer.snapshot()
            buffer.append("three")
            buffer.clear()
            equal(2, before.entries.size)
            equal(listOf("one", "two"), before.entries.map { it.text })
            val after = buffer.snapshot()
            equal(0, after.utf8Bytes)
            check(after.entries.isEmpty())
            equal(0L, after.evictedEntries)
            equal(4L, buffer.append("four").sequence)
        },
        Case("illegal_parameters") {
            for (entry in listOf(-1, 0, 31, 65_537, Int.MAX_VALUE)) {
                expectIllegal { LogPolicyConfig(entry, 1024) }
            }
            for (scan in listOf(-1, 0, 31, 262_145, Int.MAX_VALUE)) {
                expectIllegal { LogPolicyConfig(64, scan) }
            }
            val policy = LogPolicy(LogPolicyConfig(64, 1024))
            for (capacity in listOf(0, 63, 16_777_217, Int.MAX_VALUE)) {
                expectIllegal { BoundedLogBuffer(policy, capacity, 8) }
            }
            for (count in listOf(0, -1, 4097, Int.MAX_VALUE)) {
                expectIllegal { BoundedLogBuffer(policy, 128, count) }
            }
        },
        Case("safe_error_channel") {
            val cause = IOException("PATH=/private/home API_KEY=SECRET_A https://example.invalid/?token=SECRET_B")
            val line = LogPolicy().error(EngineFailureKind.PROCESS_IO, cause, -7)
            equal("error kind=process-io cause=io exit=-7", line.text)
            for (sensitive in listOf("PATH", "API_KEY", "SECRET_A", "SECRET_B", "example.invalid", "https://", "/private")) {
                absent(line.text, sensitive)
            }
            equal("error kind=startup cause=oom", LogPolicy().error(EngineFailureKind.STARTUP, OutOfMemoryError()).text)
        },
        Case("error_does_not_read_throwable") {
            val failure = TrapException()
            val buffer = BoundedLogBuffer()
            val line = buffer.appendError(EngineFailureKind.UNKNOWN, failure)
            equal("error kind=unknown cause=other", line.text)
            validSnapshot(buffer.snapshot(), buffer.maxBufferBytes, buffer.maxEntries, 4096)
        },
        Case("quoted_secret_escaping") {
            val input = """{"password":"SECRET_A\"INSIDE","ok":"visible"}"""
            val line = LogPolicy().sanitize(input)
            absent(line.text, "SECRET_A")
            absent(line.text, "INSIDE")
            check(line.text.contains("\"ok\":\"visible\""))
            val incomplete = LogPolicy().sanitize("password='SECRET_A")
            equal("password='[redacted]'", incomplete.text)
        },
        Case("environment_containers") {
            val line = LogPolicy().sanitize("""env={"PATH":"PRIVATE_PATH","nested":[{"HOME":"PRIVATE_HOME"}]} ready""")
            equal("env=[redacted] ready", line.text)
            val dump = LogPolicy().sanitize("Environment: PATH=PRIVATE_PATH\nHOME=PRIVATE_HOME\nanything")
            equal("Environment: [redacted]", dump.text)
        },
        Case("deep_malformed_container") {
            val deep = "env=" + "[".repeat(33) + "PRIVATE_PATH" + "]".repeat(33) + "tail"
            equal("env=[redacted]", LogPolicy().sanitize(deep).text)
            equal("env=[redacted]", LogPolicy().sanitize("env={] PRIVATE_PATH tail").text)
        },
        Case("cookie_header") {
            val line = LogPolicy().sanitize("Cookie: session=SECRET_A; other=SECRET_B\nready")
            equal("Cookie: [redacted]\nready", line.text)
        },
        Case("quoted_bearer") {
            equal("Bearer \"[redacted]\" next", LogPolicy().sanitize("Bearer \"SECRET_A\" next").text)
            equal("Bearer '[redacted]'", LogPolicy().sanitize("Bearer 'SECRET_A").text)
        },
        Case("bearer_in_token_field") {
            equal("token=[redacted] next", LogPolicy().sanitize("token=Bearer SECRET_A next").text)
            equal("token=[redacted] next", LogPolicy().sanitize("token=Bearer \"SECRET_A\" next").text)
        },
    )

    private class CountingInput(
        override val length: Int,
        private val prefix: String,
        private val body: Char,
    ) : CharSequence {
        var highestIndex = -1
            private set
        var reads = 0
            private set
        override fun get(index: Int): Char {
            check(index in 0 until length)
            highestIndex = maxOf(highestIndex, index)
            reads++
            return if (index < prefix.length) prefix[index] else body
        }
        override fun subSequence(startIndex: Int, endIndex: Int): CharSequence =
            throw AssertionError("input subSequence must never be called")
        override fun toString(): String = throw AssertionError("input toString must never be called")
    }

    private class TrapException : RuntimeException() {
        override val message: String
            get() = throw AssertionError("Throwable.message must never be read")
        override fun toString(): String = throw AssertionError("Throwable.toString must never be called")
    }

    private fun valid(line: SanitizedLogLine, limit: Int) {
        equal(line.text.toByteArray(Charsets.UTF_8).size, line.utf8Bytes)
        check(line.utf8Bytes <= limit)
        wellFormedUtf16(line.text)
    }

    private fun validSnapshot(snapshot: LogSnapshot, bytes: Int, count: Int, entryBytes: Int) {
        check(snapshot.entries.size <= count && snapshot.utf8Bytes <= bytes)
        equal(snapshot.entries.sumOf { it.utf8Bytes }, snapshot.utf8Bytes)
        var previous = 0L
        for (record in snapshot.entries) {
            equal(record.text.toByteArray(Charsets.UTF_8).size, record.utf8Bytes)
            check(record.utf8Bytes <= entryBytes && record.sequence > previous)
            wellFormedUtf16(record.text)
            previous = record.sequence
        }
    }

    private fun wellFormedUtf16(text: String) {
        var cursor = 0
        while (cursor < text.length) {
            val c = text[cursor]
            if (c.code in 0xD800..0xDBFF) {
                check(cursor + 1 < text.length && text[cursor + 1].code in 0xDC00..0xDFFF)
                cursor += 2
            } else {
                check(c.code !in 0xDC00..0xDFFF)
                cursor++
            }
        }
    }

    private fun equal(expected: Any?, actual: Any?) {
        check(expected == actual) { "values differ (fixtures deliberately not printed)" }
    }

    private fun absent(text: String, sensitive: String) {
        check(!text.contains(sensitive)) { "sensitive fixture leaked (value deliberately not printed)" }
    }

    private fun expectIllegal(body: () -> Unit) {
        var rejected = false
        try {
            body()
        } catch (_: IllegalArgumentException) {
            rejected = true
        }
        check(rejected) { "invalid parameters were not rejected" }
    }
}
