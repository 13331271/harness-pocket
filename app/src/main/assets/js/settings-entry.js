/**
 * v0.2.6: 「设置」入口作为侧栏「更多」行的一部分，直接塞进那一行，不再浮在屏幕上。
 *
 * 上一版用 fixed 定位悬浮按钮，结果盖住了侧栏边界（用户截图可见）。这里改成
 * 真正把节点 append 到「更多」这一行的内部，用 margin-left:auto 靠右对齐，
 * 随行本身布局，不占用额外空间，也不会跨到网页内容区。
 *
 * 找不到「更多」时依次退到：侧栏容器底部（仍是侧栏内部）→ 页面左上角的
 * 侧栏手柄。任何情况下都不再出现「压在内容上的悬浮圆钮」。
 */
(function () {
  if (window.__dshSidebarSettings) return;
  window.__dshSidebarSettings = true;

  var ID = "dsh-sidebar-settings";
  var LABELS = ["更多", "More", "Mehr", "Mais", "Ещё", "เพิ่มเติม"];
  var SIZE = 22;
  var timer = null;

  function bridge() { return window.DshAndroidSettings || null; }

  function report(mode) {
    var b = bridge();
    if (!b || typeof b.reportAnchor !== "function") return;
    try { b.reportAnchor(mode === "row"); } catch (e) { /* page reloaded */ }
  }

  function visible(el) {
    if (!el || el.offsetParent === null) return false;
    var r = el.getBoundingClientRect();
    return r.width > 8 && r.height > 8;
  }

  /** The smallest visible element on the left half whose text is exactly a label. */
  function findMoreRow() {
    var limit = (window.innerWidth || 800) * 0.5;
    var best = null;
    var nodes = document.querySelectorAll("a,button,div,span,li");
    for (var i = 0; i < nodes.length; i++) {
      var el = nodes[i];
      if (LABELS.indexOf((el.textContent || "").trim()) === -1) continue;
      if (!visible(el) || el.id === ID) continue;
      var r = el.getBoundingClientRect();
      if (r.left > limit) continue;
      var area = r.width * r.height;
      if (!best || area < best.area) best = { el: el, area: area };
    }
    return best ? best.el : null;
  }

  /** Sidebar container: walk up from the row until the ancestor is clearly wider. */
  function sidebarOf(row) {
    var cur = row;
    for (var i = 0; i < 6 && cur.parentElement; i++) {
      var parent = cur.parentElement;
      var pr = parent.getBoundingClientRect();
      if (pr.width > (window.innerWidth || 800) * 0.45) return cur;
      cur = parent;
    }
    return cur;
  }

  function iconSvg() {
    return '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" ' +
      'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
      '<circle cx="12" cy="12" r="3"></circle>' +
      '<path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 ' +
      '1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 ' +
      '1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09a1.65 1.65 0 0 0 ' +
      '1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33h.09a1.65 1.65 0 ' +
      '0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83' +
      'l-.06.06a1.65 1.65 0 0 0-.33 1.82v.09a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z">' +
      "</path></svg>";
  }

  function makeButton(inline) {
    var b = document.createElement("button");
    b.id = ID;
    b.type = "button";
    b.setAttribute("aria-label", "settings");
    b.style.cssText = [
      "display:inline-flex", "align-items:center", "justify-content:center",
      "width:" + SIZE + "px", "height:" + SIZE + "px", "margin-left:auto",
      "border:0", "border-radius:6px", "padding:0", "cursor:pointer",
      "background:transparent", "color:inherit", "opacity:.62",
      "flex:0 0 auto", "-webkit-tap-highlight-color:transparent",
      inline ? "position:static" : "position:sticky",
    ].join(";");
    b.innerHTML = iconSvg();
    b.addEventListener("click", function (ev) {
      ev.preventDefault();
      ev.stopPropagation();
      var br = bridge();
      if (br && typeof br.open === "function") br.open();
    }, true);
    return b;
  }

  function place() {
    var old = document.getElementById(ID);
    var row = findMoreRow();
    var host = null;
    var mode = "none";
    if (row) {
      host = row;
      mode = "row";
    } else {
      var probe = document.querySelector('[class*="sidebar"],[class*="Sidebar"],[role="navigation"]');
      if (probe && visible(probe)) { host = probe; mode = "sidebar"; }
    }
    if (!host) {
      if (old) old.remove();
      report("none");
      return;
    }
    // Re-create when the host changed (React can swap the row node entirely).
    if (old && old.parentElement === host) {
      report(mode);
      return;
    }
    if (old) old.remove();
    var btn = makeButton(true);
    host.appendChild(btn);
    report(mode);
  }

  function schedule() {
    if (timer) return;
    timer = setTimeout(function () { timer = null; try { place(); } catch (e) { report("none"); } }, 120);
  }

  function boot() {
    try {
      new MutationObserver(schedule).observe(document.body, { childList: true, subtree: true });
    } catch (e) { /* body not ready */ }
    window.addEventListener("resize", schedule);
    schedule();
    [300, 900, 2000, 4000, 8000].forEach(function (ms) { setTimeout(schedule, ms); });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
