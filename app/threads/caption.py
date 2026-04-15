from PySide6.QtCore import QThread, Signal

from pytubefix import YouTube


class CaptionDownloadThread(QThread):
    completed = Signal(str)
    error = Signal(str)

    def __init__(self, url, caption_code, out_filename, fmt="srt", use_oauth=False,
                 oauth_verifier=None):
        super().__init__()
        self.url = url
        self.caption_code = caption_code
        self.out_filename = out_filename
        self.fmt = fmt.lower()
        self.use_oauth = use_oauth
        self.oauth_verifier = oauth_verifier
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            yt_kwargs = {"use_oauth": self.use_oauth}
            if self.use_oauth:
                yt_kwargs["allow_oauth_cache"] = True
                if self.oauth_verifier is not None:
                    yt_kwargs["oauth_verifier"] = self.oauth_verifier
            yt = YouTube(self.url, **yt_kwargs)
            if self.caption_code not in [c.code for c in yt.captions]:
                raise ValueError(f"Caption track '{self.caption_code}' not found for this video.")
            caption = yt.captions[self.caption_code]
            if self.fmt == "srt":
                content = caption.generate_srt_captions()
                with open(self.out_filename, "w", encoding="utf-8") as f:
                    f.write(content)
            elif self.fmt == "txt":
                caption.save_captions(self.out_filename)
            else:
                raise ValueError("Unsupported caption format (choose SRT or TXT).")
            if self._cancelled:
                return
            self.completed.emit(self.out_filename)
        except Exception as e:
            if not self._cancelled:
                self.error.emit(str(e))
