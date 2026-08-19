from PySide6.QtCore import Qt, QUrl, QSettings, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QCheckBox
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import (
    QWebEngineProfile, QWebEnginePage, QWebEngineScript, QWebEngineUrlRequestInterceptor
)

from app.core.adblock import (
    AUTOPLAY_CONTROL_SCRIPT, AUTOPLAY_SETTING_KEY, PLAYER_PRUNE_SCRIPT,
    THEATER_SCRIPT, build_engine
)


class AdBlockInterceptor(QWebEngineUrlRequestInterceptor):
    def __init__(self, engine, parent=None):
        super().__init__(parent)
        self._engine = engine
        self.blocked = 0

    def interceptRequest(self, info):
        if self._engine is None:
            return
        try:
            result = self._engine.check_network_urls(
                info.requestUrl().toString(), "https://www.youtube.com/", "other"
            )
        except Exception:
            return
        if result.matched:
            self.blocked += 1
            info.block(True)


class SingleVideoPage(QWebEnginePage):
    def __init__(self, profile, video_id, parent=None):
        super().__init__(profile, parent)
        self._video_id = video_id
        self._locked = True
        self.blocked_navigations = 0

    def set_locked(self, locked):
        self._locked = locked

    def acceptNavigationRequest(self, url, nav_type, is_main_frame):
        if not is_main_frame or not self._video_id or not self._locked:
            return True
        target = BrowserPlayer.video_id_of(url.toString())
        if target and target != self._video_id:
            self.blocked_navigations += 1
            return False
        return True


class BrowserPlayer(QDialog):
    closed = Signal()

    def __init__(self, video_url, title="", parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Watch: {title}" if title else "Watch")
        self.resize(1100, 700)
        self.setSizeGripEnabled(True)

        self._settings = QSettings("YouTubeDownloader", "YouTubeDownloader")
        self._autoplay_enabled = self._settings.value(AUTOPLAY_SETTING_KEY, False, type=bool)
        self._profile = QWebEngineProfile(self)
        self._engine = build_engine()
        self._interceptor = AdBlockInterceptor(self._engine, self)
        self._profile.setUrlRequestInterceptor(self._interceptor)

        for source in (PLAYER_PRUNE_SCRIPT, THEATER_SCRIPT, AUTOPLAY_CONTROL_SCRIPT):
            script = QWebEngineScript()
            script.setSourceCode(source)
            script.setInjectionPoint(QWebEngineScript.DocumentCreation)
            script.setWorldId(QWebEngineScript.MainWorld)
            script.setRunsOnSubFrames(True)
            self._profile.scripts().insert(script)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.video_id = self.video_id_of(video_url)
        self.view = QWebEngineView(self)
        self.page = SingleVideoPage(self._profile, self.video_id, self.view)
        self.view.setPage(self.page)
        layout.addWidget(self.view, stretch=1)

        bar = QHBoxLayout()
        bar.setContentsMargins(6, 4, 6, 4)
        self.status_label = QLabel(
            "Ad filtering active." if self._engine is not None
            else "Ad filtering active (filter lists still downloading)."
        )
        self.status_label.setStyleSheet("font-size: 11px;")
        bar.addWidget(self.status_label)
        bar.addStretch()

        self.autoplay_checkbox = QCheckBox("Autoplay next video")
        self.autoplay_checkbox.setToolTip(
            "When off, this window stays on the video you opened. When on, "
            "YouTube may continue to the next video when this one ends."
        )
        self.autoplay_checkbox.setChecked(self._autoplay_enabled)
        self.autoplay_checkbox.toggled.connect(self._on_autoplay_toggled)
        bar.addWidget(self.autoplay_checkbox)
        close_button = QPushButton("Close")
        close_button.setFixedWidth(80)
        close_button.clicked.connect(self.close)
        bar.addWidget(close_button)
        layout.addLayout(bar)

        self.page.set_locked(not self._autoplay_enabled)
        self.view.loadFinished.connect(self._apply_autoplay_to_page)
        self.view.load(QUrl(self.watch_url(video_url)))

    def _apply_autoplay_to_page(self, ok=True):
        flag = "true" if self._autoplay_enabled else "false"
        try:
            self.view.page().runJavaScript(
                f"window.__setAutoplay && window.__setAutoplay({flag});"
            )
        except Exception:
            pass

    def _on_autoplay_toggled(self, checked):
        self._autoplay_enabled = bool(checked)
        self._settings.setValue(AUTOPLAY_SETTING_KEY, self._autoplay_enabled)
        self.page.set_locked(not self._autoplay_enabled)
        self._apply_autoplay_to_page()

    @staticmethod
    def video_id_of(video_url):
        url = QUrl(video_url)
        host = url.host().lower()
        if "youtu.be" in host:
            return url.path().lstrip("/")
        for pair in url.query().split("&"):
            if pair.startswith("v="):
                return pair[2:]
        return ""

    @staticmethod
    def watch_url(video_url):
        video_id = BrowserPlayer.video_id_of(video_url)
        if not video_id:
            return video_url
        return f"https://www.youtube.com/watch?v={video_id}"

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event):
        try:
            self.view.stop()
            self.view.setPage(None)
        except Exception:
            pass
        self.closed.emit()
        super().closeEvent(event)
