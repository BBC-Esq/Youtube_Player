from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import (
    QWebEngineProfile, QWebEnginePage, QWebEngineScript, QWebEngineUrlRequestInterceptor
)

from app.core.adblock import PLAYER_PRUNE_SCRIPT, THEATER_SCRIPT, build_engine


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


class BrowserPlayer(QDialog):
    closed = Signal()

    def __init__(self, video_url, title="", parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Watch: {title}" if title else "Watch")
        self.resize(1100, 700)
        self.setSizeGripEnabled(True)

        self._profile = QWebEngineProfile(self)
        self._engine = build_engine()
        self._interceptor = AdBlockInterceptor(self._engine, self)
        self._profile.setUrlRequestInterceptor(self._interceptor)

        for source in (PLAYER_PRUNE_SCRIPT, THEATER_SCRIPT):
            script = QWebEngineScript()
            script.setSourceCode(source)
            script.setInjectionPoint(QWebEngineScript.DocumentCreation)
            script.setWorldId(QWebEngineScript.MainWorld)
            script.setRunsOnSubFrames(True)
            self._profile.scripts().insert(script)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.view = QWebEngineView(self)
        self.view.setPage(QWebEnginePage(self._profile, self.view))
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
        close_button = QPushButton("Close")
        close_button.setFixedWidth(80)
        close_button.clicked.connect(self.close)
        bar.addWidget(close_button)
        layout.addLayout(bar)

        self.view.load(QUrl(self.watch_url(video_url)))

    @staticmethod
    def watch_url(video_url):
        video_id = ""
        url = QUrl(video_url)
        host = url.host().lower()
        if "youtu.be" in host:
            video_id = url.path().lstrip("/")
        else:
            for pair in url.query().split("&"):
                if pair.startswith("v="):
                    video_id = pair[2:]
                    break
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
