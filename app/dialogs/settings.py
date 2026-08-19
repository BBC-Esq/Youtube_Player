import os
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGroupBox,
    QLineEdit, QPushButton, QFileDialog, QMessageBox, QCheckBox
)
from PySide6.QtCore import QSettings

from app.core.adblock import AUTOPLAY_SETTING_KEY


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(450)

        self.settings = QSettings("YouTubeDownloader", "YouTubeDownloader")

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

        button_layout = QHBoxLayout()
        save_button = QPushButton("Save")
        save_button.clicked.connect(self.save_settings)
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        button_layout.addStretch()
        button_layout.addWidget(save_button)
        button_layout.addWidget(cancel_button)

        layout.addLayout(button_layout)

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
        self.accept()
