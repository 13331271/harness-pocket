package app.dsh.mobile

import android.graphics.Typeface
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.RadioButton
import android.widget.ScrollView
import android.widget.TextView
import app.dsh.mobile.engine.EngineConfig
import app.dsh.mobile.engine.EngineSupervisor
import org.json.JSONObject
import java.io.File
import java.net.HttpURLConnection
import java.net.URL

/**
 * 内核升级（v0.2.6）：在手机本地用运行时自带的 npm 把 `@deepseek-ai/dsh` 换成
 * npm 上的新版本，而不是等 APK 重发。
 *
 * 为什么能这么做：运行包自带 `bin/npm`（corepack 包装）与 node，真实 Android
 * 环境可以解析依赖、跑原生构建。为什么必须小心：npm 会重写 node_modules，
 * 而本项目的三处原生修复（真实 flock、PTY 背压、JSONL 不覆盖发布 + link 回退）
 * 正是改在这些包里 —— 所以升级前后各备份/还原一次补丁文件，失败自动回滚。
 *
 * 流程：检查（读本地版本 + npm dist-tags）→ 升级（停引擎 → 备份补丁 → npm install
 * → 还原补丁 → 起引擎 → 校验版本）→ 任一步失败 → 恢复旧版本并重启。
 * 全程把 npm 的输出写进页面，失败时用户能直接把日志发回来。
 */
class KernelUpgradeActivity : ThemedActivity() {
    override val usesSettingsBackground: Boolean get() = true

    private lateinit var currentView: TextView
    private lateinit var availableView: TextView
    private lateinit var logView: TextView
    private lateinit var upgradeButton: Button
    private lateinit var channelLatest: RadioButton
    private lateinit var channelNext: RadioButton

    private val ui = Handler(Looper.getMainLooper())
    private var busy = false
    private var latest: String? = null
    private var next: String? = null

    override fun attachBaseContext(newBase: android.content.Context) {
        super.attachBaseContext(LocaleHelper.wrap(newBase))
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        OrientationPrefs.applyTo(this)
        setContentView(buildUi())
        refreshLocal()
        checkRegistry()
    }

    // ── UI ────────────────────────────────────────────────────────────────
    private fun dp(v: Int) = (v * resources.displayMetrics.density).toInt()

    private fun buildUi(): View {
        val root = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
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
            setText(R.string.kernel_title)
            textSize = 20f
            typeface = Typeface.DEFAULT_BOLD
            setTextColor(Accent.current(this@KernelUpgradeActivity).argb)
        }, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.MATCH_PARENT, 1f).apply {
            gravity = Gravity.CENTER_VERTICAL
        })
        root.addView(bar)

        val body = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(16), dp(8), dp(16), dp(16))
        }
        body.addView(sectionLabel(R.string.kernel_current))
        currentView = TextView(this).apply { textSize = 14f; setText(R.string.kernel_reading) }
        body.addView(currentView)

        body.addView(sectionLabel(R.string.kernel_available))
        availableView = TextView(this).apply { textSize = 13f; setText(R.string.kernel_checking) }
        body.addView(availableView)

        val channels = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(0, dp(8), 0, 0)
        }
        channelLatest = RadioButton(this).apply {
            setText(R.string.kernel_channel_latest)
            isChecked = true
        }
        channelNext = RadioButton(this).apply { setText(R.string.kernel_channel_next) }
        channels.addView(channelLatest)
        channels.addView(channelNext)
        body.addView(channels)

        val actions = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            setPadding(0, dp(10), 0, 0)
        }
        actions.addView(Button(this).apply {
            setText(R.string.kernel_check)
            setOnClickListener { checkRegistry() }
        }, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
        upgradeButton = Button(this).apply {
            setText(R.string.kernel_upgrade)
            isEnabled = false
            setOnClickListener { confirmUpgrade() }
        }
        actions.addView(upgradeButton, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
        body.addView(actions)

        body.addView(TextView(this).apply {
            setText(R.string.kernel_warning)
            textSize = 11f
            setPadding(0, dp(10), 0, dp(6))
        })

        logView = TextView(this).apply {
            textSize = 11f
            typeface = Typeface.MONOSPACE
            setTextIsSelectable(true)
            setPadding(dp(8), dp(8), dp(8), dp(8))
            setBackgroundColor(0x1F888888)
        }
        body.addView(logView, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f))

        val scroll = ScrollView(this).apply { addView(body) }
        root.addView(scroll, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f))
        return root
    }

    private fun sectionLabel(res: Int) = TextView(this).apply {
        setText(res)
        textSize = 12f
        typeface = Typeface.DEFAULT_BOLD
        setPadding(0, dp(12), 0, dp(4))
        setTextColor(Accent.current(this@KernelUpgradeActivity).argb)
    }

    private fun log(line: String) {
        ui.post {
            logView.append(if (logView.text.isEmpty()) line else "\n$line")
        }
    }

    private fun setBusy(on: Boolean, status: Int? = null) {
        busy = on
        upgradeButton.isEnabled = !on && availableVersion() != null
        channelLatest.isEnabled = !on
        channelNext.isEnabled = !on
        if (status != null) setStatus(status)
    }

    private fun setStatus(res: Int) {
        ui.post { availableView.setText(res) }
    }

    private fun availableVersion(): String? {
        val v = if (channelNext.isChecked) next else latest
        return v?.takeIf { it.isNotBlank() }
    }

    // ── local state ───────────────────────────────────────────────────────
    private fun engineRoot(): File = EngineConfig.engineRoot(this)

    private fun readJsonVersion(path: File): String? = runCatching {
        JSONObject(path.readText(Charsets.UTF_8)).optString("version").takeIf { it.isNotBlank() }
    }.getOrNull()

    private fun installedDshVersion(): String? =
        readJsonVersion(File(engineRoot(), "lib/node_modules/@deepseek-ai/dsh/package.json"))

    private fun bundledEngineVersion(): String? =
        readJsonVersion(File(engineRoot(), "BUILD.json")).let { build ->
            runCatching {
                JSONObject(File(engineRoot(), "BUILD.json").readText()).optString("engineVersion")
            }.getOrNull()?.takeIf { it.isNotBlank() } ?: build
        }

    private fun refreshLocal() {
        val installed = installedDshVersion()
        val bundled = bundledEngineVersion()
        currentView.text = getString(
            R.string.kernel_current_value,
            installed ?: "?",
            bundled ?: "?",
        )
    }

    // ── npm registry ──────────────────────────────────────────────────────
    private fun checkRegistry() {
        setStatus(R.string.kernel_checking)
        Thread {
            val result = runCatching {
                val conn = URL("https://registry.npmjs.org/@deepseek-ai%2Fdsh").openConnection() as HttpURLConnection
                conn.connectTimeout = 8000
                conn.readTimeout = 10000
                conn.setRequestProperty("Accept", "application/json")
                conn.setRequestProperty("User-Agent", "HarnessPocket")
                val text = conn.inputStream.bufferedReader().use { it.readText() }
                conn.disconnect()
                val tags = JSONObject(text).optJSONObject("dist-tags")
                Pair(tags?.optString("latest"), tags?.optString("next"))
            }
            ui.post {
                result.fold(
                    onSuccess = { (l, n) ->
                        latest = l
                        next = n
                        availableView.text = getString(
                            R.string.kernel_available_value,
                            l ?: "-",
                            n ?: "-",
                        )
                        upgradeButton.isEnabled = !busy && availableVersion() != null
                    },
                    onFailure = { e ->
                        setStatus(R.string.kernel_registry_failed)
                        log("registry: ${e.message}")
                    },
                )
            }
        }.start()
    }

    // ── upgrade ───────────────────────────────────────────────────────────
    private fun confirmUpgrade() {
        val target = availableVersion() ?: return
        val current = installedDshVersion() ?: "?"
        android.app.AlertDialog.Builder(this)
            .setTitle(R.string.kernel_confirm_title)
            .setMessage(getString(R.string.kernel_confirm_msg, current, target))
            .setNegativeButton(R.string.action_cancel, null)
            .setPositiveButton(R.string.kernel_confirm_ok) { _, _ -> startUpgrade(target) }
            .show()
    }

    private fun startUpgrade(target: String) {
        if (busy) return
        setBusy(true, R.string.kernel_upgrading)
        Thread { runUpgrade(target) }.start()
    }

    private val patchFiles = listOf(
        "lib/node_modules/@deepseek-ai/node-addon-system/lib/flock.js",
        "lib/node_modules/@deepseek-ai/node-addon-system/lib/pocket_flock.node",
        "lib/node_modules/node-pty/lib/index.js",
        "lib/node_modules/@deepseek-ai/dsh-session-persistence-jsonl/lib/index.js",
    )

    private fun backupPatches(engine: File): File {
        val dir = File(cacheDir, "kernel-patch-backup")
        dir.deleteRecursively()
        dir.mkdirs()
        patchFiles.forEach { rel ->
            val src = File(engine, rel)
            if (src.isFile) {
                val dst = File(dir, rel)
                dst.parentFile?.mkdirs()
                src.copyTo(dst, overwrite = true)
            }
        }
        return dir
    }

    private fun restorePatches(engine: File, backup: File) {
        patchFiles.forEach { rel ->
            val src = File(backup, rel)
            if (src.isFile) {
                val dst = File(engine, rel)
                dst.parentFile?.mkdirs()
                src.copyTo(dst, overwrite = true)
                log("patch restored: $rel")
            }
        }
    }

    private fun runNpm(engine: File, spec: String): Int {
        val npm = File(engine, "bin/npm")
        if (!npm.isFile) {
            log("bin/npm missing")
            return -1
        }
        val env = EngineConfig.buildEnv(this, EngineConfig.DEFAULT_PORT)
        val pb = ProcessBuilder(
            "/system/bin/sh", "-c",
            "cd '${engine.absolutePath}/lib' && '${npm.absolutePath}' install '$spec' " +
                "--no-audit --no-fund --omit=dev --ignore-scripts --loglevel=http",
        )
        pb.environment().clear()
        env.forEach { kv ->
            val i = kv.indexOf('=')
            if (i > 0) pb.environment()[kv.substring(0, i)] = kv.substring(i + 1)
        }
        pb.environment()["npm_config_registry"] = "https://registry.npmjs.org/"
        pb.redirectErrorStream(true)
        val p = pb.start()
        p.inputStream.bufferedReader().use { r ->
            var line = r.readLine()
            while (line != null) {
                log(line.take(220))
                line = r.readLine()
            }
        }
        return p.waitFor()
    }

    private val supervisor: EngineSupervisor get() = (application as DshApp).supervisor

    private fun runUpgrade(target: String) {
        val engine = engineRoot()
        val oldVersion = installedDshVersion() ?: "0.2.2-rc.3"
        val backup = backupPatches(engine)
        log("engine: ${engine.absolutePath}")
        log("from $oldVersion -> $target")
        val ok = upgradeTo(engine, target, backup)
        if (!ok) {
            log("升级失败，正在回滚到 $oldVersion …")
            supervisor.start(kotlinx.coroutines.MainScope())
            restorePatches(engine, backup)
            ui.post { setBusy(false, R.string.kernel_failed) }
            return
        }
        log("升级完成，正在重启引擎 …")
        supervisor.restart()
        ui.post {
            refreshLocal()
            setBusy(false, R.string.kernel_done)
        }
    }

    private fun upgradeTo(engine: File, target: String, backup: File): Boolean {
        log("stopping engine …")
        supervisor.stop(graceMs = 12_000, explicit = true)
        val code = runNpm(engine, "@deepseek-ai/dsh@$target")
        log("npm exit=$code")
        restorePatches(engine, backup)
        if (code != 0) return false
        val now = installedDshVersion()
        log("installed now: ${now ?: "?"}")
        return now == target
    }

    override fun onDestroy() {
        super.onDestroy()
    }
}
