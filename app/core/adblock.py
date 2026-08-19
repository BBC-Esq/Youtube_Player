import os
import time
import urllib.request

from PySide6.QtCore import QStandardPaths

FILTER_LISTS = {
    "ubo-filters.txt": "https://ublockorigin.github.io/uAssets/filters/filters.txt",
    "ubo-privacy.txt": "https://ublockorigin.github.io/uAssets/filters/privacy.txt",
    "easylist.txt": "https://easylist.to/easylist/easylist.txt",
}

MAX_LIST_AGE_SECONDS = 7 * 24 * 60 * 60

PLAYER_PRUNE_SCRIPT = r"""
(function () {
  var AD_KEYS = ["adPlacements", "playerAds", "adSlots", "adBreakHeartbeatParams",
                 "adParams", "adServerData", "importantForAds"];
  function prune(o, d) {
    if (!o || typeof o !== "object" || (d || 0) > 12) return o;
    if (Array.isArray(o)) {
      for (var i = 0; i < o.length; i++) prune(o[i], (d || 0) + 1);
      return o;
    }
    for (var k = 0; k < AD_KEYS.length; k++) {
      if (AD_KEYS[k] in o) { try { delete o[AD_KEYS[k]]; } catch (e) {} }
    }
    for (var p in o) {
      try { var v = o[p]; if (v && typeof v === "object") prune(v, (d || 0) + 1); } catch (e) {}
    }
    return o;
  }
  var _parse = JSON.parse;
  JSON.parse = function () {
    var r = _parse.apply(this, arguments);
    return (r && typeof r === "object") ? prune(r) : r;
  };
  try {
    var _json = Response.prototype.json;
    Response.prototype.json = function () {
      return _json.apply(this, arguments).then(function (r) { return prune(r); });
    };
  } catch (e) {}
  var stored;
  try {
    Object.defineProperty(window, "ytInitialPlayerResponse", {
      configurable: true,
      get: function () { return stored; },
      set: function (v) { stored = prune(v); }
    });
  } catch (e) {}
})();
"""

AUTOPLAY_OFF_SCRIPT = r"""
(function () {
  function disable() {
    try {
      var player = document.getElementById("movie_player");
      if (player && typeof player.setAutonavState === "function") {
        player.setAutonavState(1);
      }
    } catch (e) {}
    try {
      var toggle = document.querySelector(".ytp-autonav-toggle-button");
      if (toggle && toggle.getAttribute("aria-checked") === "true") {
        toggle.click();
      }
    } catch (e) {}
  }
  disable();
  document.addEventListener("DOMContentLoaded", disable);
  var ticks = 0;
  var timer = setInterval(function () {
    disable();
    if (++ticks > 40) clearInterval(timer);
  }, 1500);
})();
"""

THEATER_SCRIPT = r"""
(function () {
  var css = "#masthead-container,#secondary,#comments,#related,ytd-merch-shelf-renderer," +
            "tp-yt-app-drawer,#chat,ytd-companion-slot-renderer,#player-ads," +
            "ytd-engagement-panel-section-list-renderer{display:none !important}" +
            "ytd-watch-flexy #primary{max-width:100% !important;padding:0 !important}" +
            "html,body{background:#000 !important;overflow:hidden !important}";
  function apply() {
    if (!document.head) return;
    var s = document.getElementById("__theater_css");
    if (s) return;
    s = document.createElement("style");
    s.id = "__theater_css";
    s.textContent = css;
    document.head.appendChild(s);
  }
  apply();
  document.addEventListener("DOMContentLoaded", apply);
  new MutationObserver(apply).observe(document.documentElement, {childList: true, subtree: false});
})();
"""


def filter_dir():
    base = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)
    if not base:
        base = os.path.join(os.path.expanduser("~"), ".youtube_downloader")
    path = os.path.join(base, "YouTubeDownloader", "filters")
    os.makedirs(path, exist_ok=True)
    return path


def list_is_stale(path):
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return True
    return (time.time() - os.path.getmtime(path)) > MAX_LIST_AGE_SECONDS


def lists_need_refresh():
    directory = filter_dir()
    return any(list_is_stale(os.path.join(directory, name)) for name in FILTER_LISTS)


def refresh_filter_lists():
    directory = filter_dir()
    updated = 0
    for name, url in FILTER_LISTS.items():
        target = os.path.join(directory, name)
        if not list_is_stale(target):
            continue
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "YouTubeDownloader"})
            with urllib.request.urlopen(request, timeout=45) as response:
                data = response.read()
            if data:
                with open(target, "wb") as handle:
                    handle.write(data)
                updated += 1
        except Exception:
            continue
    return updated


def build_engine():
    try:
        from adblock import Engine, FilterSet
    except Exception:
        return None
    directory = filter_dir()
    filter_set = FilterSet()
    loaded = 0
    for name in FILTER_LISTS:
        path = os.path.join(directory, name)
        if not os.path.exists(path):
            continue
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as handle:
                filter_set.add_filter_list(handle.read())
            loaded += 1
        except Exception:
            continue
    if not loaded:
        return None
    try:
        return Engine(filter_set=filter_set)
    except Exception:
        return None
