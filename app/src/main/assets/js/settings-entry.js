/**
 * v0.2.5: 把「设置」入口挂到侧栏「更多」那一行的最右侧。
 *
 * 为什么用 DOM 测量而不是写死坐标：侧栏是 WebUI 运行时渲染的（「更多」这个
 * 文案不在静态 bundle 里，也不在 i18n JSON 里可检索），宽度、折叠状态、语言
 * 都会变。这里每次布局变化都按文本重新找一次锚点，找不到就回收按钮并通知
 * 原生保留右下角兜底入口 —— 宁可位置不对，也不能让人进不去设置。
 */
(function () {
  if (window.__dshSettingsEntry) return;
  window.__dshSettingsEntry = true;

  var ID = "dsh-settings-entry";
  var LABELS = ["更多", "More", "Mehr", "Mais", "Ещё", "เพิ่มเติม"];
  var SIZE = 26;
  var timer = null;

  function native() {
    return window.DshAndroidSettings || null;
  }

  function report(found) {
    var bridge = native();
    if (!bridge || typeof bridge.reportAnchor !== "function") return;
    try { bridge.reportAnchor(!!found); } catch (e) { /* bridge gone on reload */ }
  }

  function visible(el) {
    if (!el || el.offsetParent === null) return false;
    var r = el.getBoundingClientRect();
    return r.width > 8 && r.height > 8 && r.bottom > 0 && r.top < (window.innerHeight || 1e9);
  }

  /** Smallest element whose trimmed text is exactly one of the sidebar labels. */
  function findAnchor() {
    var limit = (window.innerWidth || 800) * 0.5;
    var best = null;
    var nodes = document.querySelectorAll("a,button,div,span,li");
    for (var i = 0; i < nodes.length; i++) {
      var el = nodes[i];
      var text = (el.textContent || "").trim();
      if (LABELS.indexOf(text) === -1) continue;
      if (!visible(el)) continue;
      var r = el.getBoundingClientRect();
      if (r.left > limit) continue;
      var area = r.width * r.height;
      if (!best || area < best.area) best = { el: el, rect: r, area: area };
    }
    return best;
  }

  function gearSvg() {
    return '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" ' +
      'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
      '<circle cx="12" cy="12" r="3"></circle>' +
      '<path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 ' +
      '1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 ' +
      '1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09a1.65 1.65 0 0 0 ' +
      '1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33h.09a1.65 1.65 0 ' +
      '0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83' +
      'l-.06.06a1.65 1.65 0 0 0-.33 1.82v.09a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z">' +
      "</path></svg>";
  }

  function ensureButton() {
    var existing = document.getElementById(ID);
    var anchor = findAnchor();
    if (!anchor) {
      if (existing) existing.remove();
      report(false);
      return;
    }
    if (!existing) {
      existing = document.createElement("button");
      existing.id = ID;
      existing.type = "button";
      existing.setAttribute("aria-label", "设置");
      existing.style.cssText = [
        "position:fixed", "z-index:2147483000", "display:flex",
        "align-items:center", "justify-content:center",
        "width:" + SIZE + "px", "height:" + SIZE + "px",
        "border:0", "border-radius:8px", "padding:0", "cursor:pointer",
        "background:rgba(127,127,127,0.16)", "color:inherit",
        "opacity:0.85", "pointer-events:auto", "-webkit-tap-highlight-color:transparent",
      ].join(";");
      existing.innerHTML = gearSvg();
      existing.addEventListener("click", function (ev) {
        ev.preventDefault();
        ev.stopPropagation();
        var bridge = native();
        if (bridge && typeof bridge.open === "function") bridge.open();
      }, true);
      document.body.appendChild(existing);
    }
    var r = anchor.rect;
    var left = Math.min(r.right - SIZE, (window.innerWidth || 800) - SIZE - 4);
    var top = r.top + (r.height - SIZE) / 2;
    existing.style.left = Math.max(0, left) + "px";
    existing.style.top = Math.max(0, top) + "px";
    report(true);
  }

  function schedule() {
    if (timer) return;
    timer = setTimeout(function () {
      timer = null;
      try { ensureButton(); } catch (e) { report(false); }
    }, 120);
  }

  // React re-renders replace the sidebar subtree; re-anchor after each mutation.
  var observer = new MutationObserver(schedule);
  function boot() {
    try {
      observer.observe(document.body, { childList: true, subtree: true });
    } catch (e) { /* body may not exist yet */ }
    window.addEventListener("resize", schedule);
    window.addEventListener("scroll", schedule, true);
    schedule();
    // The sidebar can mount late (data fetch); poll a few times as a backstop.
    [400, 1200, 2500, 5000].forEach(function (ms) { setTimeout(schedule, ms); });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
