package app.dsh.mobile.engine

import android.content.Context
import android.system.Os
import android.util.Log
import java.io.File
import java.nio.file.Files
import java.nio.file.StandardCopyOption
import java.util.UUID

/** Kernel permission check: an ordinary app can signal only its own unique UID. */
private fun canSignalProcess(pid: Int): Boolean = runCatching {
    Os.kill(pid, 0)
    true
}.getOrDefault(false)

/** Bounded /proc parsing helpers, separately unit tested. */
object LocalProcEvidence {
    fun parseStartTicks(stat: String): Long? {
        if (stat.length !in 4..16_384) return null
        val suffix = stat.substringAfterLast(") ", "")
        if (suffix.isEmpty()) return null
        // suffix begins with field 3 (state); starttime is field 22 => index 19.
        return suffix.trim().split(Regex("\\s+")).getOrNull(19)?.toLongOrNull()
            ?.takeIf { it > 0L }
    }

    fun parseArgv(bytes: ByteArray): List<String>? {
        if (bytes.isEmpty() || bytes.size > 128 * 1024) return null
        val result = ArrayList<String>()
        var start = 0
        for (index in bytes.indices) {
            if (bytes[index].toInt() != 0) continue
            // Preserve internal empty argv items. A final NUL terminates the last
            // real item; it does not create one additional synthetic item.
            result += String(bytes, start, index - start, Charsets.UTF_8)
            start = index + 1
        }
        if (start < bytes.size) result += String(bytes, start, bytes.size - start, Charsets.UTF_8)
        return result.takeIf { it.isNotEmpty() }
    }

    fun startTicks(pid: Int): Long? = runCatching {
        parseStartTicks(File("/proc/$pid/stat").readText())
    }.getOrNull()

    fun argv(pid: Int): List<String>? = runCatching {
        parseArgv(File("/proc/$pid/cmdline").readBytes())
    }.getOrNull()
}

/** Strict argv identity evidence for a Harness Pocket web-engine process. */
object LocalEngineIdentity {
    private fun direct(args: List<String>, node: String, entry: String): Boolean {
        if (args.firstOrNull() != node) return false
        val entryIndex = args.indexOf(entry)
        return entryIndex > 0 && args.getOrNull(entryIndex + 1) == "web"
    }

    /** Parse only our exact generated LD_LIBRARY_PATH wrapper and quoted exec command. */
    internal fun parseQuotedExec(script: String): List<String>? {
        val prefix = "export LD_LIBRARY_PATH='"
        val marker = "'; exec "
        if (!script.startsWith(prefix) || script.indexOf('\n') >= 0 || script.indexOf('\r') >= 0) return null
        val markerAt = script.indexOf(marker, prefix.length)
        if (markerAt < 0 || script.indexOf(marker, markerAt + marker.length) >= 0) return null
        val libraryPath = script.substring(prefix.length, markerAt)
        if (libraryPath.isEmpty() || libraryPath.indexOf('\'') >= 0 || libraryPath.indexOf(';') >= 0) return null
        val command = script.substring(markerAt + marker.length)
        val args = ArrayList<String>()
        var cursor = 0
        while (cursor < command.length) {
            while (cursor < command.length && command[cursor] == ' ') cursor++
            if (cursor == command.length) break
            if (command[cursor] != '\'') return null
            val end = command.indexOf('\'', cursor + 1)
            if (end < 0) return null
            args += command.substring(cursor + 1, end)
            cursor = end + 1
            if (cursor < command.length && command[cursor] != ' ') return null
        }
        return args.takeIf { it.isNotEmpty() }
    }

    fun matches(argv: List<String>, engineRoot: File): Boolean {
        if (argv.isEmpty() || argv.any { it.indexOf('\u0000') >= 0 || it.contains("lan-web-proxy") }) return false
        val root = engineRoot.path.replace('\\', '/').trimEnd('/')
        val normalized = argv.map { it.replace('\\', '/') }
        val node = "$root/bin/node"
        val entry = "$root/lib/node_modules/@deepseek-ai/dsh/lib/bin.js"
        if (direct(normalized, node, entry)) return true
        if (normalized.size != 3 || normalized[0] != "/system/bin/sh" || normalized[1] != "-c") return false
        return parseQuotedExec(normalized[2])?.let { direct(it, node, entry) } == true
    }
}

/**
 * Private generation-bound ownership proof for the currently spawned engine.
 * The record contains no token, command arguments, credentials or public path.
 */
object EngineOwnerRecord {
    private const val TAG = "EngineOwnerRecord"
    private const val VERSION = 2
    private const val MAX_AGE_MS = 7L * 24 * 60 * 60 * 1000
    private val lock = Any()

    data class Record(val pid: Int, val createdAt: Long, val startTicks: Long)

    class Lease internal constructor(private val file: File?, private val record: Record?) {
        fun clear() {
            val f = file ?: return
            val expected = record ?: return
            synchronized(lock) { clearIfSameLocked(f, expected) }
        }
    }

    internal fun encode(record: Record): String =
        "version=$VERSION\npid=${record.pid}\ncreatedAt=${record.createdAt}\nstartTicks=${record.startTicks}\n"

    internal fun decode(text: String): Record? {
        if (text.length !in 1..256) return null
        val lines = text.lineSequence().filter { it.isNotEmpty() }.toList()
        if (lines.size != 4 || lines[0] != "version=$VERSION") return null
        fun number(index: Int, prefix: String): Long? = lines[index]
            .takeIf { it.startsWith(prefix) }?.removePrefix(prefix)?.toLongOrNull()
        val pidLong = number(1, "pid=") ?: return null
        val createdAt = number(2, "createdAt=") ?: return null
        val startTicks = number(3, "startTicks=") ?: return null
        if (pidLong !in 2..Int.MAX_VALUE.toLong() || createdAt <= 0L || startTicks <= 0L) return null
        return Record(pidLong.toInt(), createdAt, startTicks)
    }

    private fun fileFor(logFile: File): File? {
        val engine = logFile.absoluteFile.parentFile ?: return null
        val filesDir = engine.parentFile ?: return null
        return File(filesDir, "pocket-engine-owner.v2")
    }

    private fun read(file: File): Record? = runCatching {
        if (!file.isFile || file.length() > 256) null else decode(file.readText())
    }.getOrNull()

    private fun clearIfSameLocked(file: File, expected: Record) {
        if (read(file) == expected) file.delete()
    }

    fun register(logFile: File, pid: Int): Lease {
        val file = fileFor(logFile)
        val startTicks = if (pid > 1) LocalProcEvidence.startTicks(pid) else null
        if (file == null || startTicks == null) return Lease(null, null)
        val record = Record(pid, System.currentTimeMillis(), startTicks)
        synchronized(lock) {
            runCatching {
                file.parentFile?.mkdirs()
                val temporary = File(
                    file.parentFile,
                    file.name + ".tmp-" + pid + "-" + record.createdAt + "-" + UUID.randomUUID(),
                )
                temporary.writeText(encode(record))
                runCatching {
                    Files.move(
                        temporary.toPath(), file.toPath(),
                        StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING,
                    )
                }.getOrElse {
                    Files.move(temporary.toPath(), file.toPath(), StandardCopyOption.REPLACE_EXISTING)
                }
            }.onFailure { Log.w(TAG, "cannot persist engine owner record") }
        }
        return Lease(file, record)
    }

    private fun matchesCurrent(record: Record, engineRoot: File): Boolean =
        LocalProcEvidence.startTicks(record.pid) == record.startTicks &&
            LocalProcEvidence.argv(record.pid)?.let { LocalEngineIdentity.matches(it, engineRoot) } == true &&
            canSignalProcess(record.pid)

    /** Return 1 only when the exact recorded generation was signalled. */
    fun reapRecorded(logFile: File, portStillBusy: () -> Boolean): Int = synchronized(lock) {
        val file = fileFor(logFile) ?: return@synchronized 0
        val record = read(file)
        if (record == null) {
            file.delete()
            return@synchronized 0
        }
        val now = System.currentTimeMillis()
        val engineRoot = logFile.absoluteFile.parentFile ?: return@synchronized 0
        if (record.pid == android.os.Process.myPid() || record.createdAt > now + 60_000 ||
            now - record.createdAt > MAX_AGE_MS || !matchesCurrent(record, engineRoot)
        ) {
            clearIfSameLocked(file, record)
            return@synchronized 0
        }
        try {
            Log.w(TAG, "stopping recorded stale engine pid=${record.pid}")
            if (runCatching { Os.kill(record.pid, 15) }.isFailure) return@synchronized 0
            val deadline = System.currentTimeMillis() + 900L
            while (System.currentTimeMillis() < deadline && portStillBusy()) Thread.sleep(90L)
            if (portStillBusy() && matchesCurrent(record, engineRoot)) {
                runCatching { Os.kill(record.pid, 9) }
            }
            1
        } finally {
            clearIfSameLocked(file, record)
        }
    }
}

/** Same-UID fallback for the tiny fork-to-record race and legacy 0.1.0. */
object LocalOwnedEngineReaper {
    private const val TAG = "LocalOwnedEngineReaper"
    private data class Candidate(val pid: Int, val startTicks: Long)

    private fun stillMatches(candidate: Candidate, root: File): Boolean =
        LocalProcEvidence.startTicks(candidate.pid) == candidate.startTicks &&
            LocalProcEvidence.argv(candidate.pid)?.let { LocalEngineIdentity.matches(it, root) } == true &&
            canSignalProcess(candidate.pid)

    fun reapVisible(ctx: Context, portStillBusy: () -> Boolean): Int {
        val root = EngineConfig.engineRoot(ctx)
        val myPid = android.os.Process.myPid()
        val entries = runCatching { File("/proc").listFiles() }.getOrNull() ?: return 0
        val candidates = entries.mapNotNull { entry ->
            val pid = entry.name.toIntOrNull() ?: return@mapNotNull null
            if (pid <= 1 || pid == myPid || !canSignalProcess(pid)) return@mapNotNull null
            val start = LocalProcEvidence.startTicks(pid) ?: return@mapNotNull null
            val argv = LocalProcEvidence.argv(pid) ?: return@mapNotNull null
            if (!LocalEngineIdentity.matches(argv, root)) return@mapNotNull null
            Candidate(pid, start)
        }
        val signalled = candidates.filter { candidate ->
            if (!stillMatches(candidate, root)) return@filter false
            Log.w(TAG, "stopping visible stale local engine pid=${candidate.pid}")
            runCatching { Os.kill(candidate.pid, 15) }.isSuccess
        }
        val deadline = System.currentTimeMillis() + 900L
        while (System.currentTimeMillis() < deadline && portStillBusy()) Thread.sleep(90L)
        if (portStillBusy()) {
            for (candidate in signalled) {
                if (stillMatches(candidate, root)) runCatching { Os.kill(candidate.pid, 9) }
            }
        }
        return signalled.size
    }
}
