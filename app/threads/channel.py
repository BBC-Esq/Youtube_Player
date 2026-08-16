from itertools import islice

from PySide6.QtCore import QThread, Signal

UNREADABLE_CHANNEL_MESSAGE = (
    "Could not read this channel's video list. The installed pytubefix version "
    "cannot parse YouTube's current channel pages."
)


def _extract_channel_video(video, author, channel_url):
    try:
        url = video.watch_url
    except Exception:
        return None
    try:
        title = video.title or "(no title)"
    except Exception:
        title = "(no title)"
    try:
        length = video.length or 0
    except Exception:
        length = 0
    try:
        views = video.views
    except Exception:
        views = None
    try:
        thumb = video.thumbnail_url or ""
    except Exception:
        thumb = ""
    return {
        "title": title,
        "author": author,
        "length": length,
        "url": url,
        "views": views,
        "thumbnail_url": thumb,
        "channel_url": channel_url,
    }


class ChannelThread(QThread):
    finished = Signal(str, list, int, object)
    error = Signal(str)

    def __init__(self, channel_url, batch_size=30):
        super().__init__()
        self.channel_url = channel_url
        self.batch_size = batch_size

    def run(self):
        try:
            from pytubefix import Channel
            ch = Channel(self.channel_url)
            name = ch.channel_name or ""
            total = len(list(ch.video_urls))
            videos = ch.videos
            results = []
            seen = 0
            for video in islice(iter(videos), self.batch_size):
                seen += 1
                data = _extract_channel_video(video, name, self.channel_url)
                if data:
                    results.append(data)
            if seen and not results:
                self.error.emit(UNREADABLE_CHANNEL_MESSAGE)
                return
            self.finished.emit(name, results, total, videos)
        except Exception as e:
            self.error.emit(str(e))


class ChannelBatchThread(QThread):
    finished = Signal(list)
    error = Signal(str)

    def __init__(self, videos, channel_name, channel_url, skip, batch_size=30):
        super().__init__()
        self.videos = videos
        self.channel_name = channel_name
        self.channel_url = channel_url
        self.skip = skip
        self.batch_size = batch_size

    def run(self):
        try:
            results = []
            seen = 0
            batch = islice(iter(self.videos), self.skip, self.skip + self.batch_size)
            for video in batch:
                seen += 1
                data = _extract_channel_video(video, self.channel_name, self.channel_url)
                if data:
                    results.append(data)
            if seen and not results:
                self.error.emit(UNREADABLE_CHANNEL_MESSAGE)
                return
            self.finished.emit(results)
        except Exception as e:
            self.error.emit(str(e))
