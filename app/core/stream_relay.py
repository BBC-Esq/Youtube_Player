import re
import secrets
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import av
from av.stream import Discard

CHUNK_SIZE = 4 * 1024 * 1024
BLOCK_SIZE = 64 * 1024
UPSTREAM_HEADERS = {"User-Agent": "Mozilla/5.0", "accept-language": "en-US,en"}
UPSTREAM_TIMEOUT = 20
UPSTREAM_ATTEMPTS = 3


def _open_upstream(url, first, last):
    request = urllib.request.Request(f"{url}&range={first}-{last}", headers=UPSTREAM_HEADERS)
    return urllib.request.urlopen(request, timeout=UPSTREAM_TIMEOUT)


def _pick_live_streams(container, max_height, audio_only):
    audio = max(container.streams.audio, key=lambda s: s.codec_context.bit_rate or 0, default=None)
    if audio_only:
        return [audio] if audio else []
    videos = list(container.streams.video)
    fitting = [s for s in videos if not max_height or s.codec_context.height <= max_height] or videos
    video = max(
        fitting,
        key=lambda s: (s.codec_context.height, int(s.metadata.get("variant_bitrate", 0))),
        default=None,
    )
    return [s for s in (video, audio) if s is not None]


class _RelayHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        key = self.path.lstrip("/")
        live = self.server.live.get(key)
        if live is not None:
            self._relay_live(*live)
            return
        entry = self.server.streams.get(key)
        if entry is None:
            self.send_error(404)
            return
        url, size, mime_type = entry

        start, end = 0, size - 1
        match = re.match(r"bytes=(\d*)-(\d*)", self.headers.get("Range", ""))
        if match:
            if match.group(1):
                start = int(match.group(1))
            if match.group(2):
                end = min(int(match.group(2)), size - 1)
        if start >= size or start > end:
            self.send_response(416)
            self.send_header("Content-Range", f"bytes */{size}")
            self.end_headers()
            return

        try:
            upstream = _open_upstream(url, start, min(start + CHUNK_SIZE - 1, end))
        except Exception:
            self.send_error(502)
            return

        self.send_response(206 if match else 200)
        self.send_header("Content-Type", mime_type)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        if match:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()

        position = start
        failures = 0
        while position <= end:
            if upstream is None:
                try:
                    upstream = _open_upstream(url, position, min(position + CHUNK_SIZE - 1, end))
                except Exception:
                    failures += 1
                    if failures >= UPSTREAM_ATTEMPTS:
                        return
                    continue
            with upstream:
                while True:
                    try:
                        block = upstream.read(BLOCK_SIZE)
                    except Exception:
                        failures += 1
                        if failures >= UPSTREAM_ATTEMPTS:
                            return
                        break
                    if not block:
                        break
                    try:
                        self.wfile.write(block)
                    except OSError:
                        return
                    position += len(block)
                    failures = 0
            upstream = None

    def _relay_live(self, hls_url, max_height, audio_only):
        try:
            source = av.open(hls_url, options={"user_agent": UPSTREAM_HEADERS["User-Agent"],
                                               "headers": "Accept-Encoding: gzip\r\n"},
                             timeout=UPSTREAM_TIMEOUT)
        except (OSError, av.FFmpegError):
            self.send_error(502)
            return
        with source:
            selected = _pick_live_streams(source, max_height, audio_only)
            if not selected:
                self.send_error(502)
                return
            selected_indexes = {s.index for s in selected}
            for stream in source.streams:
                if stream.index not in selected_indexes:
                    stream.discard = Discard.all

            self.send_response(200)
            self.send_header("Content-Type", "video/mp2t")
            self.end_headers()
            try:
                with av.open(self.wfile, mode="w", format="mpegts") as output:
                    outputs = {s.index: output.add_stream_from_template(s, opaque=True) for s in selected}
                    for packet in source.demux(*selected):
                        if packet.dts is None:
                            continue
                        packet.stream = outputs[packet.stream.index]
                        output.mux(packet)
            except (OSError, av.FFmpegError):
                pass


class StreamRelay:
    def __init__(self):
        self._server = None
        self._lock = threading.Lock()

    def _ensure_started(self):
        with self._lock:
            if self._server is None:
                server = ThreadingHTTPServer(("127.0.0.1", 0), _RelayHandler)
                server.daemon_threads = True
                server.streams = {}
                server.live = {}
                threading.Thread(target=server.serve_forever, daemon=True).start()
                self._server = server
        return self._server

    def local_urls(self, *streams):
        server = self._ensure_started()
        port = server.server_address[1]
        entries = {}
        urls = []
        for stream in streams:
            if stream is None:
                urls.append(None)
                continue
            try:
                size = 0 if stream.is_sabr else stream.filesize or 0
            except Exception:
                size = 0
            if not size:
                urls.append(stream.url)
                continue
            token = secrets.token_hex(8)
            entries[token] = (stream.url, size, stream.mime_type)
            urls.append(f"http://127.0.0.1:{port}/{token}")
        server.streams = entries
        return urls

    def live_url(self, hls_url, max_height=None, audio_only=False):
        server = self._ensure_started()
        token = secrets.token_hex(8)
        server.live = {token: (hls_url, max_height, audio_only)}
        return f"http://127.0.0.1:{server.server_address[1]}/{token}"

    def close(self):
        with self._lock:
            server, self._server = self._server, None
        if server is not None:
            server.shutdown()
            server.server_close()
