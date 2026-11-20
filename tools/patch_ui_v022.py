#!/usr/bin/env python3
"""v0.2.2 UI pass:
  1. Retire the home-screen engine status island (status moves to Settings).
  2. Show the live engine state in Settings' engine row.
  3. Point the version strings at the bundled engine 0.2.2-rc.5.
"""
from __future__ import annotations

import io
import os
import re
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app-source")
JAVA = os.path.join(ROOT, "app", "src", "main", "java", "app", "dsh", "mobile")
RES = os.path.join(ROOT, "app", "src", "main", "res")

MAIN = os.path.join(JAVA, "MainActivity.kt")
SETTINGS = os.path.join(JAVA, "SettingsActivity.kt")

HIDE_BLOCK = '''        // v0.2.2（用户要求）：引擎状态已迁到「设置 → 引擎」，首页不再常驻状态岛。
        // 可见性本来就只有这一个入口，所以直接收起三种形态；下面按状态推导的
        // 逻辑保留给将来恢复状态岛时使用，当前不会执行到。
        overlay.visibility = View.GONE
        row.visibility = View.GONE
        handle.visibility = View.GONE
        sideHost?.visibility = View.GONE
        return
'''

HELPER = '''    /**
     * 引擎行副标题：实时反映引擎状态（v0.2.2）。
     *
     * 首页状态岛退役后，这里是用户唯一能看到「引擎到底跑没跑」的地方，
     * 所以每次回到设置页都刷新一次，而不是沿用布局里的静态文案。
     */
    private fun refreshEngineRow() {
        val sup = (application as DshApp).supervisor
        val label = findViewById<TextView>(R.id.valEngine) ?: return
        label.text = when (val state = sup.state.value) {
            is EngineSupervisor.State.Healthy -> getString(R.string.setting_engine_sub_ready, sup.healthyPort)
            is EngineSupervisor.State.Starting,
            is EngineSupervisor.State.Installing -> getString(R.string.setting_engine_sub_starting)
            is EngineSupervisor.State.SafeMode -> getString(R.string.setting_engine_sub_safe)
            is EngineSupervisor.State.Backoff,
            is EngineSupervisor.State.Failed,
            is EngineSupervisor.State.Stopped -> getString(R.string.setting_engine_sub_not_running)
            else -> state.toString()
        }
    }

'''

STRINGS = {
    "values": {
        "setting_engine_sub_ready": "Ready · port %1$d",
        "setting_engine_sub_starting": "Starting…",
        "setting_engine_sub_safe": "Safe mode",
        "setting_engine_sub_not_running": "Not running — tap for details",
    },
    "values-zh-rCN": {
        "setting_engine_sub_ready": "已就绪 · 端口 %1$d",
        "setting_engine_sub_starting": "启动中…",
        "setting_engine_sub_safe": "安全模式",
        "setting_engine_sub_not_running": "未运行，点此看详情",
    },
    "values-de": {
        "setting_engine_sub_ready": "Bereit · Port %1$d",
        "setting_engine_sub_starting": "Startet…",
        "setting_engine_sub_safe": "Sicherer Modus",
        "setting_engine_sub_not_running": "Läuft nicht – tippen für Details",
    },
    "values-pt-rBR": {
        "setting_engine_sub_ready": "Pronto · porta %1$d",
        "setting_engine_sub_starting": "Iniciando…",
        "setting_engine_sub_safe": "Modo seguro",
        "setting_engine_sub_not_running": "Não está rodando — toque para detalhes",
    },
    "values-ru": {
        "setting_engine_sub_ready": "Готов · порт %1$d",
        "setting_engine_sub_starting": "Запуск…",
        "setting_engine_sub_safe": "Безопасный режим",
        "setting_engine_sub_not_running": "Не запущен — нажмите для подробностей",
    },
    "values-th": {
        "setting_engine_sub_ready": "พร้อมใช้งาน · พอร์ต %1$d",
        "setting_engine_sub_starting": "กำลังเริ่ม…",
        "setting_engine_sub_safe": "โหมดปลอดภัย",
        "setting_engine_sub_not_running": "ไม่ได้ทำงาน — แตะเพื่อดูรายละเอียด",
    },
}


def patch_main() -> None:
    text = io.open(MAIN, encoding="utf-8", newline="").read()
    anchor = """        val handle = findViewById<View>(R.id.handleBar) ?: return
        val side = islandDock != IslandDock.TOP"""
    if HIDE_BLOCK in text:
        print("main: already patched")
        return
    assert anchor in text, "renderIslandVisibility anchor missing"
    text = text.replace(anchor, anchor.replace("        val side = islandDock != IslandDock.TOP",
                                               HIDE_BLOCK + "        @Suppress(\"UNREACHABLE_CODE\")\n        val side = islandDock != IslandDock.TOP"), 1)
    io.open(MAIN, "w", encoding="utf-8", newline="").write(text)
    print("main: island retired")


def patch_settings() -> None:
    text = io.open(SETTINGS, encoding="utf-8", newline="").read()
    if "refreshEngineRow" in text:
        print("settings: already patched")
    else:
        anchor = """        findViewById<LinearLayout>(R.id.rowEngine).setOnClickListener {
            showEngineStatusDialog()
        }
"""
        assert anchor in text, "rowEngine anchor missing"
        text = text.replace(anchor, anchor + "        refreshEngineRow()\n", 1)

        helper_anchor = "    /** 首页顶部引擎状态栏移入设置后的弹出对话框：显示引擎当前状态与端口，并可重启引擎。 */"
        assert helper_anchor in text
        text = text.replace(helper_anchor, HELPER + helper_anchor, 1)

        resume_anchor = """        refreshUpdateEntrySub()
        refreshDeveloperOptionsEntry()"""
        assert resume_anchor in text
        text = text.replace(resume_anchor, """        refreshUpdateEntrySub()
        refreshEngineRow()
        refreshDeveloperOptionsEntry()""", 1)
        io.open(SETTINGS, "w", encoding="utf-8", newline="").write(text)
        print("settings: live engine row wired")


def patch_strings() -> None:
    for loc, items in STRINGS.items():
        path = os.path.join(RES, loc, "strings.xml")
        text = io.open(path, encoding="utf-8", newline="").read()
        block = "".join(f'    <string name="{k}">{v}</string>\n' for k, v in items.items())
        idx = text.rfind("</resources>")
        text = text[:idx] + block + text[idx:]
        # Engine version: 0.2.2-rc.3 (0.2.2-rc.5 runtime pending WSL build) -> 0.2.2-rc.5
        text, n = re.subn(r"0\.2\.2-rc\.3 \(0\.2\.2-rc\.5[^)]*\)", "0.2.2-rc.5", text)
        io.open(path, "w", encoding="utf-8", newline="").write(text)
        print(f"{loc}: +{len(items)} keys, version-fix={n}")


def main() -> int:
    patch_main()
    patch_settings()
    patch_strings()
    return 0


if __name__ == "__main__":
    sys.exit(main())
