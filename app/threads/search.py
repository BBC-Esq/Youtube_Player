from PySide6.QtCore import QThread, Signal


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
                results.append({
                    "title": video.title or "(no title)",
                    "author": video.author or "",
                    "length": video.length or 0,
                    "url": video.watch_url,
                    "views": video.views,
                    "thumbnail_url": video.thumbnail_url or "",
                    "channel_url": video.channel_url or "",
                })
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
                results.append({
                    "title": video.title or "(no title)",
                    "author": video.author or "",
                    "length": video.length or 0,
                    "url": video.watch_url,
                    "views": video.views,
                    "thumbnail_url": video.thumbnail_url or "",
                    "channel_url": video.channel_url or "",
                })
            self.finished.emit(results)
        except Exception as e:
            self.error.emit(str(e))
