import os
import sys
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
    QLineEdit, QPushButton, QFileDialog, QMessageBox, QCheckBox, QSpinBox, QComboBox
)

from app.core.adblock import AUTOPLAY_SETTING_KEY
from app.core.app_settings import app_settings
from app.core.audio_devices import (
    AUDIO_DEVICE_SETTING_KEY, AUDIO_DEVICE_NAME_SETTING_KEY, output_devices
)
from app.core.cpu import (
    CONVERSION_WORKERS_SETTING_KEY, RESERVED_PHYSICAL_CORES,
    configured_conversion_workers, max_conversion_workers, physical_core_count
)


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(450)

        self.settings = app_settings()

        layout = QVBoxLayout(self)

        download_group = QGroupBox("Download Location")
        download_layout = QHBoxLayout(download_group)

        self.path_edit = QLineEdit()
        self.path_edit.setReadOnly(True)
        self.path_edit.setPlaceholderText("No download folder selected")
        current_path = self.settings.value("download_directory", "")
        if current_path:
            self.path_edit.setText(current_path)

        browse_button = QPushButton("Browse...")
        browse_button.clicked.connect(self.browse_folder)

        download_layout.addWidget(self.path_edit)
        download_layout.addWidget(browse_button)

        layout.addWidget(download_group)

        playback_group = QGroupBox("Browser Playback")
        playback_layout = QVBoxLayout(playback_group)
        self.autoplay_checkbox = QCheckBox("Autoplay next video")
        self.autoplay_checkbox.setToolTip(
            "When off, the browser player stays on the video you opened. When on, "
            "YouTube may continue to the next video when this one ends."
        )
        self.autoplay_checkbox.setChecked(
            self.settings.value(AUTOPLAY_SETTING_KEY, False, type=bool)
        )
        playback_layout.addWidget(self.autoplay_checkbox)
        layout.addWidget(playback_group)

        self.device_combo = None
        if sys.platform == "win32":
            layout.addWidget(self._build_sound_group())

        conversion_group = QGroupBox("Audio Conversion")
        conversion_layout = QVBoxLayout(conversion_group)
        limit = max_conversion_workers()
        physical = physical_core_count()
        spin_row = QHBoxLayout()
        spin_row.addWidget(QLabel("Conversions at once:"))
        self.conversion_spin = QSpinBox()
        self.conversion_spin.setRange(1, limit)
        self.conversion_spin.setValue(configured_conversion_workers(self.settings))
        self.conversion_spin.setEnabled(limit > 1)
        spin_row.addWidget(self.conversion_spin)
        spin_row.addStretch()
        conversion_layout.addLayout(spin_row)
        if not physical:
            detail = ("This computer's physical cores could not be detected, "
                      "so conversions run one at a time.")
        elif physical - RESERVED_PHYSICAL_CORES < 1:
            detail = (f"This computer has {physical} physical cores, "
                      "so conversions run one at a time.")
        else:
            detail = (f"Up to {limit} on this computer: {physical} physical cores, "
                      f"{RESERVED_PHYSICAL_CORES} kept free. Downloads always run one at a time.")
        detail_label = QLabel(detail)
        detail_label.setWordWrap(True)
        detail_label.setStyleSheet("font-size: 11px;")
        conversion_layout.addWidget(detail_label)
        layout.addWidget(conversion_group)

        button_layout = QHBoxLayout()
        save_button = QPushButton("Save")
        save_button.clicked.connect(self.save_settings)
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        button_layout.addStretch()
        button_layout.addWidget(save_button)
        button_layout.addWidget(cancel_button)

        layout.addLayout(button_layout)

    def _build_sound_group(self):
        group = QGroupBox("Sound Output")
        group_layout = QVBoxLayout(group)
        row = QHBoxLayout()
        row.addWidget(QLabel("Play sound through:"))
        self.device_combo = QComboBox()
        self.device_combo.addItem("Windows default device", "")
        self._device_names = {"": ""}
        for device_id, name in output_devices():
            self.device_combo.addItem(name, device_id)
            self._device_names[device_id] = name
        saved_id = self.settings.value(AUDIO_DEVICE_SETTING_KEY, "", type=str)
        if saved_id:
            index = self.device_combo.findData(saved_id)
            if index < 0:
                saved_name = (self.settings.value(AUDIO_DEVICE_NAME_SETTING_KEY, "", type=str)
                              or "Chosen device")
                self.device_combo.addItem(f"{saved_name} (not connected)", saved_id)
                self._device_names[saved_id] = saved_name
                index = self.device_combo.count() - 1
            self.device_combo.setCurrentIndex(index)
        row.addWidget(self.device_combo, stretch=1)
        group_layout.addLayout(row)
        note = QLabel(
            "The player's sound goes to this device without changing the Windows default. "
            "While the device is unplugged, or a Razer Barracuda Pro headset on its 2.4 GHz "
            "dongle is switched off, the Windows default is used instead. "
            "Watch in Browser always uses the Windows default."
        )
        note.setWordWrap(True)
        note.setStyleSheet("font-size: 11px;")
        group_layout.addWidget(note)
        return group

    def browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Download Folder")
        if folder:
            self.path_edit.setText(folder)

    def save_settings(self):
        path = self.path_edit.text().strip()
        if path and not os.path.isdir(path):
            QMessageBox.warning(self, "Invalid Path", "The selected folder does not exist.")
            return
        self.settings.setValue("download_directory", path)
        self.settings.setValue(AUTOPLAY_SETTING_KEY, self.autoplay_checkbox.isChecked())
        self.settings.setValue(CONVERSION_WORKERS_SETTING_KEY, self.conversion_spin.value())
        if self.device_combo is not None:
            device_id = self.device_combo.currentData() or ""
            self.settings.setValue(AUDIO_DEVICE_SETTING_KEY, device_id)
            self.settings.setValue(AUDIO_DEVICE_NAME_SETTING_KEY, self._device_names.get(device_id, ""))
        self.accept()
