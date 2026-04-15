import os
import re
import threading
import webbrowser
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QComboBox, QFrame, QGroupBox, QMessageBox,
    QCheckBox, QListWidget, QInputDialog
)
from PySide6.QtCore import Qt, Slot, Signal, QSettings, QTimer
from PySide6.QtGui import QPixmap

from app.constants import (
    AUDIO_FORMATS, BITRATE_OPTIONS, SAMPLE_RATE_OPTIONS,
    CHANNEL_OPTIONS, VIDEO_CODEC_NAMES, VIDEO_CODEC_TOOLTIPS,
    AUDIO_CODEC_NAMES, AUDIO_CODEC_TOOLTIPS
)
from app.threads import FetchThread, CaptionDownloadThread, ThumbnailThread
from app.dialogs import SettingsDialog
from app.widgets import VideoPlayer, DownloadsPanel, Toast
from app.core import DownloadManager, DownloadJob


class MainWindow(QMainWindow):
    _oauth_dialog_requested = Signal(str, str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("YouTube Downloader")
        self.setGeometry(100, 100, 900, 780)

        self.settings = QSettings("YouTubeDownloader", "YouTubeDownloader")
        self.streams_objects = []
        self.video_streams = []
        self.audio_streams = []
        self.captions_data = []
        self.video_url = ""
        self.video_title = ""
        self._pre_fullscreen_geometry = None
        self._fullscreen_hidden_widgets = []
        self._active_threads = []
        self._oauth_event = threading.Event()
        self._oauth_lock = threading.Lock()
        self._oauth_dialog_requested.connect(self._display_oauth_dialog)

        self.download_manager = DownloadManager(self, oauth_verifier=self._oauth_verifier)
        self.download_manager.job_added.connect(self._on_job_added)
        self.download_manager.job_updated.connect(self._on_job_updated)
        self.download_manager.job_finished.connect(self._on_job_finished)
        self.download_manager.job_failed.connect(self._on_job_failed)

        menu_bar = self.menuBar()
        settings_menu = menu_bar.addMenu("Settings")
        settings_action = settings_menu.addAction("Preferences...")
        settings_action.triggered.connect(self.open_settings)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        self.main_layout = QVBoxLayout(central_widget)

        url_frame = QFrame()
        url_layout = QHBoxLayout(url_frame)
        url_label = QLabel("YouTube URL:")
        self.url_entry = QLineEdit()
        self.url_entry.setPlaceholderText("Paste a YouTube URL here...")
        self.fetch_timer = QTimer()
        self.fetch_timer.setSingleShot(True)
        self.fetch_timer.setInterval(1000)
        self.fetch_timer.timeout.connect(self.fetch_video_info)
        self.url_entry.textChanged.connect(self.on_url_text_changed)
        url_layout.addWidget(url_label)
        url_layout.addWidget(self.url_entry)
        self.main_layout.addWidget(url_frame)

        self.use_oauth = QCheckBox("Use OAuth (required for some age-restricted videos)")
        self.main_layout.addWidget(self.use_oauth)

        self.error_label = QLabel()
        self.error_label.setStyleSheet("color: red;")
        self.main_layout.addWidget(self.error_label)

        self.title_label = QLabel()
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        self.title_label.setWordWrap(True)
        self.main_layout.addWidget(self.title_label)

        self.player = VideoPlayer()
        self.player.fullscreen_toggled.connect(self._handle_fullscreen)
        self.player.error_occurred.connect(self._player_error)
        self.player.play_requested.connect(self.preview_video)
        self.main_layout.addWidget(self.player, stretch=1)

        self.playback_frame = QFrame()
        playback_layout = QHBoxLayout(self.playback_frame)
        playback_layout.setContentsMargins(0, 2, 0, 2)
        playback_layout.setSpacing(6)

        self.pb_res_label = QLabel("Resolution:")
        self.pb_resolution_combo = QComboBox()
        self.pb_resolution_combo.currentIndexChanged.connect(self.on_pb_resolution_changed)
        playback_layout.addWidget(self.pb_res_label)
        playback_layout.addWidget(self.pb_resolution_combo)

        self.pb_fmt_label = QLabel("Video Format:")
        self.pb_format_combo = QComboBox()
        playback_layout.addWidget(self.pb_fmt_label)
        playback_layout.addWidget(self.pb_format_combo)

        self.pb_audio_label = QLabel("Audio:")
        self.pb_audio_combo = QComboBox()
        playback_layout.addWidget(self.pb_audio_label)
        playback_layout.addWidget(self.pb_audio_combo)

        self.pb_update_button = QPushButton("Update")
        self.pb_update_button.setFixedWidth(60)
        self.pb_update_button.setEnabled(False)
        self.pb_update_button.clicked.connect(self.apply_playback_settings)
        playback_layout.addWidget(self.pb_update_button)

        self._pb_active_video_itag = None
        self._pb_active_audio_itag = None

        self.pb_resolution_combo.currentIndexChanged.connect(self._on_pb_selection_changed)
        self.pb_format_combo.currentIndexChanged.connect(self._on_pb_selection_changed)
        self.pb_audio_combo.currentIndexChanged.connect(self._on_pb_selection_changed)

        playback_layout.addStretch()
        self.main_layout.addWidget(self.playback_frame)

        self.options_group = QGroupBox("Download Options")
        options_layout = QVBoxLayout(self.options_group)

        self.audio_only_checkbox = QCheckBox("Audio Only")
        self.audio_only_checkbox.toggled.connect(self.toggle_audio_only)
        options_layout.addWidget(self.audio_only_checkbox)

        combos_layout = QHBoxLayout()

        self.res_label = QLabel("Resolution:")
        self.resolution_combo = QComboBox()
        self.resolution_combo.currentIndexChanged.connect(self.on_resolution_changed)
        res_layout = QVBoxLayout()
        res_layout.addWidget(self.res_label)
        res_layout.addWidget(self.resolution_combo)
        combos_layout.addLayout(res_layout)

        self.fmt_label = QLabel("Video Format:")
        self.video_format_combo = QComboBox()
        self.video_format_combo.currentIndexChanged.connect(self.update_format_tooltip)
        fmt_layout = QVBoxLayout()
        fmt_layout.addWidget(self.fmt_label)
        fmt_layout.addWidget(self.video_format_combo)
        combos_layout.addLayout(fmt_layout)

        audio_q_layout = QVBoxLayout()
        audio_q_layout.addWidget(QLabel("Audio Quality:"))
        self.audio_quality_combo = QComboBox()
        self.audio_quality_combo.currentIndexChanged.connect(self.update_audio_tooltip)
        audio_q_layout.addWidget(self.audio_quality_combo)
        combos_layout.addLayout(audio_q_layout)

        self.conversion_group = QGroupBox("Conversion Options")
        conv_layout = QVBoxLayout(self.conversion_group)
        conv_layout.setContentsMargins(6, 6, 6, 6)
        conv_layout.setSpacing(3)

        self.conversion_mode_combo = QComboBox()
        self.conversion_mode_combo.addItems([
            "No Conversion",
            "Convert and Keep Original",
            "Convert and Delete Original"
        ])
        self.conversion_mode_combo.currentTextChanged.connect(self._update_conversion_fields_state)
        conv_layout.addWidget(self.conversion_mode_combo)

        conv_row1 = QHBoxLayout()
        conv_row1.setSpacing(4)
        self.conv_format_combo = QComboBox()
        self.conv_format_combo.addItems(list(AUDIO_FORMATS.keys()))
        self.conv_format_combo.currentTextChanged.connect(self._update_bitrate_state)
        conv_row1.addWidget(QLabel("Format:"))
        conv_row1.addWidget(self.conv_format_combo)
        self.conv_bitrate_combo = QComboBox()
        self.conv_bitrate_combo.addItems([f"{b} kbps" for b in BITRATE_OPTIONS])
        self.conv_bitrate_combo.setCurrentIndex(BITRATE_OPTIONS.index("192"))
        conv_row1.addWidget(QLabel("Bitrate:"))
        conv_row1.addWidget(self.conv_bitrate_combo)
        conv_layout.addLayout(conv_row1)

        conv_row2 = QHBoxLayout()
        conv_row2.setSpacing(4)
        self.conv_sample_rate_combo = QComboBox()
        self.conv_sample_rate_combo.addItems([f"{r} Hz" for r in SAMPLE_RATE_OPTIONS])
        self.conv_sample_rate_combo.setCurrentIndex(SAMPLE_RATE_OPTIONS.index("44100"))
        conv_row2.addWidget(QLabel("Sample Rate:"))
        conv_row2.addWidget(self.conv_sample_rate_combo)
        self.conv_channels_combo = QComboBox()
        self.conv_channels_combo.addItems(list(CHANNEL_OPTIONS.keys()))
        conv_row2.addWidget(QLabel("Channels:"))
        conv_row2.addWidget(self.conv_channels_combo)
        conv_layout.addLayout(conv_row2)

        self._update_conversion_fields_state()
        self.conversion_group.setVisible(False)
        combos_layout.addWidget(self.conversion_group)

        options_layout.addLayout(combos_layout)

        self.main_layout.addWidget(self.options_group)

        download_row = QHBoxLayout()
        self.download_button = QPushButton("Add to Queue")
        self.download_button.setEnabled(False)
        self.download_button.setMinimumHeight(40)
        self.download_button.setStyleSheet("font-size: 14px; font-weight: bold;")
        self.download_button.clicked.connect(self.enqueue_download)
        download_row.addWidget(self.download_button)
        self.main_layout.addLayout(download_row)

        self.transcripts_group = QGroupBox("Transcripts")
        transcripts_layout = QHBoxLayout(self.transcripts_group)
        self.transcripts_list = QListWidget()
        self.transcripts_list.setMaximumHeight(80)
        transcripts_layout.addWidget(self.transcripts_list)
        self.transcript_download_button = QPushButton("Download\nTranscript")
        self.transcript_download_button.setEnabled(False)
        self.transcript_download_button.setFixedWidth(90)
        self.transcript_download_button.clicked.connect(self.download_transcript)
        transcripts_layout.addWidget(self.transcript_download_button)
        self.main_layout.addWidget(self.transcripts_group)

        self.downloads_panel = DownloadsPanel()
        self.downloads_panel.cancel_requested.connect(self.download_manager.cancel)
        self.downloads_panel.remove_requested.connect(self._remove_job)
        self.main_layout.addWidget(self.downloads_panel)

        self.status_label = QLabel("Paste a YouTube URL above to get started.")
        self.main_layout.addWidget(self.status_label)

        self.toast = Toast(self)

        self.transcripts_list.itemSelectionChanged.connect(
            lambda: self.transcript_download_button.setEnabled(
                bool(self.transcripts_list.selectedItems())
            )
        )

    def open_settings(self):
        dialog = SettingsDialog(self)
        dialog.exec()

    def get_download_directory(self):
        download_dir = self.settings.value("download_directory", "")
        if not download_dir:
            QMessageBox.warning(
                self,
                "Download Folder Not Set",
                "You must select a download folder before downloading.\n\n"
                "Please go to Settings > Preferences and choose a download location."
            )
            return None
        return download_dir

    def on_url_text_changed(self, text):
        self.fetch_timer.stop()
        if text.strip():
            self.fetch_timer.start()

    def fetch_video_info(self):
        url = self.url_entry.text().strip()
        if not url:
            self.error_label.setText("Please enter a YouTube video URL.")
            return

        previous_fetch = getattr(self, 'fetch_thread', None)
        if previous_fetch is not None and previous_fetch.isRunning():
            if hasattr(previous_fetch, 'cancel'):
                previous_fetch.cancel()

        self.video_url = url
        self.status_label.setText("Fetching data...")
        self.error_label.clear()
        self.title_label.clear()
        self.resolution_combo.clear()
        self.video_format_combo.clear()
        self.audio_quality_combo.clear()
        self.pb_resolution_combo.clear()
        self.pb_format_combo.clear()
        self.pb_audio_combo.clear()
        self.transcripts_list.clear()
        self.download_button.setEnabled(False)

        self.url_entry.setEnabled(False)
        self.player.stop()

        self.fetch_thread = FetchThread(url, use_oauth=self.use_oauth.isChecked(),
                                        oauth_verifier=self._oauth_verifier)
        self.fetch_thread.finished.connect(self.update_info)
        self.fetch_thread.error.connect(self.show_error)
        self.fetch_thread.client_switched.connect(self.show_client_switch)
        self.fetch_thread.start()
        self._track_thread(self.fetch_thread)

    @Slot(str, str)
    def show_client_switch(self, original_client, new_client):
        if self.sender() is not getattr(self, 'fetch_thread', None):
            return
        self.status_label.setText(
            f"Client switched from {original_client} to {new_client} to fetch video data."
        )

    @Slot(list, list, list, str, str)
    def update_info(self, streams_info, captions_info, streams_objects, status, thumbnail_url):
        if self.sender() is not getattr(self, 'fetch_thread', None):
            return
        self.streams_objects = streams_objects
        self.captions_data = captions_info or []
        self.url_entry.setEnabled(True)

        if streams_objects:
            title = streams_objects[0].title
            self.video_title = title
            self.title_label.setText(title)
            self.setWindowTitle(f"YouTube Downloader - {title}")

        self.video_streams = [
            s for s in streams_objects
            if s.includes_video_track and s.is_adaptive
        ]
        self.audio_streams = [
            s for s in streams_objects
            if s.type == "audio" and not s.is_progressive
        ]

        self.populate_resolution_combo()
        self.populate_audio_quality_combo()
        self.populate_pb_resolution_combo()
        self.populate_pb_audio_combo()

        self.transcripts_list.clear()
        for cap in self.captions_data:
            self.transcripts_list.addItem(f"{cap['name']} ({cap['code']})")

        self.download_button.setEnabled(True)

        self.status_label.setText(status)
        self.error_label.clear()

        if thumbnail_url:
            self.thumbnail_thread = ThumbnailThread(thumbnail_url)
            self.thumbnail_thread.finished.connect(self._on_thumbnail_loaded)
            self.thumbnail_thread.start()
            self._track_thread(self.thumbnail_thread)

    @Slot(QPixmap)
    def _on_thumbnail_loaded(self, pixmap):
        if self.sender() is not getattr(self, 'thumbnail_thread', None):
            return
        self.player.set_thumbnail(pixmap)

    def preview_video(self, seek_ms=None):
        if self.audio_only_checkbox.isChecked():
            audio_itag = self.pb_audio_combo.currentData()
            audio_stream = self.find_stream_by_itag(audio_itag) if audio_itag else None
            if not audio_stream:
                return
            self._pb_active_video_itag = None
            self._pb_active_audio_itag = audio_itag
            self.pb_update_button.setEnabled(False)
            self.status_label.setText("Starting audio preview...")
            self.player.play_stream(audio_stream.url, seek_ms=seek_ms)
            self.status_label.setText("Playing audio preview.")
            return

        if not self.video_streams:
            return

        video_itag = self.pb_format_combo.currentData()
        video_stream = self.find_stream_by_itag(video_itag) if video_itag else None
        if not video_stream:
            return

        audio_itag = self.pb_audio_combo.currentData()
        audio_stream = self.find_stream_by_itag(audio_itag) if audio_itag else None
        if not audio_stream:
            audio_stream = self.get_best_audio_for_video(video_stream)

        video_url = video_stream.url
        audio_url = audio_stream.url if audio_stream else None

        self._pb_active_video_itag = video_itag
        self._pb_active_audio_itag = audio_itag if audio_itag else (audio_stream.itag if audio_stream else None)
        self.pb_update_button.setEnabled(False)

        self.status_label.setText("Starting preview...")
        self.player.play_stream(video_url, audio_url, seek_ms=seek_ms)
        self.status_label.setText("Playing preview.")

    def _on_pb_selection_changed(self):
        current_video_itag = self.pb_format_combo.currentData()
        current_audio_itag = self.pb_audio_combo.currentData()
        has_active = self._pb_active_video_itag is not None or self._pb_active_audio_itag is not None
        changed = (
            current_video_itag != self._pb_active_video_itag or
            current_audio_itag != self._pb_active_audio_itag
        )
        self.pb_update_button.setEnabled(changed and has_active)

    def apply_playback_settings(self):
        seek_ms = self.player.get_current_time_ms()
        if seek_ms is None or seek_ms < 0:
            seek_ms = None
        self.player.stop()
        self.preview_video(seek_ms=seek_ms)

    def _handle_fullscreen(self, entering):
        if entering:
            self._pre_fullscreen_geometry = self.geometry()
            self._fullscreen_hidden_widgets = []
            for i in range(self.main_layout.count()):
                w = self.main_layout.itemAt(i).widget()
                if w and w is not self.player:
                    if w.isVisible():
                        self._fullscreen_hidden_widgets.append(w)
                        w.hide()
            self.menuBar().hide()
            self.showFullScreen()
        else:
            for w in self._fullscreen_hidden_widgets:
                w.show()
            self._fullscreen_hidden_widgets = []
            self.menuBar().show()
            self.showNormal()
            if self._pre_fullscreen_geometry:
                self.setGeometry(self._pre_fullscreen_geometry)
            self.player.show_controls()

    @Slot(str)
    def _player_error(self, msg):
        self.error_label.setText(f"Player: {msg}")

    def populate_resolution_combo(self):
        self.resolution_combo.blockSignals(True)
        self.resolution_combo.clear()

        resolutions = {}
        for s in self.video_streams:
            res = s.resolution
            if res and res not in resolutions:
                fps = getattr(s, 'fps', 30)
                res_num = int(res.replace("p", "")) if res.replace("p", "").isdigit() else 0
                resolutions[res] = (res_num, fps)

        sorted_res = sorted(resolutions.keys(), key=lambda r: resolutions[r], reverse=True)
        for res in sorted_res:
            self.resolution_combo.addItem(res)

        self.resolution_combo.blockSignals(False)
        if sorted_res:
            self.on_resolution_changed()

    def on_resolution_changed(self):
        self.video_format_combo.clear()
        resolution = self.resolution_combo.currentText()
        if not resolution:
            return

        matching = [s for s in self.video_streams if s.resolution == resolution]
        matching.sort(key=lambda s: s.filesize_mb if s.filesize_mb else 0)

        for s in matching:
            raw_codec = s.video_codec.split(".")[0] if s.video_codec else ""
            codec_display = VIDEO_CODEC_NAMES.get(raw_codec, raw_codec or s.subtype)
            fps = getattr(s, 'fps', '')
            fps_str = f" {fps}fps" if fps and fps != 30 else ""
            bitrate = s.bitrate
            if bitrate and bitrate >= 1_000_000:
                br_str = f" {bitrate / 1_000_000:.1f} Mbps"
            elif bitrate:
                br_str = f" {bitrate // 1000} kbps"
            else:
                br_str = ""
            size = f"{s.filesize_mb:.1f} MB" if s.filesize_mb else "? MB"
            label = f"{s.subtype.upper()} ({codec_display}){fps_str}{br_str} - {size}"
            idx = self.video_format_combo.count()
            self.video_format_combo.addItem(label, userData=s.itag)
            tooltip = VIDEO_CODEC_TOOLTIPS.get(codec_display, "")
            if tooltip:
                self.video_format_combo.setItemData(idx, tooltip, Qt.ToolTipRole)

        self.update_format_tooltip(self.video_format_combo.currentIndex())

    def update_format_tooltip(self, index):
        if index >= 0:
            tooltip = self.video_format_combo.itemData(index, Qt.ToolTipRole)
            self.video_format_combo.setToolTip(tooltip or "")
        else:
            self.video_format_combo.setToolTip("")

    def update_audio_tooltip(self, index):
        if index >= 0:
            tooltip = self.audio_quality_combo.itemData(index, Qt.ToolTipRole)
            self.audio_quality_combo.setToolTip(tooltip or "")
        else:
            self.audio_quality_combo.setToolTip("")

    def populate_audio_quality_combo(self):
        self.audio_quality_combo.clear()

        sorted_audio = sorted(
            self.audio_streams,
            key=lambda s: int(s.abr.replace("kbps", "")) if s.abr else 0,
            reverse=True
        )

        for s in sorted_audio:
            raw_codec = s.audio_codec.split(".")[0] if s.audio_codec else ""
            codec_display = AUDIO_CODEC_NAMES.get(raw_codec, raw_codec or s.subtype)
            bitrate = s.abr or "?"
            size = f"{s.filesize_mb:.1f} MB" if s.filesize_mb else "? MB"
            label = f"{bitrate} - {s.subtype.upper()} ({codec_display}) - {size}"
            idx = self.audio_quality_combo.count()
            self.audio_quality_combo.addItem(label, userData=s.itag)
            tooltip = AUDIO_CODEC_TOOLTIPS.get(codec_display, "")
            if tooltip:
                self.audio_quality_combo.setItemData(idx, tooltip, Qt.ToolTipRole)

        self.update_audio_tooltip(self.audio_quality_combo.currentIndex())

    def populate_pb_resolution_combo(self):
        self.pb_resolution_combo.blockSignals(True)
        self.pb_resolution_combo.clear()

        resolutions = {}
        for s in self.video_streams:
            res = s.resolution
            if res and res not in resolutions:
                fps = getattr(s, 'fps', 30)
                res_num = int(res.replace("p", "")) if res.replace("p", "").isdigit() else 0
                resolutions[res] = (res_num, fps)

        sorted_res = sorted(resolutions.keys(), key=lambda r: resolutions[r], reverse=True)
        for res in sorted_res:
            self.pb_resolution_combo.addItem(res)

        self.pb_resolution_combo.blockSignals(False)
        if sorted_res:
            self.on_pb_resolution_changed()

    def on_pb_resolution_changed(self):
        self.pb_format_combo.clear()
        resolution = self.pb_resolution_combo.currentText()
        if not resolution:
            return

        matching = [s for s in self.video_streams if s.resolution == resolution]
        matching.sort(key=lambda s: s.filesize_mb if s.filesize_mb else 0)

        for s in matching:
            raw_codec = s.video_codec.split(".")[0] if s.video_codec else ""
            codec_display = VIDEO_CODEC_NAMES.get(raw_codec, raw_codec or s.subtype)
            fps = getattr(s, 'fps', '')
            fps_str = f" {fps}fps" if fps and fps != 30 else ""
            bitrate = s.bitrate
            if bitrate and bitrate >= 1_000_000:
                br_str = f" {bitrate / 1_000_000:.1f} Mbps"
            elif bitrate:
                br_str = f" {bitrate // 1000} kbps"
            else:
                br_str = ""
            label = f"{s.subtype.upper()} ({codec_display}){fps_str}{br_str}"
            self.pb_format_combo.addItem(label, userData=s.itag)

    def populate_pb_audio_combo(self):
        self.pb_audio_combo.clear()

        sorted_audio = sorted(
            self.audio_streams,
            key=lambda s: int(s.abr.replace("kbps", "")) if s.abr else 0,
            reverse=True
        )

        for s in sorted_audio:
            raw_codec = s.audio_codec.split(".")[0] if s.audio_codec else ""
            codec_display = AUDIO_CODEC_NAMES.get(raw_codec, raw_codec or s.subtype)
            bitrate = s.abr or "?"
            label = f"{bitrate} ({codec_display})"
            self.pb_audio_combo.addItem(label, userData=s.itag)

    def toggle_audio_only(self, checked):
        self.res_label.setVisible(not checked)
        self.resolution_combo.setVisible(not checked)
        self.fmt_label.setVisible(not checked)
        self.video_format_combo.setVisible(not checked)
        self.pb_res_label.setVisible(not checked)
        self.pb_resolution_combo.setVisible(not checked)
        self.pb_fmt_label.setVisible(not checked)
        self.pb_format_combo.setVisible(not checked)
        self.conversion_group.setVisible(checked)

    def sanitize_filename(self, title):
        return re.sub(r'[\\/*?:"<>|]', "", title)

    def find_stream_by_itag(self, itag):
        return next((s for s in self.streams_objects if s.itag == itag), None)

    def get_best_audio_for_video(self, video_stream):
        v_subtype = video_stream.subtype.lower()

        preferred = []
        fallback = []
        for a in self.audio_streams:
            a_sub = a.subtype.lower()
            if v_subtype == "mp4" and a_sub == "mp4":
                preferred.append(a)
            elif v_subtype == "webm" and a_sub == "webm":
                preferred.append(a)
            else:
                fallback.append(a)

        candidates = preferred if preferred else fallback
        if not candidates:
            candidates = self.audio_streams

        candidates.sort(
            key=lambda s: int(s.abr.replace("kbps", "")) if s.abr else 0,
            reverse=True
        )
        return candidates[0] if candidates else None

    def _build_conversion_params(self):
        mode = self.conversion_mode_combo.currentText()
        if mode == "No Conversion":
            return None
        bitrate_str = self.conv_bitrate_combo.currentText().replace(" kbps", "")
        bitrate = int(bitrate_str) * 1000
        sample_rate = int(self.conv_sample_rate_combo.currentText().replace(" Hz", ""))
        channel_name = self.conv_channels_combo.currentText()
        channels = CHANNEL_OPTIONS.get(channel_name, 2)
        return {
            "mode": mode,
            "format": self.conv_format_combo.currentText(),
            "bitrate": bitrate,
            "sample_rate": sample_rate,
            "channels": channels,
        }

    def enqueue_download(self):
        download_dir = self.get_download_directory()
        if not download_dir:
            return
        if not self.streams_objects:
            self.error_label.setText("No streams available to download.")
            return

        self.error_label.clear()
        audio_only = self.audio_only_checkbox.isChecked()

        if audio_only:
            audio_itag = self.audio_quality_combo.currentData()
            if audio_itag is None:
                self.error_label.setText("No audio stream selected.")
                return
            audio_stream = self.find_stream_by_itag(audio_itag)
            if not audio_stream:
                self.error_label.setText("Could not find selected audio stream.")
                return
            conversion_params = self._build_conversion_params()
            job = DownloadJob(
                url=self.video_url,
                title=self.video_title or "audio",
                output_dir=download_dir,
                audio_only=True,
                use_oauth=self.use_oauth.isChecked(),
                audio_itag=audio_itag,
                audio_stream=audio_stream,
                convert_after=conversion_params is not None,
                conversion_params=conversion_params,
            )
        else:
            video_itag = self.video_format_combo.currentData()
            if video_itag is None:
                self.error_label.setText("No video stream selected.")
                return
            video_stream = self.find_stream_by_itag(video_itag)
            if not video_stream:
                self.error_label.setText("Could not find selected video stream.")
                return
            audio_stream = self.get_best_audio_for_video(video_stream)
            if not audio_stream:
                self.error_label.setText("No compatible audio stream found.")
                return
            job = DownloadJob(
                url=self.video_url,
                title=self.video_title or "video",
                output_dir=download_dir,
                audio_only=False,
                use_oauth=self.use_oauth.isChecked(),
                video_itag=video_itag,
                audio_itag=audio_stream.itag,
                video_stream=video_stream,
                audio_stream=audio_stream,
            )

        self.download_manager.enqueue(job)
        self.status_label.setText(f"Added to queue: {job.title}")
        self.toast.show_message(f"Added to queue: {job.title}", level="info", duration_ms=2500)

    @Slot(str)
    def _on_job_added(self, job_id):
        job = self.download_manager.get_job(job_id)
        if job:
            self.downloads_panel.add_job(job)
            self.downloads_panel.sync(self.download_manager.all_jobs())

    @Slot(str)
    def _on_job_updated(self, job_id):
        job = self.download_manager.get_job(job_id)
        if job is None:
            self.downloads_panel.remove_job(job_id)
        else:
            self.downloads_panel.update_job(job)
        self.downloads_panel.sync(self.download_manager.all_jobs())

    @Slot(str, str)
    def _on_job_finished(self, job_id, final_path):
        name = os.path.basename(final_path) if final_path else ""
        self.status_label.setText(f"Download completed: {final_path}")
        self.toast.show_message(f"Download complete: {name}", level="success")
        QTimer.singleShot(5000, lambda jid=job_id: self._remove_job(jid))

    @Slot(str, str)
    def _on_job_failed(self, job_id, error_message):
        self.status_label.setText(f"Download failed: {error_message}")
        short = error_message if len(error_message) <= 140 else error_message[:137] + "..."
        self.toast.show_message(f"Download failed: {short}", level="error", duration_ms=6000)

    def _remove_job(self, job_id):
        self.download_manager.remove(job_id)
        self.downloads_panel.remove_job(job_id)
        self.downloads_panel.sync(self.download_manager.all_jobs())

    def download_transcript(self):
        download_dir = self.get_download_directory()
        if not download_dir:
            return

        selected = self.transcripts_list.selectedItems()
        if not selected:
            return

        idx = self.transcripts_list.row(selected[0])
        cap = self.captions_data[idx]
        cap_code = cap["code"]

        fmt, ok = QInputDialog.getItem(
            self, "Choose Transcript Format", "Select format:",
            ["srt", "txt"], 0, False
        )
        if not ok:
            return

        base_title = self.sanitize_filename(self.video_title or "YouTube")
        auto = cap_code.startswith("a.")
        lang = cap_code.split(".", 1)[-1] if auto else cap_code
        descriptor = "AutoTranscript" if auto else "Transcript"
        proposed = f"{base_title}_{descriptor}_{lang}.{fmt}"
        if len(proposed) > 200:
            ext = f".{fmt}"
            proposed = f"{proposed[:200 - len(ext)]}{ext}"

        confirmed, ok2 = QInputDialog.getText(
            self, "Confirm Filename",
            f"Filename will be:\n{proposed}\nDo you want to proceed?",
            text=proposed
        )
        if not ok2:
            return
        final = confirmed or proposed
        if not final.lower().endswith(f".{fmt}"):
            final += f".{fmt}"

        out_path = os.path.join(download_dir, final)
        self.status_label.setText(f"Downloading transcript: {final}")
        self.error_label.clear()
        self.transcript_download_button.setEnabled(False)

        self.caption_thread = CaptionDownloadThread(
            url=self.video_url,
            caption_code=cap_code,
            out_filename=out_path,
            fmt=fmt,
            use_oauth=self.use_oauth.isChecked(),
            oauth_verifier=self._oauth_verifier
        )
        self.caption_thread.completed.connect(self.transcript_download_completed)
        self.caption_thread.error.connect(self.transcript_download_error)
        self.caption_thread.start()
        self._track_thread(self.caption_thread)

    @Slot(str)
    def transcript_download_completed(self, file_path):
        self.status_label.setText(f"Transcript saved: {file_path}")
        self.transcript_download_button.setEnabled(True)
        self.toast.show_message(f"Transcript saved: {os.path.basename(file_path)}", level="success")

    @Slot(str)
    def transcript_download_error(self, error_message):
        self.error_label.setText(f"Error: {error_message}")
        self.status_label.setText("Transcript download failed.")
        self.transcript_download_button.setEnabled(True)

    def _update_conversion_fields_state(self):
        enabled = self.conversion_mode_combo.currentText() != "No Conversion"
        self.conv_format_combo.setEnabled(enabled)
        self.conv_bitrate_combo.setEnabled(enabled)
        self.conv_sample_rate_combo.setEnabled(enabled)
        self.conv_channels_combo.setEnabled(enabled)
        if enabled:
            self._update_bitrate_state()

    def _update_bitrate_state(self):
        if not self.conv_format_combo.isEnabled():
            return
        fmt = self.conv_format_combo.currentText()
        is_lossy = AUDIO_FORMATS.get(fmt, {}).get("lossy", True)
        self.conv_bitrate_combo.setEnabled(is_lossy)

    def show_error(self, error):
        if self.sender() is not getattr(self, 'fetch_thread', None):
            return
        self.error_label.setText(f"Error: {error}")
        self.status_label.setText("Failed to fetch data.")
        self.url_entry.setEnabled(True)

    def _track_thread(self, thread):
        self._active_threads.append(thread)

    def _oauth_verifier(self, verification_url, user_code):
        with self._oauth_lock:
            self._oauth_event.clear()
            self._oauth_dialog_requested.emit(str(verification_url), str(user_code))
            self._oauth_event.wait()

    @Slot(str, str)
    def _display_oauth_dialog(self, verification_url, user_code):
        try:
            webbrowser.open(verification_url)
        except Exception:
            pass
        QMessageBox.information(
            self,
            "YouTube OAuth Authentication",
            f"A browser window was opened for YouTube authentication.\n\n"
            f"Enter this code when prompted:\n\n    {user_code}\n\n"
            f"If the browser did not open, visit:\n{verification_url}\n\n"
            f"Click OK after you have completed authentication in the browser."
        )
        self._oauth_event.set()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'toast'):
            self.toast.reposition()

    def closeEvent(self, event):
        self._oauth_event.set()
        self.player.release()
        self.download_manager.cancel_all()
        self.download_manager.wait_for_all(3000)
        for t in self._active_threads:
            if t.isRunning():
                if hasattr(t, 'cancel'):
                    t.cancel()
                t.quit()
                t.wait(3000)
        super().closeEvent(event)
