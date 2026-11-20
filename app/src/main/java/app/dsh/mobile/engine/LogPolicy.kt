package app.dsh.mobile.engine

/** Limits apply to retained UTF-8 text, not caller-owned inputs or JVM object overhead. */
data class LogPolicyConfig(
    val maxEntryBytes: Int = 4 * 1024,
    val maxScanChars: Int = 16 * 1024,
) {
    init {
        require(maxEntryBytes in 32..65_536) { "maxEntryBytes must be in 32..65536" }
        require(maxScanChars in 32..262_144) { "maxScanChars must be in 32..262144" }
    }
}

/** Produced only by LogPolicy. No reference to the original input is retained. */
data class SanitizedLogLine internal constructor(
    val text: String,
    val utf8Bytes: Int,
    val truncated: Boolean,
)

/** A closed vocabulary: never replace this with caller-supplied error context. */
enum class EngineFailureKind(val code: String) {
    STARTUP("startup"),
    PROCESS_IO("process-io"),
    PROCESS_EXIT("process-exit"),
    CONFIGURATION("configuration"),
    UNKNOWN("unknown"),
}

/**
 * Bounded, non-regex display-log sanitizer. Safe to share between threads.
 *
 * Marked credentials are redacted; URI-like strings are removed in their entirety.
 * This is NOT a DLP system for arbitrary files, arbitrary encodings, or unlabeled secrets.
 * Input must be a stable CharSequence (normally String); mutable inputs must not change
 * during this call. Neither toString(), subSequence(), nor UTF-8 encoding of the input
 * is used. Only indices below maxScanChars are inspected.
 */
class LogPolicy(val config: LogPolicyConfig = LogPolicyConfig()) {
    fun sanitize(input: CharSequence): SanitizedLogLine {
        val length = input.length
        val limit = minOf(length, config.maxScanChars)
        val output = Utf8Writer(config.maxEntryBytes)
        var cursor = 0
        var boundaryCut = false

        while (cursor < limit && !output.full) {
            val atBoundary = cursor == 0 || !isNameChar(input[cursor - 1])

            if (atBoundary && isUrlStart(input, cursor, limit)) {
                if (!output.appendAscii(URL_MARKER)) break
                cursor = skipUrl(input, cursor, limit)
                continue
            }

            if (atBoundary && isBearerStart(input, cursor, limit)) {
                var valueStart = cursor + 6
                while (valueStart < limit && isHorizontalSpace(input[valueStart])) valueStart++
                if (!appendRange(output, input, cursor, valueStart)) break
                val quote = if (valueStart < limit && isQuote(input[valueStart])) input[valueStart] else null
                if (quote != null && !output.appendCodePoint(quote.code)) break
                if (!output.appendAscii(REDACTED)) break
                cursor = if (quote != null) skipQuoted(input, valueStart, limit)
                    else skipBareToken(input, valueStart, limit)
                if (quote != null && !output.appendCodePoint(quote.code)) break
                continue
            }

            if (atBoundary && isSkStart(input, cursor, limit)) {
                if (!output.appendAscii(REDACTED)) break
                cursor += 3
                while (cursor < limit && isCredentialChar(input[cursor])) cursor++
                continue
            }

            val field = if (atBoundary) findSensitiveField(input, cursor, limit) else null
            if (field != null) {
                if (!appendRange(output, input, cursor, field.valueStart)) break
                val start = field.valueStart
                val quote = if (start < limit && isQuote(input[start])) input[start] else null
                if (quote != null && !output.appendCodePoint(quote.code)) break
                if (!output.appendAscii(REDACTED)) break
                cursor = skipSensitiveValue(input, start, limit, field.kind)
                // Add a closing display quote even when the source quote was unterminated.
                if (quote != null && !output.appendCodePoint(quote.code)) break
                continue
            }

            val first = input[cursor]
            if (isHighSurrogate(first) && cursor + 1 == limit && limit < length) {
                // Do not replace half of an otherwise valid pair at the scan boundary.
                boundaryCut = true
                break
            }
            val point = readPoint(input, cursor, limit)
            if (!output.appendCodePoint(point and POINT_MASK)) break
            cursor += point ushr POINT_SHIFT
        }

        return output.finish(output.full || boundaryCut || cursor < length)
    }

    /**
     * Safe error channel: deliberately NEVER reads message, cause, stack trace, class
     * name, process arguments, environment variables, paths, or URLs from Throwable.
     * Do not append the original Throwable or an environment dump at the call site.
     */
    fun error(
        kind: EngineFailureKind,
        failure: Throwable? = null,
        exitCode: Int? = null,
    ): SanitizedLogLine {
        val causeCode = when (failure) {
            null -> "unspecified"
            is OutOfMemoryError -> "oom"
            is SecurityException -> "security"
            is IllegalArgumentException -> "invalid-argument"
            is java.io.IOException -> "io"
            else -> "other"
        }
        val summary = "error kind=${kind.code} cause=$causeCode" +
            if (exitCode == null) "" else " exit=$exitCode"
        return sanitize(summary)
    }

    private enum class FieldKind { VALUE, AUTHORIZATION, ENVIRONMENT }
    private data class Field(val valueStart: Int, val kind: FieldKind)

    private fun findSensitiveField(input: CharSequence, start: Int, limit: Int): Field? {
        if (!isAsciiLetter(input[start])) return null
        var end = start
        while (end < limit && isNameChar(input[end])) {
            if (end - start >= MAX_FIELD_NAME_CHARS) return null
            end++
        }
        // Common human-readable label in addition to api_key / api-key / apiKey.
        if (normalizedEquals(input, start, end, "api")) {
            var next = end
            while (next < limit && isHorizontalSpace(input[next])) next++
            if (next > end && matchesAscii(input, next, limit, "key")) {
                val after = next + 3
                if (after == limit || !isNameChar(input[after])) end = after
            }
        }
        val kind = when {
            normalizedEquals(input, start, end, "authorization") ||
                normalizedEquals(input, start, end, "proxyauthorization") ||
                normalizedEquals(input, start, end, "cookie") ||
                normalizedEquals(input, start, end, "setcookie") -> FieldKind.AUTHORIZATION
            normalizedEquals(input, start, end, "env") ||
                normalizedEquals(input, start, end, "environment") -> FieldKind.ENVIRONMENT
            VALUE_FIELDS.any { normalizedEquals(input, start, end, it) } -> FieldKind.VALUE
            else -> return null
        }
        var separator = end
        if (separator < limit && isQuote(input[separator])) separator++
        while (separator < limit && isHorizontalSpace(input[separator])) separator++
        if (separator == limit || (input[separator] != ':' && input[separator] != '=')) return null
        var valueStart = separator + 1
        while (valueStart < limit && isHorizontalSpace(input[valueStart])) valueStart++
        return Field(valueStart, kind)
    }

    private fun skipSensitiveValue(
        input: CharSequence,
        start: Int,
        limit: Int,
        kind: FieldKind,
    ): Int {
        if (start >= limit) return limit
        val first = input[start]
        if (isQuote(first)) return skipQuoted(input, start, limit)
        if (first == '{' || first == '[') return skipContainer(input, start, limit)
        if (kind == FieldKind.ENVIRONMENT) return limit // Fail closed for free-form env dumps.
        if (kind == FieldKind.VALUE && isBearerStart(input, start, limit)) {
            var tokenStart = start + 6
            while (tokenStart < limit && isHorizontalSpace(input[tokenStart])) tokenStart++
            return if (tokenStart < limit && isQuote(input[tokenStart])) skipQuoted(input, tokenStart, limit)
                else skipBareToken(input, tokenStart, limit)
        }
        var cursor = start
        while (cursor < limit) {
            val c = input[cursor]
            if (kind == FieldKind.AUTHORIZATION) {
                // Header credentials may contain spaces, commas and semicolon-separated cookies.
                if (c == '\r' || c == '\n' || isQuote(c) || c == '}' || c == ']') break
            } else if (isValueDelimiter(c) || isHorizontalSpace(c)) break
            cursor++
        }
        return cursor
    }

    private fun skipQuoted(input: CharSequence, start: Int, limit: Int): Int {
        val quote = input[start]
        var cursor = start + 1
        var escaped = false
        while (cursor < limit) {
            val c = input[cursor++]
            if (escaped) escaped = false
            else if (c == '\\') escaped = true
            else if (c == quote) return cursor
        }
        return limit
    }

    private fun skipContainer(input: CharSequence, start: Int, limit: Int): Int {
        val closers = CharArray(MAX_CONTAINER_DEPTH)
        closers[0] = if (input[start] == '{') '}' else ']'
        var depth = 1
        var quote: Char? = null
        var escaped = false
        var cursor = start + 1
        while (cursor < limit) {
            val c = input[cursor++]
            if (quote != null) {
                if (escaped) escaped = false
                else if (c == '\\') escaped = true
                else if (c == quote) quote = null
            } else if (isQuote(c)) {
                quote = c
            } else if (c == '{' || c == '[') {
                if (depth == MAX_CONTAINER_DEPTH) return limit // No growing stack.
                closers[depth++] = if (c == '{') '}' else ']'
            } else if (c == '}' || c == ']') {
                if (c != closers[depth - 1]) return limit // Malformed container: fail closed.
                depth--
                if (depth == 0) return cursor
            }
        }
        return limit
    }

    private fun isUrlStart(input: CharSequence, start: Int, limit: Int): Boolean {
        if (matchesAscii(input, start, limit, "www.")) return true
        if (!isAsciiLetter(input[start])) return false
        var cursor = start + 1
        while (cursor < limit && cursor - start <= MAX_SCHEME_CHARS) {
            val c = input[cursor]
            if (c == ':') {
                return cursor + 2 < limit && input[cursor + 1] == '/' && input[cursor + 2] == '/'
            }
            if (!isAsciiLetter(c) && c !in '0'..'9' && c != '+' && c != '-' && c != '.') return false
            cursor++
        }
        return false
    }

    private fun skipUrl(input: CharSequence, start: Int, limit: Int): Int {
        var cursor = start
        while (cursor < limit) {
            val c = input[cursor]
            if (isWhitespace(c) || isQuote(c) || c == '<' || c == '>') break
            cursor++
        }
        return cursor
    }

    private fun isBearerStart(input: CharSequence, start: Int, limit: Int): Boolean =
        matchesAscii(input, start, limit, "bearer") && start + 6 < limit &&
            isHorizontalSpace(input[start + 6])

    private fun isSkStart(input: CharSequence, start: Int, limit: Int): Boolean =
        start + 3 < limit && lowerAscii(input[start]) == 's' &&
            lowerAscii(input[start + 1]) == 'k' &&
            (input[start + 2] == '-' || input[start + 2] == '_') &&
            isCredentialChar(input[start + 3])

    private fun skipBareToken(input: CharSequence, start: Int, limit: Int): Int {
        var cursor = start
        while (cursor < limit && !isWhitespace(input[cursor]) && !isValueDelimiter(input[cursor])) cursor++
        return cursor
    }

    private fun appendRange(output: Utf8Writer, input: CharSequence, start: Int, end: Int): Boolean {
        var cursor = start
        while (cursor < end) {
            val point = readPoint(input, cursor, end)
            if (!output.appendCodePoint(point and POINT_MASK)) return false
            cursor += point ushr POINT_SHIFT
        }
        return true
    }

    // Pack code point + consumed UTF-16 chars into one primitive Int: no per-character objects.
    private fun readPoint(input: CharSequence, index: Int, limit: Int): Int {
        val first = input[index]
        if (isHighSurrogate(first)) {
            if (index + 1 < limit && isLowSurrogate(input[index + 1])) {
                val second = input[index + 1]
                val value = 0x10000 + ((first.code - 0xD800) shl 10) + second.code - 0xDC00
                return value or (2 shl POINT_SHIFT)
            }
            return 0xFFFD or (1 shl POINT_SHIFT)
        }
        if (isLowSurrogate(first) || (first.code < 0x20 && first != '\n' && first != '\t') || first.code == 0x7F) {
            return 0xFFFD or (1 shl POINT_SHIFT)
        }
        return first.code or (1 shl POINT_SHIFT)
    }

    private fun normalizedEquals(input: CharSequence, start: Int, end: Int, expected: String): Boolean {
        var matched = 0
        for (index in start until end) {
            val c = input[index]
            if (c == '-' || c == '_' || isHorizontalSpace(c)) continue
            if (matched == expected.length || lowerAscii(c) != expected[matched++]) return false
        }
        return matched == expected.length
    }

    private fun matchesAscii(input: CharSequence, start: Int, limit: Int, expected: String): Boolean {
        if (limit - start < expected.length) return false
        for (offset in expected.indices) {
            if (lowerAscii(input[start + offset]) != expected[offset]) return false
        }
        return true
    }

    private class Utf8Writer(private val maxBytes: Int) {
        private val text = StringBuilder(minOf(maxBytes, 256))
        private var bytes = 0
        var full: Boolean = false
            private set

        fun appendAscii(value: String): Boolean {
            for (c in value) if (!appendCodePoint(c.code)) return false
            return true
        }

        fun appendCodePoint(point: Int): Boolean {
            val width = utf8Width(point)
            if (bytes > maxBytes - width) {
                full = true
                return false
            }
            if (point <= 0xFFFF) text.append(point.toChar())
            else {
                val adjusted = point - 0x10000
                text.append((0xD800 + (adjusted shr 10)).toChar())
                text.append((0xDC00 + (adjusted and 0x3FF)).toChar())
            }
            bytes += width
            return true
        }

        fun finish(truncated: Boolean): SanitizedLogLine {
            if (truncated) {
                while (bytes > maxBytes - TRUNCATED.length) {
                    val last = text[text.length - 1]
                    val paired = isLowSurrogate(last) && text.length >= 2 && isHighSurrogate(text[text.length - 2])
                    bytes -= if (paired) 4 else utf8Width(last.code)
                    text.delete(text.length - (if (paired) 2 else 1), text.length)
                }
                text.append(TRUNCATED)
                bytes += TRUNCATED.length // ASCII marker.
            }
            return SanitizedLogLine(text.toString(), bytes, truncated)
        }
    }

    private companion object {
        const val REDACTED = "[redacted]"
        const val URL_MARKER = "[url]"
        const val TRUNCATED = "...[truncated]"
        const val POINT_SHIFT = 21
        const val POINT_MASK = 0x1FFFFF
        const val MAX_FIELD_NAME_CHARS = 64
        const val MAX_SCHEME_CHARS = 32
        const val MAX_CONTAINER_DEPTH = 32
        val VALUE_FIELDS = arrayOf(
            "token", "apitoken", "apikey", "xapikey", "accesstoken", "refreshtoken", "idtoken",
            "password", "passwd", "secret", "clientsecret", "privatekey", "credentials",
        )

        fun isAsciiLetter(c: Char): Boolean = c in 'a'..'z' || c in 'A'..'Z'
        fun lowerAscii(c: Char): Char = if (c in 'A'..'Z') (c.code + 32).toChar() else c
        fun isNameChar(c: Char): Boolean = isAsciiLetter(c) || c in '0'..'9' || c == '_' || c == '-'
        fun isCredentialChar(c: Char): Boolean = isNameChar(c)
        fun isHorizontalSpace(c: Char): Boolean = c == ' ' || c == '\t'
        fun isWhitespace(c: Char): Boolean = isHorizontalSpace(c) || c == '\r' || c == '\n'
        fun isQuote(c: Char): Boolean = c == '\'' || c == '"'
        fun isValueDelimiter(c: Char): Boolean =
            c == '\r' || c == '\n' || isQuote(c) || c == ',' || c == ';' || c == '&' || c == '}' || c == ']' || c == '<' || c == '>'
        fun isHighSurrogate(c: Char): Boolean = c.code in 0xD800..0xDBFF
        fun isLowSurrogate(c: Char): Boolean = c.code in 0xDC00..0xDFFF
        fun utf8Width(point: Int): Int = when {
            point <= 0x7F -> 1
            point <= 0x7FF -> 2
            point <= 0xFFFF -> 3
            else -> 4
        }
    }
}
