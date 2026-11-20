package app.dsh.mobile

import android.app.AlertDialog
import android.content.ClipData
import android.content.ClipboardManager
import android.os.Bundle
import android.os.SystemClock
import android.widget.ScrollView
import android.widget.ImageView
import android.widget.TextView
import android.widget.Toast
import app.dsh.mobile.engine.RepoConfig
import app.dsh.mobile.update.AppUpdatePrefs
import app.dsh.mobile.update.AppUpdateScheduler
import app.dsh.mobile.update.UpdateDialogs

/**
 * About page (MIUI style): app identity card, intro, source link, licence notice.
 *
 * Identity policy: the product ships under its own name and links only to its
 * own repository plus the upstream DeepSeek Harness project. Third-party author
 * handles, community groups and star prompts are deliberately absent; the
 * mandatory copyright/licence notices live in assets/legal and are shown here.
 */
class AboutActivity : ThemedActivity() {
    /** Belongs to the settings family: honours the "settings background" option. */
    override val usesSettingsBackground: Boolean get() = true


    override fun attachBaseContext(newBase: android.content.Context) {
        super.attachBaseContext(LocaleHelper.wrap(newBase))
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        OrientationPrefs.applyToSettingsPage(this)
        setContentView(R.layout.activity_about)

        // Normalise stale "downloaded / pending install" state; the readiness
        // dialog in onResume depends on a clean state.
        AppUpdatePrefs.clearStaleInstallState(this)

        findViewById<ImageView>(R.id.btnBack).setOnClickListener { finish() }
        findViewById<TextView>(R.id.txtVersion).text =
            getString(R.string.about_version, versionName())

        var versionTapCount = 0
        var firstVersionTapAt = 0L
        findViewById<TextView>(R.id.txtVersion).setOnClickListener {
            if (DeveloperModePrefs.isEnabled(this)) return@setOnClickListener
            val now = SystemClock.elapsedRealtime()
            if (versionTapCount == 0 || now - firstVersionTapAt > 5_000L) { versionTapCount = 0; firstVersionTapAt = now }
            versionTapCount += 1
            if (versionTapCount >= 7) {
                versionTapCount = 0
                DeveloperModePrefs.setEnabled(this, true)
                Toast.makeText(this, R.string.developer_options_unlocked, Toast.LENGTH_LONG).show()
            }
        }

        val repo = RepoConfig.REPO
        findViewById<TextView>(R.id.txtRepo).text = "github.com/" + repo

        // Source link: hand off to the system browser instead of asking the user
        // to copy/paste. Falls back to the clipboard when no browser exists.
        findViewById<android.view.View>(R.id.rowRepo).setOnClickListener {
            val url = "https://github.com/" + repo
            runCatching {
                startActivity(android.content.Intent(android.content.Intent.ACTION_VIEW, android.net.Uri.parse(url)))
            }.onFailure {
                val cm = getSystemService(CLIPBOARD_SERVICE) as ClipboardManager
                cm.setPrimaryClip(ClipData.newPlainText("harness-pocket", url))
                Toast.makeText(this, R.string.about_copied, Toast.LENGTH_SHORT).show()
            }
        }

        findViewById<android.view.View>(R.id.rowLicenses).setOnClickListener { showLicenses() }
    }

    /**
     * Licence viewer: the shipped notices are the legally required attribution
     * for the MIT/Apache-2.0/GPL-2.0 components inside the APK. Text comes from
     * assets/legal so the shipped copy and the repository copy cannot diverge.
     */
    private fun showLicenses() {
        val body = listOf("LICENSE.txt", "NOTICE.txt").joinToString("\n\n") { name ->
            runCatching {
                assets.open("legal/$name").bufferedReader(Charsets.UTF_8).use { it.readText() }
            }.getOrElse { getString(R.string.about_licenses_missing, name) }
        }
        val pad = (20 * resources.displayMetrics.density).toInt()
        val view = ScrollView(this).apply {
            addView(TextView(this@AboutActivity).apply {
                text = body
                textSize = 12f
                setPadding(pad, pad, pad, pad)
                setTextIsSelectable(true)
                typeface = android.graphics.Typeface.MONOSPACE
            })
        }
        AlertDialog.Builder(this)
            .setTitle(R.string.about_licenses)
            .setView(view)
            .setPositiveButton(R.string.close, null)
            .show()
    }

    override fun onResume() {
        super.onResume()
        // Re-align the page when the appearance tab changed orientation/scale.
        OrientationPrefs.applyToSettingsPage(this)
        // Back to the foreground: top up the update check if 24h elapsed (§6).
        AppUpdateScheduler.onForeground(this)
        UpdateDialogs.maybeShow(this)
    }

    private fun versionName(): String =
        runCatching { packageManager.getPackageInfo(packageName, 0).versionName }
            .getOrNull() ?: "?"
}
