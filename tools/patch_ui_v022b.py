#!/usr/bin/env python3
"""Refine the v0.2.2 island retirement: keep a single compact settings entry.

Hiding the whole island would also hide the gear (btnMore), which is the only
path from the home screen into Settings. So the capsule goes away and a small
gear button takes its place.
"""
from __future__ import annotations

import io
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app-source")
MAIN = os.path.join(ROOT, "app", "src", "main", "java", "app", "dsh", "mobile", "MainActivity.kt")

OLD = '''        // v0.2.2（用户要求）：引擎状态已迁到「设置 → 引擎」，首页不再常驻状态岛。
        // 可见性本来就只有这一个入口，所以直接收起三种形态；下面按状态推导的
        // 逻辑保留给将来恢复状态岛时使用，当前不会执行到。
        overlay.visibility = View.GONE
        row.visibility = View.GONE
        handle.visibility = View.GONE
        sideHost?.visibility = View.GONE
        return
'''

NEW = '''        // v0.2.2（用户要求）：引擎状态已迁到「设置 → 引擎」，首页不再常驻状态岛。
        // ⚠️ 但状态岛上的齿轮是主界面进入设置的**唯一**入口（btnMore），整条藏掉
        // 会让用户再也进不去设置页 —— 所以收起全部形态，只补一个小齿轮入口。
        overlay.visibility = View.GONE
        row.visibility = View.GONE
        handle.visibility = View.GONE
        sideHost?.visibility = View.GONE
        installSettingsEntry()
        return
'''

FUNC = '''    /**
     * 主界面唯一的设置入口（v0.2.2）。
     *
     * 状态岛退役后它被移除，而齿轮原本只存在于岛上。这里补一个 44dp 的圆形齿轮：
     * 贴右上角、跟随状态栏 insets 下移、点击进设置页；重复调用是空操作。
     */
    private fun installSettingsEntry() {
        val overlay = findViewById<View>(R.id.statusBarOverlay) ?: return
        val container = overlay.parent as? android.view.ViewGroup ?: return
        if (container.findViewWithTag<View>(SETTINGS_ENTRY_TAG) != null) return
        val d = resources.displayMetrics.density
        val size = (44 * d).toInt()
        val button = android.widget.ImageView(this).apply {
            tag = SETTINGS_ENTRY_TAG
            setImageResource(R.drawable.ic_settings)
            setBackgroundResource(R.drawable.bg_island_btn)
            contentDescription = getString(R.string.settings_title)
            setPadding((10 * d).toInt(), (10 * d).toInt(), (10 * d).toInt(), (10 * d).toInt())
            alpha = 0.85f
            setOnClickListener {
                startActivity(Intent(this@MainActivity, SettingsActivity::class.java))
            }
        }
        val lp = android.widget.FrameLayout.LayoutParams(size, size).apply {
            gravity = android.view.Gravity.TOP or android.view.Gravity.END
            topMargin = (8 * d).toInt()
            marginEnd = (8 * d).toInt()
        }
        container.addView(button, lp)
        button.setOnApplyWindowInsetsListener { view, insets ->
            val statusTop = if (android.os.Build.VERSION.SDK_INT >= 30) {
                insets.getInsets(android.view.WindowInsets.Type.statusBars()).top
            } else {
                @Suppress("DEPRECATION")
                insets.systemWindowInsetTop
            }
            val margin = statusTop + (8 * d).toInt()
            (view.layoutParams as? android.widget.FrameLayout.LayoutParams)?.let {
                if (it.topMargin != margin) {
                    it.topMargin = margin
                    view.layoutParams = it
                }
            }
            insets
        }
        button.requestApplyInsets()
    }

'''

ANCHOR = "    private fun renderIslandVisibility() {"
CONST_ANCHOR = "    private var islandCollapsed = false"


def main() -> int:
    text = io.open(MAIN, encoding="utf-8", newline="").read()
    if OLD in text:
        text = text.replace(OLD, NEW, 1)
        print("island block refined")
    elif "installSettingsEntry()" in text:
        print("already refined")
    else:
        print("ERROR: hide block missing", file=sys.stderr)
        return 1
    if "private fun installSettingsEntry()" not in text:
        assert ANCHOR in text
        text = text.replace(ANCHOR, FUNC + ANCHOR, 1)
        print("installSettingsEntry added")
    if "SETTINGS_ENTRY_TAG" not in text.split("private fun installSettingsEntry()")[0]:
        assert CONST_ANCHOR in text
        text = text.replace(
            CONST_ANCHOR,
            CONST_ANCHOR + '\n\n    /** Main-screen gear entry view tag (v0.2.2). */\n    private val SETTINGS_ENTRY_TAG = "main-settings-entry"',
            1,
        )
        print("tag added")
    io.open(MAIN, "w", encoding="utf-8", newline="").write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
