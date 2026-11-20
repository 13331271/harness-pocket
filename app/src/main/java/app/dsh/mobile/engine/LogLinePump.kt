package app.dsh.mobile.engine

import java.io.Reader

/** Bounded diagnostic line assembly; preserves split UTF-16 pairs and CRLF. */
object LogLinePump {
    fun read(
        reader: Reader,
        maxChars: Int = 32768,
        isClosed: () -> Boolean = { false },
        emit: (String) -> Unit,
    ) {
        require(maxChars in 32..262144)
        val block = CharArray(4096)
        val pending = StringBuilder(minOf(maxChars, 256))
        var truncated = false
        var suppressLf = false
        fun line() {
            if (truncated && pending.isNotEmpty() && pending.last().isHighSurrogate()) {
                pending.setLength(pending.length - 1)
            }
            val text = pending.toString() + if (truncated) "...[line truncated]" else ""
            emit(text)
            pending.setLength(0)
            truncated = false
        }
        while (!isClosed()) {
            val count = reader.read(block)
            if (count < 0) break
            if (count == 0) continue
            for (index in 0 until count) {
                val char = block[index]
                if (char == '\n' || char == '\r') {
                    if (char == '\n' && suppressLf) {
                        suppressLf = false
                        continue
                    }
                    line()
                    suppressLf = char == '\r'
                } else {
                    suppressLf = false
                    if (pending.length < maxChars) pending.append(char) else truncated = true
                }
            }
        }
        if (pending.isNotEmpty() || truncated) line()
    }
}
