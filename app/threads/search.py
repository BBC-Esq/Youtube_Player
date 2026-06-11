from PySide6.QtCore import QThread, Signal


def _extract_video_data(video):
    try:
        url = video.watch_url
    except Exception:
        return None
    try:
        title = video.title or "(no title)"
    except Exception:
        title = "(no title)"
    try:
        author = video.author or ""
    except Exception:
        author = ""
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
    try:
        channel_url = video.channel_url or ""
    except Exception:
        channel_url = ""
    return {
        "title": title,
        "author": author,
        "length": length,
        "url": url,
        "views": views,
        "thumbnail_url": thumb,
        "channel_url": channel_url,
    }


class SearchThread(QThread):
    finished = Signal(list)
    suggestions_ready = Signal(list)
    error = Signal(str)

    def __init__(self, query, filters=None):
        super().__init__()
        self.query = query
        self.filters = filters

    def run(self):
        try:
            from pytubefix import Search
            s = Search(self.query, filters=self.filters)
            results = []
            for video in s.videos:
                data = _extract_video_data(video)
                if data:
                    results.append(data)
            suggestions = []
            try:
                suggestions = s.completion_suggestions or []
            except Exception:
                pass
            self.suggestions_ready.emit(suggestions)
            self.finished.emit(results)
        except Exception as e:
            self.error.emit(str(e))


class NextPageThread(QThread):
    finished = Signal(list)
    error = Signal(str)

    def __init__(self, search_obj):
        super().__init__()
        self.search_obj = search_obj

    def run(self):
        try:
            self.search_obj.get_next_results()
            results = []
            for video in self.search_obj.videos:
                data = _extract_video_data(video)
                if data:
                    results.append(data)
            self.finished.emit(results)
        except Exception as e:
            self.error.emit(str(e))
