package app.dsh.mobile.engine

import java.io.File
import java.io.RandomAccessFile
import java.util.concurrent.ArrayBlockingQueue
import java.util.concurrent.CountDownLatch
import java.util.concurrent.RejectedExecutionHandler
import java.util.concurrent.ThreadFactory
import java.util.concurrent.ThreadPoolExecutor
import java.util.concurrent.TimeUnit

/**
 * Serialized engine.log sink for the local Android distribution.
 *
 * Common marked credentials and complete URLs are sanitized before buffering.
 * Each retained record is <=8KiB including its final LF; the UI queue retains at
 * most 64 such records, and the on-disk file remains <=2MiB. Queue saturation
 * discards old diagnostic records rather than blocking the UI thread.
 *
 * This is not a DLP system for arbitrary file contents or unlabeled secrets.
 * Conversation persistence is separate: dropping diagnostics does not drop chat.
 */
object EngineLog {
    const val MAX_BYTES: Long = 2L shl 20
    const val MAX_ENTRY_BYTES: Int = 8192
    const val MAX_ASYNC_WRITES: Int = 64

    private val policy = LogPolicy(LogPolicyConfig(MAX_ENTRY_BYTES - 1, 32768))
    private val lock = Any()
    private val asyncExec = ThreadPoolExecutor(
        1, 1, 0L, TimeUnit.MILLISECONDS,
        ArrayBlockingQueue<Runnable>(MAX_ASYNC_WRITES),
        ThreadFactory { r -> Thread(r, "pocket-engine-log").apply { isDaemon = true } },
        RejectedExecutionHandler { task, executor ->
            // Direct offer is deliberately non-recursive: DiscardOldestPolicy can
            // recursively reject under competing producers. Never block callers.
            if (!executor.isShutdown) {
                executor.queue.poll()
                executor.queue.offer(task)
            }
        },
    ).apply { prestartCoreThread() }

    fun append(file: File, text: String) {
        val bytes = record(text)
        synchronized(lock) { writeLocked(file, bytes) }
    }

    fun appendAsync(file: File, text: String) {
        // Sanitize before the closure is queued, so it never retains a giant raw
        // console string or an unredacted credential while waiting for disk I/O.
        val bytes = record(text)
        runCatching { asyncExec.execute { synchronized(lock) { writeLocked(file, bytes) } } }
    }

    private fun record(text: String): ByteArray {
        val safe = policy.sanitize(text).text.trimEnd('\n')
        return (safe + "\n").toByteArray(Charsets.UTF_8)
    }

    private fun writeLocked(file: File, add: ByteArray) {
        try {
            check(add.size <= MAX_ENTRY_BYTES)
            file.parentFile?.mkdirs()
            RandomAccessFile(file, "rw").use { raf ->
                val current = raf.length()
                if (current <= MAX_BYTES - add.size) {
                    raf.seek(current)
                    raf.write(add)
                    return
                }
                // Keep a bounded tail even if another writer previously made an
                // oversized legacy file. Never allocate/read the complete file.
                val keep = minOf(current, MAX_BYTES / 2).toInt()
                raf.seek(current - keep)
                val tail = ByteArray(keep)
                raf.readFully(tail)
                var start = 0
                while (start < tail.size && (tail[start].toInt() and 0xC0) == 0x80) start++
                val retained = tail.size - start
                raf.seek(0)
                raf.write(tail, start, retained)
                raf.setLength(retained.toLong())
                raf.seek(retained.toLong())
                raf.write(add)
                check(raf.length() <= MAX_BYTES)
            }
        } catch (_: Exception) {
            // Diagnostics must not break startup; do not log the original error,
            // its message/stack, environment, paths or URLs through another sink.
        }
    }

    internal fun pendingAsyncCountForTests(): Int = asyncExec.queue.size

    internal fun drainAsyncForTests(timeoutMillis: Long): Boolean {
        val done = CountDownLatch(1)
        asyncExec.execute { done.countDown() }
        return done.await(timeoutMillis, TimeUnit.MILLISECONDS)
    }
}
