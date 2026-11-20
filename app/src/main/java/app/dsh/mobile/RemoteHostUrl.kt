package app.dsh.mobile

/**
 * Pure address handling for the remote-host screen.
 *
 * Kept out of [RemoteHostActivity] on purpose: URL normalisation is exactly the
 * part that silently breaks (missing scheme, token glued on twice, whitespace
 * from the keyboard), and it must be testable without an Android device.
 */
object RemoteHostUrl {

    /** Normalises what the user typed. Returns null when the input is unusable. */
    fun normalize(raw: String): String? {
        val trimmed = raw.trim()
        if (trimmed.isEmpty()) return null
        val withScheme =
            if (trimmed.startsWith("http://") || trimmed.startsWith("https://")) trimmed
            else "http://$trimmed"
        // A keyboard-filled address may carry spaces or newlines; sending those to
        // java.net.URL fails with an opaque error, so reject early and explain.
        if (withScheme.any { it.isWhitespace() }) return null
        // A scheme-only string ("http://") is not a target.
        val afterScheme = withScheme.substringAfter("://")
        if (afterScheme.isEmpty()) return null
        return withScheme
    }

    /** Appends the boot token as a query parameter, preserving an existing query. */
    fun withToken(url: String, token: String): String {
        val trimmed = token.trim()
        if (trimmed.isEmpty()) return url
        val separator = if (url.contains('?')) '&' else '?'
        return "$url$separator" + "token=" + trimmed
    }

    /** Normalise + token in one step; null when the address is unusable. */
    fun build(address: String, token: String): String? =
        normalize(address)?.let { withToken(it, token) }

    /** Host and port for the status line, without credentials or query. */
    fun origin(url: String): String =
        url.substringAfter("://", url).substringBefore('/').substringBefore('?')
}
