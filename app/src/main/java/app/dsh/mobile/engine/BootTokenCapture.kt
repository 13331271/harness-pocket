package app.dsh.mobile.engine

import java.net.URI

/** One boot/process's private authentication channel, never a diagnostic log. */
class BootTokenCapture(private val expectedPort: Int) {
    init { require(expectedPort in 1..65535) }
    private val lock = Any()
    private var active = true
    private var captured: String? = null

    fun observe(line: String): Boolean = synchronized(lock) {
        if (!active || captured != null || line.length > 32768) return false
        val hit = ANNOUNCEMENT.find(line)?.groupValues?.get(1) ?: return false
        val uri = try { URI(hit) } catch (_: Exception) { return false }
        if (uri.scheme != "http" || uri.host != "127.0.0.1" || uri.port != expectedPort ||
            uri.rawPath != "/" || uri.rawUserInfo != null || uri.rawFragment != null) return false
        val query = uri.rawQuery ?: return false
        if (!query.startsWith("token=") || query.indexOf('&') >= 0 || query.indexOf(';') >= 0) return false
        val token = query.removePrefix("token=")
        if (token.isEmpty() || token.length > 2048 || !TOKEN.matches(token)) return false
        // Rebuild from fixed origin/port plus validated query, never retain a raw line.
        captured = "http://127.0.0.1:$expectedPort/?token=$token"
        true
    }

    fun value(): String? = synchronized(lock) { if (active) captured else null }

    /** Invalidation is permanent for this instance; late output cannot revive it. */
    fun invalidate() = synchronized(lock) {
        active = false
        captured = null
    }

    private companion object {
        val ANNOUNCEMENT = Regex("dsh web: (http://127\\.0\\.0\\.1:[0-9]+/\\?token=[^\\s\\u001b]+)")
        val TOKEN = Regex("(?:[A-Za-z0-9._~+\\-]|%[0-9A-Fa-f]{2})+")
    }
}
