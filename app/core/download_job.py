import os
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class JobStatus(Enum):
    QUEUED = "Queued"
    DOWNLOADING_VIDEO = "Downloading video"
    DOWNLOADING_AUDIO = "Downloading audio"
    MUXING = "Muxing"
    CONVERTING = "Converting"
    DONE = "Done"
    FAILED = "Failed"
    CANCELLED = "Cancelled"


@dataclass
class DownloadJob:
    url: str
    title: str
    output_dir: str
    audio_only: bool
    use_oauth: bool
    video_itag: Optional[int] = None
    audio_itag: Optional[int] = None
    video_stream: Any = None
    audio_stream: Any = None
    final_filename: str = ""
    final_output_path: str = ""
    mux_container_format: str = ""
    convert_after: bool = False
    conversion_params: Optional[dict] = None
    temp_video_path: str = ""
    temp_audio_path: str = ""
    job_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    status: JobStatus = JobStatus.QUEUED
    progress: int = 0
    error: str = ""
    retry_attempted: bool = False
    current_thread: Any = None
    thumbnail_pixmap: Any = None

    def display_status(self) -> str:
        if self.status == JobStatus.FAILED and self.error:
            return f"Failed: {self.error[:60]}"
        return self.status.value

    def cleanup_temp_files(self):
        for path in (self.temp_video_path, self.temp_audio_path):
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    pass
