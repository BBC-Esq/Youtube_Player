import sys
import platform

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSlider, QFrame, QStyle, QStyleOptionSlider, QSizePolicy
)
from PySide6.QtCore import Qt, QTimer, Signal, QObject, QPoint
from PySide6.QtGui import QPixmap, QKeyEvent, QMouseEvent, QWheelEvent, QCursor

from app.core.audio_devices import connected_device
from app.core.headset_link import HeadsetLink, find_headset_dongle

VLC_AVAILABLE = False
vlc = None
try:
    import vlc as _vlc
    vlc = _vlc
    VLC_AVAILABLE = True
except (ImportError, OSError):
    pass

if sys.platform == "win32":
    import ctypes
    ctypes.windll.ole32.CoInitialize(None)


class VLCEventHandler(QObject):
    end_reached = Signal()
    error_occurred = Signal()

    def handle_end(self, event):
        self.end_reached.emit()

    def handle_error(self, event):
        self.error_occurred.emit()


class ClickableSlider(QSlider):
    seekRequested = Signal(int)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            opt = QStyleOptionSlider()
            self.initStyleOption(opt)
            groove = self.style().subControlRect(
                QStyle.CC_Slider, opt, QStyle.SC_SliderGroove, self
            )
            if self.orientation() == Qt.Horizontal:
                pos = event.position().x()
                val = QStyle.sliderValueFromPosition(
                    self.minimum(), self.maximum(), int(pos - groove.x()), groove.width()
                )
            else:
                pos = event.position().y()
                val = QStyle.sliderValueFromPosition(
                    self.minimum(), self.maximum(), int(pos - groove.y()), groove.height()
                )
            self.setValue(val)
            self.seekRequested.emit(val)
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if event.buttons() & Qt.LeftButton:
            opt = QStyleOptionSlider()
            self.initStyleOption(opt)
            groove = self.style().subControlRect(
                QStyle.CC_Slider, opt, QStyle.SC_SliderGroove, self
            )
            if self.orientation() == Qt.Horizontal:
                pos = event.position().x()
                val = QStyle.sliderValueFromPosition(
                    self.minimum(), self.maximum(), int(pos - groove.x()), groove.width()
                )
            else:
                pos = event.position().y()
                val = QStyle.sliderValueFromPosition(
                    self.minimum(), self.maximum(), int(pos - groove.y()), groove.height()
                )
            self.setValue(val)
            self.seekRequested.emit(val)
            event.accept()
        else:
            super().mouseMoveEvent(event)


class VideoPlayer(QWidget):
    fullscreen_toggled = Signal(bool)
    playback_started = Signal()
    playback_stopped = Signal()
    play_requested = Signal()
    error_occurred = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_playing = False
        self._is_fullscreen = False
        self._vlc_instance = None
        self._media_player = None
        self._event_handler = None
        self._current_video_url = None
        self._current_audio_url = None
        self._current_container = None
        self._live = False
        self._sound_only = False
        self._audio_device = ""
        self._headset_link = None
        self._thumbnail_pixmap = None
        self._hide_timer = QTimer()
        self._hide_timer.setSingleShot(True)
        self._hide_timer.setInterval(3000)
        self._hide_timer.timeout.connect(self._auto_hide_controls)
        self._last_cursor_pos = None
        self._cursor_timer = QTimer()
        self._cursor_timer.setInterval(200)
        self._cursor_timer.timeout.connect(self._check_cursor)

        self._build_ui()
        self._init_vlc()

        self._poll_timer = QTimer()
        self._poll_timer.setInterval(250)
        self._poll_timer.timeout.connect(self._update_position)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.video_frame = QFrame()
        self.video_frame.setStyleSheet("background-color: black;")
        self.video_frame.setMinimumHeight(300)
        self.video_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.video_frame.setMouseTracking(True)
        layout.addWidget(self.video_frame)

        self.thumbnail_label = QLabel(self.video_frame)
        self.thumbnail_label.setAlignment(Qt.AlignCenter)
        self.thumbnail_label.setStyleSheet("background-color: black;")

        self.overlay_label = QLabel(self.video_frame)
        self.overlay_label.setAlignment(Qt.AlignCenter)
        self.overlay_label.setStyleSheet("color: white; font-size: 16px; background: transparent;")
        self.overlay_label.hide()

        self.controls_widget = QWidget()
        controls_layout = QVBoxLayout(self.controls_widget)
        controls_layout.setContentsMargins(4, 2, 4, 2)
        controls_layout.setSpacing(2)

        self.position_slider = ClickableSlider(Qt.Horizontal)
        self.position_slider.setRange(0, 1000)
        self.position_slider.setMinimumHeight(28)
        self.position_slider.setStyleSheet(
            "QSlider::groove:horizontal {"
            "  height: 10px;"
            "  background: #444;"
            "  border-radius: 5px;"
            "}"
            "QSlider::handle:horizontal {"
            "  width: 20px;"
            "  height: 20px;"
            "  margin: -6px 0;"
            "  background: #ddd;"
            "  border-radius: 10px;"
            "}"
            "QSlider::sub-page:horizontal {"
            "  background: #2979ff;"
            "  border-radius: 5px;"
            "}"
        )
        self.position_slider.seekRequested.connect(self._seek_to)
        controls_layout.addWidget(self.position_slider)

        transport_layout = QHBoxLayout()
        transport_layout.setSpacing(4)

        self.play_button = QPushButton("Play")
        self.play_button.setFixedWidth(50)
        self.play_button.clicked.connect(self.toggle_play)
        transport_layout.addWidget(self.play_button)

        self.stop_button = QPushButton("Stop")
        self.stop_button.setFixedWidth(50)
        self.stop_button.clicked.connect(self.stop)
        transport_layout.addWidget(self.stop_button)

        self.time_label = QLabel("0:00 / 0:00")
        self.time_label.setFixedWidth(110)
        transport_layout.addWidget(self.time_label)

        transport_layout.addStretch()

        self.mute_button = QPushButton("Mute")
        self.mute_button.setFixedWidth(50)
        self.mute_button.clicked.connect(self._toggle_mute)
        transport_layout.addWidget(self.mute_button)

        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(75)
        self.volume_slider.setFixedWidth(100)
        self.volume_slider.valueChanged.connect(self._set_volume)
        transport_layout.addWidget(self.volume_slider)

        self.volume_label = QLabel("75%")
        self.volume_label.setFixedWidth(35)
        transport_layout.addWidget(self.volume_label)

        self.fullscreen_button = QPushButton("Full")
        self.fullscreen_button.setFixedWidth(40)
        self.fullscreen_button.clicked.connect(self.toggle_fullscreen)
        transport_layout.addWidget(self.fullscreen_button)

        controls_layout.addLayout(transport_layout)
        layout.addWidget(self.controls_widget)

        self.setFocusPolicy(Qt.StrongFocus)

    def _init_vlc(self):
        if not VLC_AVAILABLE:
            self.overlay_label.setText("VLC not found. Install VLC to enable video preview.")
            self.overlay_label.show()
            self.play_button.setEnabled(False)
            self.stop_button.setEnabled(False)
            return

        try:
            options = ["--quiet", "--no-xlib"]
            if sys.platform == "win32":
                options.append("--aout=directsound")
            self._vlc_instance = vlc.Instance(*options)
            self._media_player = self._vlc_instance.media_player_new()

            if sys.platform == "win32":
                self._media_player.set_hwnd(int(self.video_frame.winId()))
            elif sys.platform == "darwin":
                self._media_player.set_nsobject(int(self.video_frame.winId()))
            else:
                self._media_player.set_xwindow(int(self.video_frame.winId()))

            self._media_player.video_set_mouse_input(False)
            self._media_player.video_set_key_input(False)

            self._event_handler = VLCEventHandler()
            self._event_handler.end_reached.connect(self._on_end_reached)
            self._event_handler.error_occurred.connect(self._on_error)

            events = self._media_player.event_manager()
            events.event_attach(vlc.EventType.MediaPlayerEndReached, self._event_handler.handle_end)
            events.event_attach(vlc.EventType.MediaPlayerEncounteredError, self._event_handler.handle_error)

            self._media_player.audio_set_volume(75)
        except Exception as e:
            self.overlay_label.setText(f"VLC init error: {e}")
            self.overlay_label.show()
            self.play_button.setEnabled(False)
            self.stop_button.setEnabled(False)

    def set_thumbnail(self, pixmap):
        self._thumbnail_pixmap = pixmap
        if not self._is_playing or self._sound_only:
            self._show_thumbnail()

    def _show_thumbnail(self):
        if self._thumbnail_pixmap:
            self.thumbnail_label.setGeometry(self.video_frame.rect())
            scaled = self._thumbnail_pixmap.scaled(
                self.video_frame.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            self.thumbnail_label.setPixmap(scaled)
            self.thumbnail_label.show()
            self.thumbnail_label.raise_()

    def _hide_thumbnail(self):
        self.thumbnail_label.hide()

    def play_stream(self, video_url, audio_url=None, seek_ms=None, container=None, sound_only=False):
        if not VLC_AVAILABLE or not self._media_player:
            self.error_occurred.emit("VLC is not available.")
            return

        self._current_video_url = video_url
        self._current_audio_url = audio_url
        self._current_container = container
        self._live = False
        self._sound_only = sound_only
        self._pending_seek_ms = seek_ms

        media = self._vlc_instance.media_new(video_url)
        media.add_option(":network-caching=1500")
        if audio_url:
            media.add_option(f":input-slave={audio_url}")
            if container == "webm":
                media.add_option(":demux=avformat,any")
        if seek_ms and seek_ms > 0:
            media.add_option(f":start-time={seek_ms / 1000:.1f}")

        self.position_slider.setEnabled(True)
        self._start(media)

    def play_live(self, url, sound_only=False):
        if not VLC_AVAILABLE or not self._media_player:
            self.error_occurred.emit("VLC is not available.")
            return

        self._current_video_url = url
        self._current_audio_url = None
        self._current_container = None
        self._live = True
        self._sound_only = sound_only

        media = self._vlc_instance.media_new(url)
        media.add_option(":network-caching=1500")

        self.position_slider.setValue(self.position_slider.maximum())
        self.position_slider.setEnabled(False)
        self.time_label.setText("LIVE")
        self._start(media)

    def set_audio_device(self, device_id):
        self._audio_device = device_id or ""
        if self._media_player:
            self._apply_audio_device()

    def _apply_audio_device(self):
        device = connected_device(self._audio_device)
        self._update_headset_link(device)
        if device and self._headset_link and self._headset_link.headset_on is False:
            device = ""
        self._media_player.audio_output_device_set("directx", device)
        self._media_player.audio_output_device_set(None, device)

    def _update_headset_link(self, device):
        link = self._headset_link
        if link and link.device_id == device and link.is_alive():
            if link.headset_on is None:
                link.ask()
            return
        self._close_headset_link()
        path = find_headset_dongle(device)
        if not path:
            return
        link = HeadsetLink(path, device)
        link.state_changed.connect(self._on_headset_changed)
        if link.start():
            self._headset_link = link
        else:
            link.state_changed.disconnect(self._on_headset_changed)

    def _close_headset_link(self):
        link, self._headset_link = self._headset_link, None
        if link:
            link.state_changed.disconnect(self._on_headset_changed)
            link.close()

    def _on_headset_changed(self):
        if self._media_player:
            self._apply_audio_device()

    def _start(self, media):
        self._media_player.set_media(media)
        self._apply_audio_device()
        self._media_player.play()

        if self._sound_only:
            self._show_thumbnail()
        else:
            self._hide_thumbnail()
        self._is_playing = True
        self.play_button.setText("Pause")
        self._poll_timer.start()
        self.playback_started.emit()

    def is_playing_media(self):
        if not self._media_player or not vlc:
            return False
        try:
            state = self._media_player.get_state()
            if state in (vlc.State.Playing, vlc.State.Paused):
                return self._media_player.get_time() > 0
        except Exception:
            return False
        return False

    def is_live(self):
        return self._live

    def is_playing(self):
        return self._is_playing

    def get_current_time_ms(self):
        if self._media_player:
            return self._media_player.get_time()
        return 0

    def toggle_play(self):
        if not self._media_player:
            return

        if self._is_playing:
            self._media_player.pause()
            self._is_playing = False
            self.play_button.setText("Play")
            self._poll_timer.stop()
        else:
            if not self._current_video_url:
                self.play_requested.emit()
                return
            state = self._media_player.get_state()
            if vlc and state in (vlc.State.Ended, vlc.State.Stopped, vlc.State.NothingSpecial):
                if self._live:
                    self.play_live(self._current_video_url, sound_only=self._sound_only)
                else:
                    self.play_stream(self._current_video_url, self._current_audio_url,
                                     container=self._current_container, sound_only=self._sound_only)
                return
            self._media_player.play()
            self._is_playing = True
            self.play_button.setText("Pause")
            self._poll_timer.start()

    def stop(self):
        if not self._media_player:
            return
        self._media_player.stop()
        self._is_playing = False
        self._current_video_url = None
        self._current_audio_url = None
        self._current_container = None
        self._live = False
        self.play_button.setText("Play")
        self._poll_timer.stop()
        self.position_slider.setEnabled(True)
        self.position_slider.setValue(0)
        self.time_label.setText("0:00 / 0:00")
        self._show_thumbnail()
        self.playback_stopped.emit()

    def _seek_to(self, value):
        if self._media_player and self._is_playing:
            self._media_player.set_position(value / 1000.0)

    def _set_volume(self, value):
        if self._media_player:
            self._media_player.audio_set_volume(value)
        self.volume_label.setText(f"{value}%")
        if value == 0:
            self.mute_button.setText("Unmute")
        else:
            self.mute_button.setText("Mute")

    def _toggle_mute(self):
        if not self._media_player:
            return
        if self._media_player.audio_get_volume() > 0:
            self._prev_volume = self._media_player.audio_get_volume()
            self._media_player.audio_set_volume(0)
            self.volume_slider.setValue(0)
            self.mute_button.setText("Unmute")
        else:
            vol = getattr(self, '_prev_volume', 75)
            self._media_player.audio_set_volume(vol)
            self.volume_slider.setValue(vol)
            self.mute_button.setText("Mute")

    def _update_position(self):
        if not self._media_player or self._live:
            return
        pos = self._media_player.get_position()
        if pos >= 0:
            self.position_slider.blockSignals(True)
            self.position_slider.setValue(int(pos * 1000))
            self.position_slider.blockSignals(False)

        current_ms = self._media_player.get_time()
        total_ms = self._media_player.get_length()
        self.time_label.setText(f"{self._format_time(current_ms)} / {self._format_time(total_ms)}")

    @staticmethod
    def _format_time(ms):
        if ms is None or ms < 0:
            return "0:00"
        seconds = ms // 1000
        minutes = seconds // 60
        hours = minutes // 60
        if hours > 0:
            return f"{hours}:{minutes % 60:02d}:{seconds % 60:02d}"
        return f"{minutes}:{seconds % 60:02d}"

    def toggle_fullscreen(self):
        self._is_fullscreen = not self._is_fullscreen
        self.fullscreen_toggled.emit(self._is_fullscreen)
        if self._is_fullscreen:
            self._last_cursor_pos = QCursor.pos()
            self._cursor_timer.start()
            self._hide_timer.start()
        else:
            self._cursor_timer.stop()

    def _check_cursor(self):
        pos = QCursor.pos()
        if pos != self._last_cursor_pos:
            self._last_cursor_pos = pos
            self.show_controls()

    def _auto_hide_controls(self):
        if not (self._is_fullscreen and self._is_playing):
            return
        if self.controls_widget.rect().contains(self.controls_widget.mapFromGlobal(QCursor.pos())):
            self._hide_timer.start()
            return
        self.controls_widget.hide()

    def show_controls(self):
        self.controls_widget.show()
        if self._is_fullscreen:
            self._hide_timer.start()

    def _on_end_reached(self):
        self._is_playing = False
        self.play_button.setText("Play")
        self._poll_timer.stop()
        self._show_thumbnail()
        self.playback_stopped.emit()

    def _on_error(self):
        self._is_playing = False
        self.play_button.setText("Play")
        self._poll_timer.stop()
        self.error_occurred.emit("VLC playback error.")

    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()
        if key == Qt.Key_Space:
            self.toggle_play()
        elif key == Qt.Key_Left:
            self._skip(-5000)
        elif key == Qt.Key_Right:
            self._skip(5000)
        elif key == Qt.Key_Up:
            self.volume_slider.setValue(min(self.volume_slider.value() + 5, 100))
        elif key == Qt.Key_Down:
            self.volume_slider.setValue(max(self.volume_slider.value() - 5, 0))
        elif key == Qt.Key_M:
            self._toggle_mute()
        elif key in (Qt.Key_F, Qt.Key_F11):
            self.toggle_fullscreen()
        elif key == Qt.Key_Escape:
            if self._is_fullscreen:
                self.toggle_fullscreen()
        else:
            super().keyPressEvent(event)

    def wheelEvent(self, event: QWheelEvent):
        delta = event.angleDelta().y()
        if delta > 0:
            self.volume_slider.setValue(min(self.volume_slider.value() + 5, 100))
        elif delta < 0:
            self.volume_slider.setValue(max(self.volume_slider.value() - 5, 0))

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self.toggle_fullscreen()

    def _skip(self, ms):
        if not self._media_player or not self._is_playing or self._live:
            return
        current = self._media_player.get_time()
        total = self._media_player.get_length()
        if current is not None and total and total > 0:
            new_time = max(0, min(current + ms, total))
            self._media_player.set_time(new_time)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._thumbnail_pixmap and (not self._is_playing or self._sound_only):
            self._show_thumbnail()
        self.overlay_label.setGeometry(self.video_frame.rect())

    def release(self):
        self._poll_timer.stop()
        self._close_headset_link()
        if self._media_player:
            self._media_player.stop()
            self._media_player.release()
        if self._vlc_instance:
            self._vlc_instance.release()
