import os
import re
from collections import deque
from typing import Optional

from PySide6.QtCore import QObject, Signal, Slot

from app.constants import AUDIO_FORMATS, CODEC_SAMPLE_FORMATS, detect_mux_container
from app.core.download_job import DownloadJob, JobStatus
from app.threads import DownloadThread, MuxThread, ConversionThread, FetchThread


def _sanitize_filename(title: str) -> str:
    return re.sub(r'[\\/*?:"<>|]', "", title)


class DownloadManager(QObject):
    job_added = Signal(str)
    job_updated = Signal(str)
    job_finished = Signal(str, str)
    job_failed = Signal(str, str)

    def __init__(self, parent=None, oauth_verifier=None):
        super().__init__(parent)
        self._jobs: dict[str, DownloadJob] = {}
        self._queue: deque[str] = deque()
        self._running: set[str] = set()
        self._max_concurrent: int = 1
        self._oauth_verifier = oauth_verifier
        self._tracked_threads: list = []

    def set_oauth_verifier(self, verifier):
        self._oauth_verifier = verifier

    def _track_thread(self, thread):
        self._tracked_threads.append(thread)

    def wait_for_all(self, timeout_ms: int = 3000):
        for thread in list(self._tracked_threads):
            if thread.isRunning():
                if hasattr(thread, "cancel"):
                    try:
                        thread.cancel()
                    except Exception:
                        pass
                thread.quit()
                thread.wait(timeout_ms)

    def get_job(self, job_id: str) -> Optional[DownloadJob]:
        return self._jobs.get(job_id)

    def all_jobs(self) -> list[DownloadJob]:
        return list(self._jobs.values())

    def active_job_count(self) -> int:
        return len(self._running) + len(self._queue)

    def enqueue(self, job: DownloadJob) -> str:
        self._jobs[job.job_id] = job
        self._queue.append(job.job_id)
        self.job_added.emit(job.job_id)
        self._pump()
        return job.job_id

    def cancel(self, job_id: str):
        job = self._jobs.get(job_id)
        if not job:
            return
        if job.status in (JobStatus.DONE, JobStatus.FAILED, JobStatus.CANCELLED):
            return
        if job_id in self._queue:
            try:
                self._queue.remove(job_id)
            except ValueError:
                pass
            job.status = JobStatus.CANCELLED
            self.job_updated.emit(job_id)
            return
        if job.current_thread is not None and hasattr(job.current_thread, "cancel"):
            try:
                job.current_thread.cancel()
            except Exception:
                pass

    def cancel_all(self):
        for jid in list(self._jobs.keys()):
            self.cancel(jid)

    def remove(self, job_id: str):
        job = self._jobs.get(job_id)
        if not job:
            return
        if job.status == JobStatus.QUEUED and job_id in self._queue:
            try:
                self._queue.remove(job_id)
            except ValueError:
                pass
            self._jobs.pop(job_id, None)
            self.job_updated.emit(job_id)
            return
        if job.status in (JobStatus.DONE, JobStatus.FAILED, JobStatus.CANCELLED):
            self._jobs.pop(job_id, None)
            self.job_updated.emit(job_id)

    def clear_finished(self):
        for jid in [j.job_id for j in self._jobs.values()
                    if j.status in (JobStatus.DONE, JobStatus.FAILED, JobStatus.CANCELLED)]:
            self._jobs.pop(jid, None)
            self.job_updated.emit(jid)

    def _pump(self):
        while self._queue and len(self._running) < self._max_concurrent:
            job_id = self._queue.popleft()
            job = self._jobs.get(job_id)
            if not job:
                continue
            if job.status == JobStatus.CANCELLED:
                continue
            self._running.add(job_id)
            self._start_job(job)

    def _update(self, job: DownloadJob):
        self.job_updated.emit(job.job_id)

    def _finish_ok(self, job: DownloadJob, final_path: str):
        job.status = JobStatus.DONE
        job.progress = 100
        job.current_thread = None
        self._running.discard(job.job_id)
        self.job_updated.emit(job.job_id)
        self.job_finished.emit(job.job_id, final_path)
        self._pump()

    def _finish_fail(self, job: DownloadJob, error: str):
        job.status = JobStatus.FAILED
        job.error = error
        job.current_thread = None
        job.cleanup_temp_files()
        self._running.discard(job.job_id)
        self.job_updated.emit(job.job_id)
        self.job_failed.emit(job.job_id, error)
        self._pump()

    def _finish_cancel(self, job: DownloadJob):
        job.status = JobStatus.CANCELLED
        job.current_thread = None
        job.cleanup_temp_files()
        self._running.discard(job.job_id)
        self.job_updated.emit(job.job_id)
        self._pump()

    def _start_job(self, job: DownloadJob):
        base_title = _sanitize_filename(job.title or "video")
        prefix = job.job_id

        if job.audio_only:
            stream = job.audio_stream
            if stream is None:
                self._finish_fail(job, "No audio stream.")
                return
            bitrate = stream.abr or "unknown"
            filename = f"{base_title}_Audio_{bitrate}.{stream.subtype}"
            if len(filename) > 200:
                ext = f".{stream.subtype}"
                filename = f"{filename[:200 - len(ext)]}{ext}"
            job.final_filename = filename
            job.final_output_path = os.path.join(job.output_dir, filename)

            job.status = JobStatus.DOWNLOADING_AUDIO
            job.progress = 0
            self._update(job)

            thread = DownloadThread(
                stream=stream,
                output_path=job.output_dir,
                filename=filename,
                skip_existing=False,
            )
            thread.progress.connect(lambda p, jid=job.job_id: self._on_progress(jid, p))
            thread.completed.connect(lambda path, jid=job.job_id: self._on_audio_only_done(jid, path))
            thread.error.connect(lambda msg, jid=job.job_id: self._on_thread_error(jid, msg))
            job.current_thread = thread

            self._track_thread(thread)
            thread.start()
            return

        video_stream = job.video_stream
        audio_stream = job.audio_stream
        if video_stream is None or audio_stream is None:
            self._finish_fail(job, "Missing stream.")
            return

        res = video_stream.resolution or "unknown"
        video_filename = f".{prefix}_{base_title}_video_temp.{video_stream.subtype}"
        audio_filename = f".{prefix}_{base_title}_audio_temp.{audio_stream.subtype}"
        job.temp_video_path = os.path.join(job.output_dir, video_filename)
        job.temp_audio_path = os.path.join(job.output_dir, audio_filename)

        container_fmt, container_ext = detect_mux_container(
            video_stream.video_codec, audio_stream.audio_codec
        )
        final_filename = f"{base_title}_{res}{container_ext}"
        if len(final_filename) > 200:
            final_filename = f"{final_filename[:200 - len(container_ext)]}{container_ext}"
        job.final_filename = final_filename
        job.final_output_path = os.path.join(job.output_dir, final_filename)
        job.mux_container_format = container_fmt

        job.status = JobStatus.DOWNLOADING_VIDEO
        job.progress = 0
        self._update(job)

        thread = DownloadThread(
            stream=video_stream,
            output_path=job.output_dir,
            filename=video_filename,
            skip_existing=False,
        )
        thread.progress.connect(lambda p, jid=job.job_id: self._on_progress(jid, p))
        thread.completed.connect(lambda path, jid=job.job_id: self._on_video_done(jid, path))
        thread.error.connect(lambda msg, jid=job.job_id: self._on_thread_error(jid, msg))
        job.current_thread = thread

        self._track_thread(thread)
        thread.start()

    @Slot(str, int)
    def _on_progress(self, job_id: str, percent: int):
        job = self._jobs.get(job_id)
        if not job:
            return
        job.progress = percent
        self._update(job)

    def _on_video_done(self, job_id: str, video_path: str):
        job = self._jobs.get(job_id)
        if not job:
            return
        job.temp_video_path = video_path
        job.status = JobStatus.DOWNLOADING_AUDIO
        job.progress = 0
        self._update(job)

        audio_filename = os.path.basename(job.temp_audio_path)
        thread = DownloadThread(
            stream=job.audio_stream,
            output_path=job.output_dir,
            filename=audio_filename,
            skip_existing=False,
        )
        thread.progress.connect(lambda p, jid=job.job_id: self._on_progress(jid, p))
        thread.completed.connect(lambda path, jid=job.job_id: self._on_audio_for_mux_done(jid, path))
        thread.error.connect(lambda msg, jid=job.job_id: self._on_thread_error(jid, msg))
        job.current_thread = thread

        self._track_thread(thread)
        thread.start()

    def _on_audio_for_mux_done(self, job_id: str, audio_path: str):
        job = self._jobs.get(job_id)
        if not job:
            return
        job.temp_audio_path = audio_path
        job.status = JobStatus.MUXING
        job.progress = 0
        self._update(job)

        thread = MuxThread(
            video_path=job.temp_video_path,
            audio_path=job.temp_audio_path,
            output_path=job.final_output_path,
            container_format=job.mux_container_format,
        )
        thread.progress.connect(lambda p, jid=job.job_id: self._on_progress(jid, p))
        thread.completed.connect(lambda path, jid=job.job_id: self._on_mux_done(jid, path))
        thread.error.connect(lambda msg, jid=job.job_id: self._on_thread_error(jid, msg))
        job.current_thread = thread

        self._track_thread(thread)
        thread.start()

    def _on_mux_done(self, job_id: str, output_path: str):
        job = self._jobs.get(job_id)
        if not job:
            return
        job.cleanup_temp_files()
        self._finish_ok(job, output_path)

    def _on_audio_only_done(self, job_id: str, file_path: str):
        job = self._jobs.get(job_id)
        if not job:
            return
        if job.convert_after and job.conversion_params:
            self._start_conversion(job, file_path)
            return
        self._finish_ok(job, file_path)

    def _start_conversion(self, job: DownloadJob, input_path: str):
        params = job.conversion_params or {}
        fmt_name = params.get("format", "MP3")
        fmt_config = AUDIO_FORMATS.get(fmt_name, AUDIO_FORMATS["MP3"])
        bitrate = params.get("bitrate", 192000)
        sample_rate = params.get("sample_rate", 44100)
        channels = params.get("channels", 2)
        mode = params.get("mode", "Convert and Keep Original")

        base, _ = os.path.splitext(input_path)
        output_path = f"{base}.{fmt_config['extension']}"
        if os.path.normpath(output_path) == os.path.normpath(input_path):
            output_path = f"{base}_converted.{fmt_config['extension']}"

        codec = fmt_config["codec"]
        sample_format = CODEC_SAMPLE_FORMATS.get(codec, "fltp")

        job._original_audio_path = input_path
        job._conversion_mode = mode
        job.status = JobStatus.CONVERTING
        job.progress = 0
        self._update(job)

        thread = ConversionThread(
            input_path=input_path,
            output_path=output_path,
            codec=codec,
            container=fmt_config["container"],
            sample_format=sample_format,
            bitrate=bitrate if fmt_config["lossy"] else None,
            sample_rate=sample_rate,
            channels=channels,
        )
        thread.progress.connect(lambda p, jid=job.job_id: self._on_progress(jid, p))
        thread.completed.connect(lambda path, jid=job.job_id: self._on_conversion_done(jid, path))
        thread.error.connect(lambda msg, jid=job.job_id: self._on_thread_error(jid, msg))
        job.current_thread = thread

        self._track_thread(thread)
        thread.start()

    def _on_conversion_done(self, job_id: str, converted_path: str):
        job = self._jobs.get(job_id)
        if not job:
            return
        mode = getattr(job, "_conversion_mode", "Convert and Keep Original")
        original = getattr(job, "_original_audio_path", "")
        if mode == "Convert and Delete Original" and original and os.path.exists(original):
            try:
                os.remove(original)
            except OSError:
                pass
        self._finish_ok(job, converted_path)

    def _on_thread_error(self, job_id: str, error_message: str):
        job = self._jobs.get(job_id)
        if not job:
            return
        err_lower = error_message.lower()
        if "cancelled" in err_lower:
            self._finish_cancel(job)
            return
        is_expired = (
            "403" in error_message
            or "forbidden" in err_lower
            or "expired" in err_lower
            or "signature" in err_lower
        )
        if is_expired and not job.retry_attempted:
            job.retry_attempted = True
            self._refetch_and_retry(job)
            return
        self._finish_fail(job, error_message)

    def _refetch_and_retry(self, job: DownloadJob):
        job.cleanup_temp_files()
        job.current_thread = None
        thread = FetchThread(job.url, use_oauth=job.use_oauth,
                             oauth_verifier=self._oauth_verifier)
        thread.finished.connect(
            lambda si, ci, so, st, tu, jid=job.job_id: self._on_refetch_done(jid, so)
        )
        thread.error.connect(
            lambda msg, jid=job.job_id: self._on_thread_error(jid, msg)
        )
        job.current_thread = thread

        self._track_thread(thread)
        thread.start()

    def _on_refetch_done(self, job_id: str, streams_objects):
        job = self._jobs.get(job_id)
        if not job:
            return
        if job.audio_only:
            match = next((s for s in streams_objects if s.itag == job.audio_itag), None)
            if match is None:
                self._finish_fail(job, "Audio stream no longer available after re-fetch.")
                return
            job.audio_stream = match
        else:
            v = next((s for s in streams_objects if s.itag == job.video_itag), None)
            a = next((s for s in streams_objects if s.itag == job.audio_itag), None)
            if v is None or a is None:
                self._finish_fail(job, "Stream no longer available after re-fetch.")
                return
            job.video_stream = v
            job.audio_stream = a
        self._start_job(job)
