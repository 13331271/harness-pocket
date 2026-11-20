package app.dsh.mobile.engine

import org.junit.Assert.*
import org.junit.Test
import java.io.File

class LocalEngineOwnershipTest {
    private val root = File("/data/user/0/app.harness.pocket/files/engine")
    private val node = "/data/user/0/app.harness.pocket/files/engine/bin/node"
    private val entry = "/data/user/0/app.harness.pocket/files/engine/lib/node_modules/@deepseek-ai/dsh/lib/bin.js"

    @Test fun exactPrivateEngineCliMatches() {
        assertTrue(LocalEngineIdentity.matches(listOf(node, "--expose-internals", entry, "web", "--no-open"), root))
    }

    @Test fun shellWrappedPrivateEngineMatches() {
        assertTrue(LocalEngineIdentity.matches(
            listOf("/system/bin/sh", "-c", "export LD_LIBRARY_PATH='/data/app/lib'; exec '$node' '--expose-internals' '$entry' 'web'"), root,
        ))
    }

    @Test fun similarPackagePrefixDoesNotMatch() {
        val other = "/data/user/0/app.harness.pocket.evil/files/engine"
        assertFalse(LocalEngineIdentity.matches(
            listOf("$other/bin/node", "$other/lib/node_modules/@deepseek-ai/dsh/lib/bin.js", "web"), root,
        ))
    }

    @Test fun foreignExecutableMentioningBothPathsDoesNotMatch() {
        assertFalse(LocalEngineIdentity.matches(listOf("/system/bin/echo", node, entry, "web"), root))
    }

    @Test fun nodeWithoutDshCliDoesNotMatchBackgroundTools() {
        assertFalse(LocalEngineIdentity.matches(
            listOf(node, "/data/user/0/app.harness.pocket/files/workspaces/server.js"), root,
        ))
    }

    @Test fun dshEntryWithoutExactNodeDoesNotMatch() {
        assertFalse(LocalEngineIdentity.matches(listOf("/system/bin/node", entry, "web"), root))
    }

    @Test fun pathMentionInUnrelatedShellScriptDoesNotMatch() {
        val script = "echo '$node'; echo '$entry'"
        assertFalse(LocalEngineIdentity.matches(listOf("/system/bin/sh", "-c", script), root))
    }

    @Test fun shellExecOfOtherScriptCannotBorrowEarlierEntryMention() {
        val script = "echo '$entry'; exec '$node' '/tmp/other.js' 'web'"
        assertFalse(LocalEngineIdentity.matches(listOf("/system/bin/sh", "-c", script), root))
    }

    @Test fun commentedExecMarkerDoesNotMatch() {
        val script = "echo ok # ; exec '$node' '$entry' 'web'"
        assertFalse(LocalEngineIdentity.matches(listOf("/system/bin/sh", "-c", script), root))
    }

    @Test fun fixedWrapperRejectsShellOperatorsInLibraryPath() {
        val script = "export LD_LIBRARY_PATH='/safe;evil'; exec '$node' '$entry' 'web'"
        assertFalse(LocalEngineIdentity.matches(listOf("/system/bin/sh", "-c", script), root))
    }

    @Test fun backupOrDisabledSuffixDoesNotMatch() {
        assertFalse(LocalEngineIdentity.matches(listOf("$node.backup", entry, "web"), root))
        assertFalse(LocalEngineIdentity.matches(listOf(node, "$entry.disabled", "web"), root))
    }

    @Test fun lanProxyIsAlwaysExcluded() {
        assertFalse(LocalEngineIdentity.matches(listOf(node, entry, "lan-web-proxy"), root))
    }

    @Test fun blankOrEmbeddedNulIsRejected() {
        assertFalse(LocalEngineIdentity.matches(emptyList(), root))
        assertFalse(LocalEngineIdentity.matches(listOf(node + "\u0000", entry), root))
    }

    @Test fun ownerRecordRoundTrip() {
        val record = EngineOwnerRecord.Record(4321, 1_794_973_473_000L, 987654L)
        assertEquals(record, EngineOwnerRecord.decode(EngineOwnerRecord.encode(record)))
    }

    @Test fun malformedOwnerRecordsAreRejected() {
        for (text in listOf("", "version=1\npid=4321\ncreatedAt=1\nstartTicks=2\n",
            "version=2\npid=1\ncreatedAt=1\nstartTicks=2\n",
            "version=2\npid=x\ncreatedAt=1\nstartTicks=2\n",
            "version=2\npid=4321\ncreatedAt=-1\nstartTicks=2\n",
            "version=2\npid=4321\ncreatedAt=1\nstartTicks=0\n",
            "version=2\npid=4321\ncreatedAt=1\nstartTicks=2\nextra=x\n")) {
            assertNull(EngineOwnerRecord.decode(text))
        }
    }

    @Test fun recordContainsGenerationButNoTokenOrCommand() {
        val encoded = EngineOwnerRecord.encode(EngineOwnerRecord.Record(4321, 123456789L, 98765L))
        assertTrue(encoded.contains("startTicks=98765"))
        assertFalse(encoded.contains("token", ignoreCase = true))
        assertFalse(encoded.contains("cmd", ignoreCase = true))
        assertFalse(encoded.contains("path", ignoreCase = true))
        assertTrue(encoded.length <= 256)
    }

    @Test fun procStartTimeParserUsesField22AfterComplexComm() {
        val fieldsAfterComm = listOf(
            "S", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13", "14",
            "15", "16", "17", "18", "987654", "20", "21",
        )
        assertEquals(987654L, LocalProcEvidence.parseStartTicks("4321 (node worker) " + fieldsAfterComm.joinToString(" ")))
    }

    @Test fun malformedProcStatIsRejected() {
        assertNull(LocalProcEvidence.parseStartTicks(""))
        assertNull(LocalProcEvidence.parseStartTicks("4321 (node) S 1 2"))
        assertNull(LocalProcEvidence.parseStartTicks("4321 (node) " + List(22) { "x" }.joinToString(" ")))
    }

    @Test fun nulSeparatedArgvPreservesExactBoundaries() {
        val bytes = ("/system/bin/sh\u0000-c\u0000exec '$node' '$entry' web\u0000").toByteArray()
        assertEquals(
            listOf("/system/bin/sh", "-c", "exec '$node' '$entry' web"),
            LocalProcEvidence.parseArgv(bytes),
        )
    }

    @Test fun internalEmptyArgvIsNotCollapsed() {
        val bytes = "/system/bin/sh\u0000\u0000-c\u0000script\u0000".toByteArray()
        assertEquals(listOf("/system/bin/sh", "", "-c", "script"), LocalProcEvidence.parseArgv(bytes))
    }

    @Test fun emptyOrOversizedArgvIsRejected() {
        assertNull(LocalProcEvidence.parseArgv(byteArrayOf()))
        assertNull(LocalProcEvidence.parseArgv(ByteArray(128 * 1024 + 1) { 1 }))
    }
}
