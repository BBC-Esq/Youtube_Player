import re
import urllib.request

from PySide6.QtCore import QThread, Signal

from pytubefix import YouTube
from pytubefix.exceptions import BotDetection, LiveStreamError

FETCH_CLIENT_FALLBACKS = ("MWEB", "WEB")

LIVE_CLIENT = "VISION_OS"

LIVE_UNAVAILABLE_MESSAGE = (
    "YouTube did not offer a playable stream for this live broadcast. "
    "Use Watch in Browser to watch it."
)

BOT_DETECTION_MESSAGE = (
    "YouTube refused this request on every client tried ({clients}). "
    "Some videos are restricted to clients this app cannot use; others are a "
    "temporary rate limit that clears on its own after a short wait."
)

REFUSED_REASON = "YouTube refused the request"
PROTECTED_REASON = "YouTube only offered protected streams"


def _has_protected_streams(streams):
    return any(stream.is_sabr and not stream.po_token for stream in streams)


def _live_resolutions(hls_url):
    request = urllib.request.Request(hls_url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=15) as response:
        playlist = response.read().decode("utf-8", "replace")
    fps_by_height = {}
    for line in playlist.splitlines():
        if not line.startswith("#EXT-X-STREAM-INF:"):
            continue
        height = re.search(r"RESOLUTION=\d+x(\d+)", line)
        fps = re.search(r"FRAME-RATE=([\d.]+)", line)
        if height:
            height = int(height.group(1))
            fps = round(float(fps.group(1))) if fps else 30
            fps_by_height[height] = max(fps_by_height.get(height, 0), fps)
    return [
        f"{height}p{fps if fps > 30 else ''}"
        for height, fps in sorted(fps_by_height.items(), reverse=True)
    ]


def _default_client_name():
    try:
        from pytubefix.innertube import InnerTube
        return InnerTube().client_name
    except Exception:
        return "default"


class FetchThread(QThread):
    finished = Signal(list, list, list, str, str)
    live_found = Signal(str, str, list, str)
    error = Signal(str)
    blocked = Signal()
    client_switched = Signal(str, str)
    retrying = Signal(str)

    def __init__(self, url, use_oauth=False, oauth_verifier=None):
        super().__init__()
        self.url = url
        self.use_oauth = use_oauth
        self.oauth_verifier = oauth_verifier
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def _fetch(self, client=None):
        yt_kwargs = {"use_oauth": self.use_oauth}
        if client:
            yt_kwargs["client"] = client
        if self.use_oauth:
            yt_kwargs["allow_oauth_cache"] = True
            if self.oauth_verifier is not None:
                yt_kwargs["oauth_verifier"] = self.oauth_verifier
        yt = YouTube(self.url, **yt_kwargs)
        original_client = yt.client

        streams_info = []
        streams_objects = []

        for stream in yt.streams:
            try:
                filesize_text = f"{stream.filesize_mb:.2f} MB"
            except Exception:
                filesize_text = "unknown"
            stream_info = (
                f"Itag: {stream.itag} | Type: {stream.type.capitalize()} | "
                f"Resolution: {getattr(stream, 'resolution', 'N/A')} | "
                f"FPS: {getattr(stream, 'fps', 'N/A')} | "
                f"Mime Type: {stream.mime_type} | "
                f"Filesize: {filesize_text} | "
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

    def _fetch_live(self):
        yt = YouTube(self.url, client=LIVE_CLIENT)
        hls_url = yt.vid_info.get("streamingData", {}).get("hlsManifestUrl")
        if not hls_url:
            self.error.emit(LIVE_UNAVAILABLE_MESSAGE)
            return
        resolutions = _live_resolutions(hls_url)
        if not self._cancelled:
            self.live_found.emit(yt.title, hls_url, resolutions, yt.thumbnail_url or "")

    def _fetch_with_fallbacks(self):
        attempts = (None,) + FETCH_CLIENT_FALLBACKS
        tried = []
        protected = None
        reason = ""
        for index, client in enumerate(attempts):
            if self._cancelled:
                return None
            if index:
                self.retrying.emit(f"{reason}, trying the {client} client...")
            try:
                result = self._fetch(client)
            except BotDetection:
                tried.append(client or _default_client_name())
                reason = REFUSED_REASON
                continue
            except LiveStreamError:
                if not self._cancelled:
                    self._fetch_live()
                return None
            except Exception:
                if protected is None:
                    raise
                continue
            if not _has_protected_streams(result[4]):
                return result
            if protected is None:
                protected = result
            reason = PROTECTED_REASON
        if protected is not None:
            return protected
        if not self._cancelled:
            self.error.emit(BOT_DETECTION_MESSAGE.format(clients=", ".join(tried)))
            self.blocked.emit()
        return None

    def run(self):
        try:
            result = self._fetch_with_fallbacks()
            if result is None or self._cancelled:
                return

            yt, original_client, streams_info, captions_info, streams_objects, thumbnail_url = result

            if yt.client != original_client:
                self.client_switched.emit(original_client, yt.client)

            self.finished.emit(streams_info, captions_info, streams_objects, "Data fetched successfully.", thumbnail_url)
        except Exception as e:
            if not self._cancelled:
                self.error.emit(str(e))
