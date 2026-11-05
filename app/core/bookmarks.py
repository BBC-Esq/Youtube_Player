import json

from pytubefix.exceptions import RegexMatchError
from pytubefix.extract import video_id

from app.constants import CHANNEL_LIVE_LINK


def _watch_url(url):
    if CHANNEL_LIVE_LINK.search(url):
        return url
    try:
        return f"https://www.youtube.com/watch?v={video_id(url)}"
    except RegexMatchError:
        return url


class Bookmarks:
    def __init__(self, settings):
        self._settings = settings
        try:
            self._items = json.loads(settings.value("bookmarks", "") or "[]")
        except ValueError:
            self._items = []

    def items(self):
        return list(self._items)

    def add(self, url, title):
        url = _watch_url(url)
        if any(item["url"] == url for item in self._items):
            return False
        self._items.append({"url": url, "title": title or url})
        self._save()
        return True

    def remove(self, url):
        self._items = [item for item in self._items if item["url"] != url]
        self._save()

    def _save(self):
        self._settings.setValue("bookmarks", json.dumps(self._items))
