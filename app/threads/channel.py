from PySide6.QtCore import QThread, Signal


class ChannelThread(QThread):
    finished = Signal(str, list, int)
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
            results = []
            for video in ch.videos:
                if len(results) >= self.batch_size:
                    break
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
                results.append({
                    "title": title,
                    "author": name,
                    "length": length,
                    "url": video.watch_url,
                    "views": views,
                    "thumbnail_url": thumb,
                    "channel_url": self.channel_url,
                })
            self.finished.emit(name, results, total)
        except Exception as e:
            self.error.emit(str(e))


class ChannelBatchThread(QThread):
    finished = Signal(list)
    error = Signal(str)

    def __init__(self, channel_url, channel_name, skip, batch_size=30):
        super().__init__()
        self.channel_url = channel_url
        self.channel_name = channel_name
        self.skip = skip
        self.batch_size = batch_size

    def run(self):
        try:
            from pytubefix import Channel
            ch = Channel(self.channel_url)
            results = []
            count = 0
            for video in ch.videos:
                if count < self.skip:
                    count += 1
                    continue
                if len(results) >= self.batch_size:
                    break
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
                results.append({
                    "title": title,
                    "author": self.channel_name,
                    "length": length,
                    "url": video.watch_url,
                    "views": views,
                    "thumbnail_url": thumb,
                    "channel_url": self.channel_url,
                })
                count += 1
            self.finished.emit(results)
        except Exception as e:
            self.error.emit(str(e))
