package app.dsh.mobile.engine

import org.junit.Assert.*
import org.junit.Test

class BootTokenCaptureTest {
    @Test fun persistentEngineRejectsWholeProcessRootBeforeNativeSpawn() {
        val unused = java.io.File("unused-local-engine-test")
        try {
            EngineProcess.spawn(unused, unused, unused, emptyArray(), unused, suPath = "/system/bin/su")
            fail("whole-process Root must be rejected for the local persistent engine")
        } catch (error: EngineStartException) {
            assertTrue(error.message.orEmpty().contains("application UID"))
        }
    }
    private val url = "http://127.0.0.1:3080/?token=private_test_token_123"
    private fun capture(line: String, port: Int = 3080): BootTokenCapture =
        BootTokenCapture(port).also { it.observe(line) }

    @Test fun acceptsOnlyValidEngineAnnouncement() {
        val channel = capture("dsh web: $url")
        assertEquals(url, channel.value())
    }
    @Test fun unrelatedUrlsAreNotAnnouncements() {
        assertNull(capture("message $url").value())
    }
    @Test fun wrongOriginIsRejected() {
        assertNull(capture("dsh web: http://example.invalid:3080/?token=a").value())
        assertNull(capture("dsh web: http://127.0.0.1.evil.invalid:3080/?token=a").value())
    }
    @Test fun wrongPortIsRejected() {
        assertNull(capture("dsh web: $url", 3081).value())
    }
    @Test fun wrongSchemePathOrUserInfoIsRejected() {
        for (value in listOf("https://127.0.0.1:3080/?token=a",
            "http://127.0.0.1:3080/other?token=a", "http://user@127.0.0.1:3080/?token=a")) {
            assertNull(capture("dsh web: $value").value())
        }
    }
    @Test fun extraQueryAndFragmentAreRejected() {
        assertNull(capture("dsh web: ${url}&redirect=elsewhere").value())
        assertNull(capture("dsh web: ${url}#fragment").value())
    }
    @Test fun emptyOrInvalidEncodedTokenIsRejected() {
        assertNull(capture("dsh web: http://127.0.0.1:3080/?token=").value())
        assertNull(capture("dsh web: http://127.0.0.1:3080/?token=%XX").value())
    }
    @Test fun firstValidValueCannotBeOverwritten() {
        val channel = capture("dsh web: $url")
        assertFalse(channel.observe("dsh web: http://127.0.0.1:3080/?token=other"))
        assertEquals(url, channel.value())
    }
    @Test fun bootInstancesDoNotShareState() {
        val old = capture("dsh web: $url")
        val fresh = BootTokenCapture(3080)
        assertNull(fresh.value())
        old.invalidate()
        assertFalse(old.observe("dsh web: $url"))
        assertNull(old.value())
        assertNull(fresh.value())
    }
    @Test fun credentialsStayOutOfBothDiagnosticSinks() {
        val raw = "dsh web: $url"
        val channel = capture(raw)
        val safe = LogPolicy().sanitize(raw).text
        assertEquals(url, channel.value())
        assertTrue(safe.contains("[url]"))
        assertFalse(safe.contains("private_test_token_123"))
        assertFalse(safe.contains("http://"))
    }
    @Test fun oversizedAnnouncementIsRejected() {
        assertNull(capture("x".repeat(32768) + "dsh web: $url").value())
    }
    @Test fun terminalAnsiSuffixDoesNotEnterCapturedUrl() {
        assertEquals(url, capture("dsh web: $url\u001b[0m").value())
    }
    @Test fun invalidPortIsRejected() {
        try { BootTokenCapture(0); fail("expected invalid-port rejection") }
        catch (_: IllegalArgumentException) {}
    }
}
