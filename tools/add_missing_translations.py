#!/usr/bin/env python3
"""Add the missing translations for de / pt-BR / ru / th.

Keys covered: the 0.2.0 additions (remote host, licence page, ASR notice) and
six keys that were already missing before this release. Values are UI-length
translations of the English source; placeholders keep their original format.
"""
from __future__ import annotations

import io
import os
import sys

RES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app-source",
                   "app", "src", "main", "res")

DATA = {
    "values-de": {
        "about_licenses": "Open-Source-Lizenzen",
        "about_licenses_sub": "Lizenz- und Drittanbieterhinweise dieser Version",
        "about_licenses_missing": "Fehlende Datei: %1$s",
        "asrapp_not_bundled": "Diese Version liefert die Erkennungs-App nicht mit. Ist sie bereits installiert, nutze sie direkt; Sprachaufnahme funktioniert auch über den unten konfigurierten OpenAI-kompatiblen ASR-Endpunkt.",
        "dialog_engine_message": "Status: %1$s\\nPort: %2$d\\nEingebauter Motor: 0.2.2-rc.3 (0.2.2-rc.5-Laufzeit wartet auf WSL-Build)",
        "dialog_engine_title": "Motor",
        "pocket_linux_unavailable": "Diese Version enthält den nativen Android-Harness-Motor. Der optionale proprietäre Linux-Container und Grafikserver sind nicht enthalten. Nutze native Arbeitsbereiche und kompatible Android-Werkzeuge.",
        "pocket_manual_update_only": "Diese lokale Version wird per APK manuell aktualisiert. Automatisches Ersetzen von App und Laufzeit ist deaktiviert, um Daten und native Korrekturen zu erhalten.",
        "remote_host_address_hint": "http://192.168.1.10:3080",
        "remote_host_address_label": "Adresse",
        "remote_host_connect": "Verbinden",
        "remote_host_connecting": "Lade %1$s",
        "remote_host_intro": "Öffnet die Weboberfläche eines DeepSeek Harness auf einem anderen Gerät. Diese Seite ist vom lokalen Motor unabhängig: Sie startet und stoppt ihn nicht, und Eingaben gehen ausschließlich an die angegebene Adresse.",
        "remote_host_keepalive": "Tipp: Halte den Host wach. Läuft er auf einem Telefon, erlaube der App die Hintergrundausführung, sonst bricht die Seite beim Sperren des Bildschirms ab.",
        "remote_host_load_failed": "Laden fehlgeschlagen: %1$s",
        "remote_host_need_address": "Bitte zuerst eine Adresse eingeben.",
        "remote_host_security": "Sicherheit: Verbinde dich nur mit einem Host, den du kontrollierst. Unverschlüsseltes http:// kann in gemeinsam genutzten Netzen mitgelesen werden; nutze bevorzugt eine SSH-Weiterleitung.",
        "remote_host_test": "Testen",
        "remote_host_test_bad": "Host antwortet mit HTTP %1$d. Prüfe Port und Pfad der Weboberfläche.",
        "remote_host_test_failed": "Host nicht erreichbar: %1$s",
        "remote_host_test_ok": "Erreichbar (HTTP %1$d). Öffnet die Seite trotzdem nicht, ist meist das Token falsch.",
        "remote_host_testing": "Wird getestet…",
        "remote_host_title": "Remote-Host",
        "remote_host_token_hint": "Token aus dem Startprotokoll des Hosts",
        "remote_host_token_label": "Zugriffstoken (optional)",
        "setting_engine": "Motor",
        "setting_engine_sub_idle": "Motor bereit · 3080",
        "setting_remote_host": "Remote-Host",
        "setting_remote_host_sub": "Ein DSH auf deinem Computer oder Server öffnen",
    },
    "values-pt-rBR": {
        "about_licenses": "Licenças de código aberto",
        "about_licenses_sub": "Avisos de licença e de terceiros desta versão",
        "about_licenses_missing": "Arquivo ausente: %1$s",
        "asrapp_not_bundled": "Esta versão não distribui o aplicativo de reconhecimento. Se ele já estiver instalado, use-o diretamente; a entrada de voz também funciona pelo endpoint ASR compatível com OpenAI configurado abaixo.",
        "dialog_engine_message": "Status: %1$s\\nPorta: %2$d\\nMotor integrado: 0.2.2-rc.3 (runtime 0.2.2-rc.5 aguardando build no WSL)",
        "dialog_engine_title": "Motor",
        "pocket_linux_unavailable": "Esta versão inclui o motor Harness nativo do Android. O contêiner Linux proprietário opcional e o servidor gráfico não estão incluídos. Use espaços de trabalho nativos e ferramentas Android compatíveis.",
        "pocket_manual_update_only": "Esta versão local é atualizada manualmente pelo APK. A substituição automática do aplicativo e do runtime está desativada para preservar os dados e as correções nativas.",
        "remote_host_address_hint": "http://192.168.1.10:3080",
        "remote_host_address_label": "Endereço",
        "remote_host_connect": "Conectar",
        "remote_host_connecting": "Carregando %1$s",
        "remote_host_intro": "Abre a interface web de um DeepSeek Harness em outra máquina. Esta tela é independente do motor local: não o inicia nem o interrompe, e o que você digita vai apenas para o endereço informado.",
        "remote_host_keepalive": "Dica: mantenha o host acordado. Se ele roda em um celular, permita a execução em segundo plano; caso contrário a página cai quando a tela apaga.",
        "remote_host_load_failed": "Falha ao carregar: %1$s",
        "remote_host_need_address": "Informe um endereço primeiro.",
        "remote_host_security": "Segurança: conecte apenas a um host que você controla. HTTP sem criptografia pode ser lido por terceiros em redes compartilhadas; prefira um encaminhamento SSH.",
        "remote_host_test": "Testar",
        "remote_host_test_bad": "O host respondeu HTTP %1$d. Verifique a porta e o caminho da interface web.",
        "remote_host_test_failed": "Não foi possível alcançar o host: %1$s",
        "remote_host_test_ok": "Acessível (HTTP %1$d). Se a página ainda não abrir, provavelmente o token está errado.",
        "remote_host_testing": "Testando…",
        "remote_host_title": "Host remoto",
        "remote_host_token_hint": "Token impresso no log de inicialização do host",
        "remote_host_token_label": "Token de acesso (opcional)",
        "setting_engine": "Motor",
        "setting_engine_sub_idle": "Motor pronto · 3080",
        "setting_remote_host": "Host remoto",
        "setting_remote_host_sub": "Abrir um DSH no seu computador ou servidor",
    },
    "values-ru": {
        "about_licenses": "Открытые лицензии",
        "about_licenses_sub": "Лицензии и уведомления третьих сторон для этой сборки",
        "about_licenses_missing": "Отсутствует файл: %1$s",
        "asrapp_not_bundled": "В этой сборке нет приложения-распознавателя. Если оно уже установлено, используйте его напрямую; ввод голоса также работает через совместимый с OpenAI ASR-эндпоинт, настроенный ниже.",
        "dialog_engine_message": "Состояние: %1$s\\nПорт: %2$d\\nВстроенный движок: 0.2.2-rc.3 (среда 0.2.2-rc.5 ожидает сборки в WSL)",
        "dialog_engine_title": "Движок",
        "pocket_linux_unavailable": "Эта сборка содержит нативный движок Harness для Android. Необязательный проприетарный контейнер Linux и графический сервер не включены. Используйте нативные рабочие области и совместимые инструменты Android.",
        "pocket_manual_update_only": "Эта локальная сборка обновляется вручную через APK. Автоматическая замена приложения и среды отключена, чтобы сохранить данные и нативные исправления.",
        "remote_host_address_hint": "http://192.168.1.10:3080",
        "remote_host_address_label": "Адрес",
        "remote_host_connect": "Подключиться",
        "remote_host_connecting": "Загрузка %1$s",
        "remote_host_intro": "Открывает веб-интерфейс DeepSeek Harness на другой машине. Этот экран не зависит от локального движка: он его не запускает и не останавливает, а введённые данные отправляются только по указанному адресу.",
        "remote_host_keepalive": "Совет: не давайте хосту засыпать. Если хост — телефон, разрешите приложению работу в фоне, иначе страница оборвётся при выключении экрана.",
        "remote_host_load_failed": "Не удалось загрузить: %1$s",
        "remote_host_need_address": "Сначала укажите адрес.",
        "remote_host_security": "Безопасность: подключайтесь только к своему хосту. Открытый http:// в общей сети может быть прочитан другими; предпочитайте SSH-туннель.",
        "remote_host_test": "Проверить",
        "remote_host_test_bad": "Хост ответил HTTP %1$d. Проверьте порт и путь к веб-интерфейсу.",
        "remote_host_test_failed": "Хост недоступен: %1$s",
        "remote_host_test_ok": "Доступен (HTTP %1$d). Если страница всё равно не открывается, скорее всего неверен токен.",
        "remote_host_testing": "Проверка…",
        "remote_host_title": "Удалённый хост",
        "remote_host_token_hint": "Токен из журнала запуска хоста",
        "remote_host_token_label": "Токен доступа (необязательно)",
        "setting_engine": "Движок",
        "setting_engine_sub_idle": "Движок готов · 3080",
        "setting_remote_host": "Удалённый хост",
        "setting_remote_host_sub": "Открыть DSH на компьютере или сервере",
    },
    "values-th": {
        "about_licenses": "สัญญาอนุญาตโอเพนซอร์ส",
        "about_licenses_sub": "ประกาศสัญญาอนุญาตและบุคคลที่สามของบิลด์นี้",
        "about_licenses_missing": "ไม่พบไฟล์: %1$s",
        "asrapp_not_bundled": "บิลด์นี้ไม่ได้แจกแอปตรวจจับเสียง หากติดตั้งไว้แล้วให้เปิดใช้ได้เลย การป้อนเสียงยังใช้ปลายทาง ASR ที่รองรับ OpenAI ซึ่งตั้งค่าไว้ด้านล่างได้",
        "dialog_engine_message": "สถานะ: %1$s\\nพอร์ต: %2$d\\nเอนจินในตัว: 0.2.2-rc.3 (รันไทม์ 0.2.2-rc.5 รอสร้างใน WSL)",
        "dialog_engine_title": "เอนจิน",
        "pocket_linux_unavailable": "บิลด์นี้มีเอนจิน Harness แบบเนทีฟของ Android คอนเทนเนอร์ Linux และเซิร์ฟเวอร์กราฟิกแบบเฉพาะสิทธิ์ไม่ได้รวมอยู่ด้วย โปรดใช้เวิร์กสเปซแบบเนทีฟและเครื่องมือ Android ที่เข้ากันได้",
        "pocket_manual_update_only": "บิลด์โลคอลนี้อัปเดตด้วย APK ด้วยตนเอง ระบบแทนที่แอปและรันไทม์อัตโนมัติถูกปิดไว้เพื่อรักษาข้อมูลและการแก้ไขแบบเนทีฟ",
        "remote_host_address_hint": "http://192.168.1.10:3080",
        "remote_host_address_label": "ที่อยู่",
        "remote_host_connect": "เชื่อมต่อ",
        "remote_host_connecting": "กำลังโหลด %1$s",
        "remote_host_intro": "เปิดหน้าเว็บของ DeepSeek Harness ที่รันอยู่บนเครื่องอื่น หน้านี้แยกจากเอนจินในเครื่องอย่างสมบูรณ์ ไม่เริ่มหรือหยุดเอนจิน และข้อมูลที่กรอกจะส่งไปยังที่อยู่ที่ระบุเท่านั้น",
        "remote_host_keepalive": "คำแนะนำ: อย่าให้โฮสต์หลับ หากโฮสต์เป็นโทรศัพท์ ควรอนุญาตให้แอปทำงานเบื้องหลัง ไม่อย่างนั้นหน้าเว็บจะขาดเมื่อปิดจอ",
        "remote_host_load_failed": "โหลดไม่สำเร็จ: %1$s",
        "remote_host_need_address": "กรุณากรอกที่อยู่ก่อน",
        "remote_host_security": "ความปลอดภัย: เชื่อมต่อเฉพาะโฮสต์ที่คุณควบคุมเอง http:// แบบไม่เข้ารหัสอาจถูกอ่านได้ในเครือข่ายที่ใช้ร่วมกัน ควรใช้ SSH tunnel",
        "remote_host_test": "ทดสอบ",
        "remote_host_test_bad": "โฮสต์ตอบกลับ HTTP %1$d ตรวจสอบพอร์ตและพาธของหน้าเว็บ",
        "remote_host_test_failed": "เชื่อมต่อโฮสต์ไม่ได้: %1$s",
        "remote_host_test_ok": "เชื่อมต่อได้ (HTTP %1$d) หากหน้ายังไม่เปิด สาเหตุมักเป็นโทเคนไม่ถูกต้อง",
        "remote_host_testing": "กำลังทดสอบ…",
        "remote_host_title": "โฮสต์ระยะไกล",
        "remote_host_token_hint": "โทเคนที่แสดงในบันทึกการเริ่มต้นของโฮสต์",
        "remote_host_token_label": "โทเคนเข้าใช้งาน (ไม่บังคับ)",
        "setting_engine": "เอนจิน",
        "setting_engine_sub_idle": "เอนจินพร้อม · 3080",
        "setting_remote_host": "โฮสต์ระยะไกล",
        "setting_remote_host_sub": "เปิด DSH บนคอมพิวเตอร์หรือเซิร์ฟเวอร์ของคุณ",
    },
}


def escape(value: str) -> str:
    return (value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace("'", "\\'"))


def main() -> int:
    for loc, items in DATA.items():
        path = os.path.join(RES, loc, "strings.xml")
        text = io.open(path, encoding="utf-8", newline="").read()
        block = "".join(f'    <string name="{k}">{escape(v)}</string>\n' for k, v in items.items())
        idx = text.rfind("</resources>")
        io.open(path, "w", encoding="utf-8", newline="").write(text[:idx] + block + text[idx:])
        print(loc, "added", len(items))
    return 0


if __name__ == "__main__":
    sys.exit(main())
