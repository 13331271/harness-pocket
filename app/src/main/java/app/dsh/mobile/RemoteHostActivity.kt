package app.dsh.mobile

import android.annotation.SuppressLint
import android.graphics.Typeface
import android.os.Bundle
import android.text.InputType
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Button
import android.widget.EditText
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.TextView
import java.net.HttpURLConnection
import java.net.URL

/**
 * Remote host: open a DeepSeek Harness Web UI that runs on another machine.
 *
 * Why a separate screen instead of a switch on the local engine: the local
 * engine owns a strictly verified boot contract (token capture, generation
 * tracking, single-owner process recovery). Turning the main WebView into a
 * remote client would put an unverified URL behind that same contract. This
 * screen is isolated instead - it never starts, stops or adopts the local
 * engine, and it keeps its own small WebView.
 *
 * Scope of the address field: whatever URL actually reaches the other machine's
 * `dsh web` - a LAN address when that host listens beyond loopback, an SSH local
 * forward (http://127.0.0.1:PORT) when it does not, or a reverse proxy. The token
 * is the one printed to the host's startup log; it is stored in this app's
 * private preferences and sent only to the address above.
 */
class RemoteHostActivity : ThemedActivity() {
    /** Belongs to the settings family: honours the "settings background" option. */
    override val usesSettingsBackground: Boolean get() = true

    private lateinit var addressInput: EditText
    private lateinit var tokenInput: EditText
    private lateinit var statusView: TextView
    private lateinit var connectButton: Button
    private lateinit var panel: View
    private lateinit var webView: WebView

    private val prefs by lazy { getSharedPreferences(PREFS, MODE_PRIVATE) }

    override fun attachBaseContext(newBase: android.content.Context) {
        super.attachBaseContext(LocaleHelper.wrap(newBase))
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        OrientationPrefs.applyTo(this)
        setContentView(buildUi())
        addressInput.setText(prefs.getString(KEY_ADDRESS, "").orEmpty())
        tokenInput.setText(prefs.getString(KEY_TOKEN, "").orEmpty())
        addressInput.setSelection(addressInput.text.length)
    }

    // 鈹€鈹€ UI 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
    private fun dp(value: Int): Int = (value * resources.displayMetrics.density).toInt()

    private fun buildUi(): View {
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
        }

        val bar = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(4), 0, dp(12), 0)
        }
        bar.addView(ImageView(this).apply {
            setImageResource(R.drawable.ic_back)
            setPadding(dp(12), dp(12), dp(12), dp(12))
            contentDescription = getString(R.string.settings_back)
            setOnClickListener { finish() }
        }, LinearLayout.LayoutParams(dp(48), dp(48)))
        bar.addView(TextView(this).apply {
            setText(R.string.remote_host_title)
            textSize = 20f
            typeface = Typeface.DEFAULT_BOLD
            setTextColor(Accent.current(this@RemoteHostActivity).argb)
        }, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.MATCH_PARENT, 1f).apply {
            gravity = Gravity.CENTER_VERTICAL
        })
        root.addView(bar)

        val scroll = android.widget.ScrollView(this)
        val body = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(16), dp(8), dp(16), dp(24))
        }

        body.addView(hintText(R.string.remote_host_intro))

        body.addView(labelText(R.string.remote_host_address_label))
        addressInput = makeInput(InputType.TYPE_TEXT_VARIATION_URI, R.string.remote_host_address_hint)
        body.addView(addressInput)

        body.addView(labelText(R.string.remote_host_token_label))
        tokenInput = makeInput(InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_VISIBLE_PASSWORD,
            R.string.remote_host_token_hint)
        body.addView(tokenInput)

        val actions = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            setPadding(0, dp(14), 0, 0)
        }
        actions.addView(Button(this).apply {
            setText(R.string.remote_host_test)
            setOnClickListener { testConnection() }
        }, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
        connectButton = Button(this).apply {
            setText(R.string.remote_host_connect)
            setOnClickListener { connect() }
        }
        actions.addView(connectButton, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
        body.addView(actions)

        statusView = TextView(this).apply {
            textSize = 12f
            setPadding(0, dp(10), 0, dp(6))
            setTextColor(Accent.current(this@RemoteHostActivity).argb)
        }
        body.addView(statusView)

        body.addView(hintText(R.string.remote_host_security))
        body.addView(hintText(R.string.remote_host_keepalive))

        scroll.addView(body)
        panel = scroll
        root.addView(scroll, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f))

        webView = buildWebView()
        root.addView(webView, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f))
        webView.visibility = View.GONE
        return root
    }

    private fun hintText(res: Int): TextView = TextView(this).apply {
        setText(res)
        textSize = 12f
        setPadding(0, dp(10), 0, dp(4))
    }

    private fun labelText(res: Int): TextView = TextView(this).apply {
        setText(res)
        textSize = 13f
        typeface = Typeface.DEFAULT_BOLD
        setPadding(0, dp(14), 0, dp(6))
        setTextColor(Accent.current(this@RemoteHostActivity).argb)
    }

    private fun makeInput(inputType: Int, hintRes: Int): EditText = EditText(this).apply {
        this.inputType = inputType
        setHint(hintRes)
        setSingleLine()
        textSize = 14f
        setPadding(dp(12), dp(10), dp(12), dp(10))
        setBackgroundResource(R.drawable.bg_voice_input)
    }

    @SuppressLint("SetJavaScriptEnabled")
    private fun buildWebView(): WebView = WebView(this).apply {
        settings.javaScriptEnabled = true
        settings.domStorageEnabled = true
        settings.databaseEnabled = true
        settings.mediaPlaybackRequiresUserGesture = false
        settings.cacheMode = WebSettings.LOAD_DEFAULT
        // A remote page gets no access to app-private files or local content.
        settings.allowFileAccess = false
        settings.allowContentAccess = false
        settings.mixedContentMode = WebSettings.MIXED_CONTENT_NEVER_ALLOW
        webViewClient = object : WebViewClient() {
            override fun onReceivedError(
                view: WebView,
                request: WebResourceRequest,
                error: WebResourceError,
            ) {
                if (request.isForMainFrame) {
                    showStatus(getString(R.string.remote_host_load_failed, error.description.toString()))
                }
            }
        }
        webChromeClient = WebChromeClient()
    }

    // 鈹€鈹€ Actions 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
    /** Normalises the typed address into something the WebView can load. */
    private fun targetUrl(): String? =
        RemoteHostUrl.build(addressInput.text.toString(), tokenInput.text.toString())

    private fun connect() {
        val url = targetUrl()
        if (url == null) {
            showStatus(getString(R.string.remote_host_need_address))
            return
        }
        prefs.edit()
            .putString(KEY_ADDRESS, addressInput.text.toString().trim())
            .putString(KEY_TOKEN, tokenInput.text.toString().trim())
            .apply()
        panel.visibility = View.GONE
        webView.visibility = View.VISIBLE
        webView.loadUrl(url)
        showStatus(getString(R.string.remote_host_connecting, url))
    }

    /**
     * Reachability probe. Runs off the UI thread; a HEAD first, falling back to
     * GET because some proxies reject HEAD. The result is reported verbatim so a
     * wrong port and a wrong token do not look alike.
     */
    private fun testConnection() {
        val url = targetUrl()
        if (url == null) {
            showStatus(getString(R.string.remote_host_need_address))
            return
        }
        showStatus(getString(R.string.remote_host_testing))
        Thread {
            val result = runCatching {
                val conn = URL(url).openConnection() as HttpURLConnection
                conn.connectTimeout = 6000
                conn.readTimeout = 6000
                conn.instanceFollowRedirects = true
                conn.requestMethod = "GET"
                conn.setRequestProperty("User-Agent", "HarnessPocket")
                val code = conn.responseCode
                conn.disconnect()
                code
            }
            runOnUiThread {
                result.fold(
                    onSuccess = { code ->
                        showStatus(
                            if (code in 200..399) {
                                getString(R.string.remote_host_test_ok, code)
                            } else {
                                getString(R.string.remote_host_test_bad, code)
                            },
                        )
                    },
                    onFailure = { e ->
                        showStatus(getString(R.string.remote_host_test_failed, e.message.orEmpty()))
                    },
                )
            }
        }.start()
    }

    private fun showStatus(text: String) {
        statusView.text = text
        statusView.visibility = View.VISIBLE
    }

    // 鈹€鈹€ Back navigation 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
    @Suppress("DEPRECATION")
    override fun onBackPressed() {
        if (webView.visibility == View.VISIBLE) {
            if (webView.canGoBack()) {
                webView.goBack()
                return
            }
            // Leave the remote page; keep the typed address for next time.
            webView.visibility = View.GONE
            panel.visibility = View.VISIBLE
            return
        }
        super.onBackPressed()
    }

    override fun onDestroy() {
        if (this::webView.isInitialized) {
            webView.stopLoading()
            webView.loadUrl("about:blank")
            webView.destroy()
        }
        super.onDestroy()
    }

    private companion object {
        const val PREFS = "remote_host"
        const val KEY_ADDRESS = "address"
        const val KEY_TOKEN = "token"
    }
}

