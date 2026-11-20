package app.dsh.mobile.engine

import java.util.ArrayDeque

/** Immutable retained record. sequence is assigned at the buffer's synchronization point. */
data class LogRecord internal constructor(
    val sequence: Long,
    val text: String,
    val utf8Bytes: Int,
    val truncated: Boolean,
)

/** A detached, consistent snapshot; mutating a cast of entries cannot mutate the buffer. */
data class LogSnapshot internal constructor(
    val entries: List<LogRecord>,
    val utf8Bytes: Int,
    val evictedEntries: Long,
)

/**
 * Serialized sanitizer + oldest-first ring eviction.
 *
 * Both payload bytes and entry count are capped (empty strings still consume objects).
 * maxBufferBytes must fit at least one max-size policy line. Metadata/object overhead
 * is not counted as payload, but maxEntries also bounds it. No timestamps, callbacks,
 * raw Throwable, original input, or disk writes are retained.
 *
 * Concurrent append order is lock-acquisition order, not reproducible scheduler order.
 * Sanitizing inside the lock avoids one temporary sanitized entry per competing writer.
 */
class BoundedLogBuffer(
    val policy: LogPolicy = LogPolicy(),
    val maxBufferBytes: Int = 256 * 1024,
    val maxEntries: Int = 512,
) {
    init {
        require(maxBufferBytes in policy.config.maxEntryBytes..16_777_216) {
            "maxBufferBytes must fit maxEntryBytes and be at most 16777216"
        }
        require(maxEntries in 1..4096) { "maxEntries must be in 1..4096" }
    }

    private val lock = Any()
    private val records = ArrayDeque<LogRecord>(minOf(maxEntries, 32))
    private var bytes = 0
    private var evictions = 0L
    private var sequence = 0L

    fun append(input: CharSequence): LogRecord = synchronized(lock) {
        retain(policy.sanitize(input))
    }

    fun appendError(
        kind: EngineFailureKind,
        failure: Throwable? = null,
        exitCode: Int? = null,
    ): LogRecord = synchronized(lock) {
        retain(policy.error(kind, failure, exitCode))
    }

    fun snapshot(): LogSnapshot = synchronized(lock) {
        LogSnapshot(ArrayList(records), bytes, evictions)
    }

    /** Release retained lines. Sequence stays monotonic; eviction statistics reset. */
    fun clear() = synchronized(lock) {
        records.clear()
        bytes = 0
        evictions = 0L
    }

    // Called only while holding lock. No public raw-line insertion escape hatch.
    private fun retain(line: SanitizedLogLine): LogRecord {
        check(sequence != Long.MAX_VALUE) { "log sequence exhausted" }
        check(line.utf8Bytes <= policy.config.maxEntryBytes && line.utf8Bytes <= maxBufferBytes)
        // Use subtraction, not an overflowing bytes + line.utf8Bytes sum.
        while (records.size >= maxEntries || bytes > maxBufferBytes - line.utf8Bytes) {
            bytes -= records.removeFirst().utf8Bytes
            if (evictions != Long.MAX_VALUE) evictions++
        }
        val record = LogRecord(++sequence, line.text, line.utf8Bytes, line.truncated)
        records.addLast(record)
        bytes += line.utf8Bytes
        return record
    }
}
