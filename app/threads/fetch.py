import time

from PySide6.QtCore import QThread, Signal

from pytubefix import YouTube
from pytubefix.exceptions import BotDetection

BOT_RETRY_DELAY_SECONDS = 2.0

BOT_DETECTION_MESSAGE = (
    "YouTube temporarily refused this request (bot detection). "
    "This is a rate limit on YouTube's side, not a problem with the video. "
    "Wait a moment and try again."
)


class FetchThread(QThread):
    finished = Signal(list, list, list, str, str)
    error = Signal(str)
    client_switched = Signal(str, str)
    retrying = Signal()

    def __init__(self, url, use_oauth=False, oauth_verifier=None):
        super().__init__()
        self.url = url
        self.use_oauth = use_oauth
        self.oauth_verifier = oauth_verifier
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def _wait_before_retry(self):
        deadline = time.monotonic() + BOT_RETRY_DELAY_SECONDS
        while time.monotonic() < deadline:
            if self._cancelled:
                return False
            time.sleep(0.1)
        return not self._cancelled

    def _fetch(self):
        yt_kwargs = {"use_oauth": self.use_oauth}
        if self.use_oauth:
            yt_kwargs["allow_oauth_cache"] = True
            if self.oauth_verifier is not None:
                yt_kwargs["oauth_verifier"] = self.oauth_verifier
        yt = YouTube(self.url, **yt_kwargs)
        original_client = yt.client

        streams_info = []
        streams_objects = []

        for stream in yt.streams:
            stream_info = (
                f"Itag: {stream.itag} | Type: {stream.type.capitalize()} | "
                f"Resolution: {getattr(stream, 'resolution', 'N/A')} | "
                f"FPS: {getattr(stream, 'fps', 'N/A')} | "
                f"Mime Type: {stream.mime_type} | "
                f"Filesize: {stream.filesize_mb:.2f} MB | "
                f"Adaptive: {'Yes' if stream.is_adaptive else 'No'} | "
                f"Progressive: {'Yes' if stream.is_progressive else 'No'} | "
                f"Audio: {'Yes' if stream.includes_audio_track else 'No'} | "
                f"Video: {'Yes' if stream.includes_video_track else 'No'}"
            )
            streams_info.append(stream_info)
            streams_objects.append(stream)

        captions_info = []
        for caption in yt.captions:
            captions_info.append({
                "code": caption.code,
                "name": caption.name
            })

        thumbnail_url = yt.thumbnail_url or ""

        return yt, original_client, streams_info, captions_info, streams_objects, thumbnail_url

    def run(self):
        try:
            try:
                result = self._fetch()
            except BotDetection:
                if self._cancelled:
                    return
                self.retrying.emit()
                if not self._wait_before_retry():
                    return
                result = self._fetch()

            yt, original_client, streams_info, captions_info, streams_objects, thumbnail_url = result

            if self._cancelled:
                return

            if yt.client != original_client:
                self.client_switched.emit(original_client, yt.client)

            self.finished.emit(streams_info, captions_info, streams_objects, "Data fetched successfully.", thumbnail_url)
        except BotDetection:
            if not self._cancelled:
                self.error.emit(BOT_DETECTION_MESSAGE)
        except Exception as e:
            if not self._cancelled:
                self.error.emit(str(e))
