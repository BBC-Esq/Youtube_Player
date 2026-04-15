from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QProgressBar, QScrollArea, QFrame, QGroupBox
)
from PySide6.QtCore import Qt, Signal

from app.core.download_job import JobStatus


class JobRow(QFrame):
    cancel_requested = Signal(str)
    remove_requested = Signal(str)

    def __init__(self, job_id: str, title: str, parent=None):
        super().__init__(parent)
        self.job_id = job_id
        self.setFrameShape(QFrame.StyledPanel)
        self.setFrameShadow(QFrame.Raised)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(6)

        info_layout = QVBoxLayout()
        info_layout.setSpacing(2)

        self.title_label = QLabel(title)
        self.title_label.setStyleSheet("font-weight: bold;")
        self.title_label.setWordWrap(False)
        self.title_label.setMaximumWidth(400)
        self.title_label.setToolTip(title)
        info_layout.addWidget(self.title_label)

        row2 = QHBoxLayout()
        row2.setSpacing(6)
        self.status_label = QLabel("Queued")
        self.status_label.setStyleSheet("color: #555;")
        row2.addWidget(self.status_label)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(True)
        self.progress.setFormat("%p%")
        self.progress.setMaximumHeight(14)
        row2.addWidget(self.progress, stretch=1)
        info_layout.addLayout(row2)

        layout.addLayout(info_layout, stretch=1)

        self.action_button = QPushButton("Remove")
        self.action_button.setFixedWidth(70)
        self.action_button.clicked.connect(self._on_action_clicked)
        layout.addWidget(self.action_button)

        self._mode = "remove"

    def _on_action_clicked(self):
        if self._mode == "cancel":
            self.cancel_requested.emit(self.job_id)
        else:
            self.remove_requested.emit(self.job_id)

    def update_from_job(self, job):
        self.status_label.setText(job.display_status())
        self.progress.setValue(job.progress)
        if job.status == JobStatus.QUEUED:
            self._mode = "remove"
            self.action_button.setText("Remove")
            self.status_label.setStyleSheet("color: #555;")
        elif job.status in (JobStatus.DONE, JobStatus.FAILED, JobStatus.CANCELLED):
            self._mode = "remove"
            self.action_button.setText("Remove")
            if job.status == JobStatus.DONE:
                self.status_label.setStyleSheet("color: green; font-weight: bold;")
                self.progress.setValue(100)
            elif job.status == JobStatus.FAILED:
                self.status_label.setStyleSheet("color: red;")
                self.status_label.setToolTip(job.error)
            else:
                self.status_label.setStyleSheet("color: #888;")
        else:
            self._mode = "cancel"
            self.action_button.setText("Cancel")
            self.status_label.setStyleSheet("color: #555;")


class DownloadsPanel(QGroupBox):
    cancel_requested = Signal(str)
    remove_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__("Downloads", parent)
        self._rows: dict[str, JobRow] = {}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 6, 6, 6)
        outer.setSpacing(4)

        header = QHBoxLayout()
        self.count_label = QLabel("No active downloads.")
        header.addWidget(self.count_label)
        header.addStretch()
        outer.addLayout(header)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setMinimumHeight(120)
        self.scroll.setMaximumHeight(220)
        self.container = QWidget()
        self.container_layout = QVBoxLayout(self.container)
        self.container_layout.setContentsMargins(2, 2, 2, 2)
        self.container_layout.setSpacing(3)
        self.container_layout.addStretch()
        self.scroll.setWidget(self.container)
        outer.addWidget(self.scroll)

    def _refresh_count(self, jobs):
        active = sum(1 for j in jobs if j.status in (
            JobStatus.QUEUED, JobStatus.DOWNLOADING_VIDEO, JobStatus.DOWNLOADING_AUDIO,
            JobStatus.MUXING, JobStatus.CONVERTING
        ))
        done = sum(1 for j in jobs if j.status == JobStatus.DONE)
        failed = sum(1 for j in jobs if j.status == JobStatus.FAILED)
        if not jobs:
            self.count_label.setText("No downloads.")
        else:
            parts = []
            if active:
                parts.append(f"{active} active")
            if done:
                parts.append(f"{done} done")
            if failed:
                parts.append(f"{failed} failed")
            self.count_label.setText(", ".join(parts) if parts else "No active downloads.")

    def add_job(self, job):
        if job.job_id in self._rows:
            return
        row = JobRow(job.job_id, job.title or "(untitled)")
        row.cancel_requested.connect(self.cancel_requested.emit)
        row.remove_requested.connect(self.remove_requested.emit)
        row.update_from_job(job)
        self.container_layout.insertWidget(self.container_layout.count() - 1, row)
        self._rows[job.job_id] = row

    def update_job(self, job):
        row = self._rows.get(job.job_id)
        if row is not None:
            row.update_from_job(job)

    def remove_job(self, job_id: str):
        row = self._rows.pop(job_id, None)
        if row is not None:
            row.setParent(None)
            row.deleteLater()

    def sync(self, jobs):
        self._refresh_count(jobs)
