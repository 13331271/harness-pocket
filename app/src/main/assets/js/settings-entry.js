/**
 * v0.2.7: 设置入口 = 侧栏「更多」行最右侧的一个小齿轮（不悬浮、不跳动）。
 *
 * 上一版有两个毛病，用户截图点名了：
 *   1) 每轮 DOM 变化都 remove + append，锚点偶尔命中「文字 span」、偶尔命中
 *      「整行」，按钮就在两者之间来回跳；
 *   2) 用 fixed 定位会压住侧栏边界。
 *
 * 现在只创建一次节点、挂在 body 上，用 absolute + 页面滚动偏移量定位到那一行
 * 的右端：滚动时跟着页面走（坐标含 scrollY），重渲染只更新位置、不重建节点，
 * 所以不会上下跳。找不到锚点就隐藏（display:none），绝不跨到内容区。
 */
(function () {
  if (window.__dshSidebarSettings) return;
  window.__dshSidebarSettings = true;

  var ID = "dsh-sidebar-settings";
  var LABELS = ["更多", "More", "Mehr", "Mais", "Ещё", "เพิ่มเติม"];
  var SIZE = 22;
  var timer = null;
  var btn = null;

  function bridge() { return window.DshAndroidSettings || null; }

  function report(found) {
    var b = bridge();
    if (!b || typeof b.reportAnchor !== "function") return;
    try { b.reportAnchor(!!found); } catch (e) { /* page reloaded */ }
  }

  function visible(el) {
    if (!el || el.offsetParent === null) return false;
    var r = el.getBoundingClientRect();
    return r.width > 8 && r.height > 8;
  }

  /** 命中「更多」这行最可信的节点：可见、在左半屏、面积最小（= 行本身而非整块侧栏）。 */
  function findMoreRow() {
    var limit = (window.innerWidth || 800) * 0.55;
    var best = null;
    var nodes = document.querySelectorAll("a,button,div,span,li");
    for (var i = 0; i < nodes.length; i++) {
      var el = nodes[i];
      if (el.id === ID) continue;
      if (LABELS.indexOf((el.textContent || "").trim()) === -1) continue;
      if (!visible(el)) continue;
      var r = el.getBoundingClientRect();
      if (r.left > limit) continue;
      var area = r.width * r.height;
      if (!best || area < best.area) best = { el: el, rect: r, area: area };
    }
    return best;
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

  function ensureNode() {
    if (btn && document.body.contains(btn)) return btn;
    btn = document.createElement("button");
    btn.id = ID;
    btn.type = "button";
    btn.setAttribute("aria-label", "settings");
    btn.style.cssText = [
      "position:absolute", "z-index:2147482000", "display:none",
      "align-items:center", "justify-content:center",
      "width:" + SIZE + "px", "height:" + SIZE + "px",
      "border:0", "border-radius:6px", "padding:0", "cursor:pointer",
      "background:rgba(127,127,127,0.18)", "color:inherit", "opacity:.85",
      "-webkit-tap-highlight-color:transparent",
    ].join(";");
    btn.innerHTML = iconSvg();
    btn.addEventListener("click", function (ev) {
      ev.preventDefault();
      ev.stopPropagation();
      var b = bridge();
      if (b && typeof b.open === "function") b.open();
    }, true);
    document.body.appendChild(btn);
    return btn;
  }

  function place() {
    var node = ensureNode();
    var hit = findMoreRow();
    if (!hit) {
      node.style.display = "none";
      report(false);
      return;
    }
    var r = hit.rect;
    var sx = window.pageXOffset || document.documentElement.scrollLeft || 0;
    var sy = window.pageYOffset || document.documentElement.scrollTop || 0;
    var left = Math.round(r.right - SIZE - 2);
    var top = Math.round(r.top + (r.height - SIZE) / 2);
    node.style.left = (left + sx) + "px";
    node.style.top = (top + sy) + "px";
    node.style.display = "inline-flex";
    report(true);
  }

  function schedule() {
    if (timer) return;
    timer = setTimeout(function () { timer = null; try { place(); } catch (e) { report(false); } }, 150);
  }

  function boot() {
    try {
      new MutationObserver(schedule).observe(document.body, { childList: true, subtree: true });
    } catch (e) { /* body not ready */ }
    window.addEventListener("resize", schedule);
    window.addEventListener("scroll", schedule, true);
    schedule();
    [300, 900, 2000, 4000].forEach(function (ms) { setTimeout(schedule, ms); });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
