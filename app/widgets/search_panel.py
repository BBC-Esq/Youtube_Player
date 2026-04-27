from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QComboBox, QScrollArea, QFrame, QSizePolicy, QCompleter, QApplication
)
from PySide6.QtCore import Qt, QTimer, Signal, QUrl, QByteArray, QSettings, QStringListModel
from PySide6.QtGui import QPixmap, QFont, QCursor
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply

from app.threads.search import SearchThread, NextPageThread


def _format_views(views):
    if views is None:
        return ""
    if views >= 1_000_000_000:
        return f"{views / 1_000_000_000:.1f}B views"
    if views >= 1_000_000:
        return f"{views / 1_000_000:.1f}M views"
    if views >= 1_000:
        return f"{views / 1_000:.1f}K views"
    return f"{views} views"


def _format_duration(seconds):
    if not seconds:
        return "0:00"
    mins, secs = divmod(seconds, 60)
    hours, mins = divmod(mins, 60)
    if hours:
        return f"{hours}:{mins:02d}:{secs:02d}"
    return f"{mins}:{secs:02d}"


class ResultCard(QFrame):
    clicked = Signal(dict)

    def __init__(self, data, parent=None):
        super().__init__(parent)
        self.data = data
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.setFixedHeight(100)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFrameShape(QFrame.StyledPanel)
        self.setFrameShadow(QFrame.Raised)
        self.setAutoFillBackground(True)
        self._selected = False
        self._default_palette = self.palette()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 12, 8)
        layout.setSpacing(12)

        thumb_container = QWidget()
        thumb_container.setFixedSize(148, 84)
        thumb_layout = QVBoxLayout(thumb_container)
        thumb_layout.setContentsMargins(0, 0, 0, 0)

        self.thumbnail = QLabel()
        self.thumbnail.setFixedSize(148, 84)
        self.thumbnail.setAlignment(Qt.AlignCenter)
        self.thumbnail.setStyleSheet("font-size: 10px;")
        self.thumbnail.setText("Loading...")
        thumb_layout.addWidget(self.thumbnail)

        self.duration_badge = QLabel(_format_duration(data.get("length", 0)))
        self.duration_badge.setStyleSheet(
            "background-color: rgba(0,0,0,180); color: white; font-size: 10px;"
            "font-weight: bold; padding: 1px 4px; border-radius: 3px;"
        )
        self.duration_badge.setFixedHeight(16)
        self.duration_badge.adjustSize()
        self.duration_badge.setParent(self.thumbnail)
        self.duration_badge.move(
            148 - self.duration_badge.width() - 4,
            84 - self.duration_badge.height() - 4
        )

        layout.addWidget(thumb_container)

        info = QVBoxLayout()
        info.setContentsMargins(0, 0, 0, 0)
        info.setSpacing(3)

        self.title_label = QLabel(data.get("title", ""))
        self.title_label.setFont(QFont("", 11, QFont.Bold))
        self.title_label.setWordWrap(True)
        self.title_label.setMaximumHeight(40)
        info.addWidget(self.title_label)

        author = data.get("author", "")
        if author:
            author_label = QLabel(author)
            author_label.setStyleSheet("font-size: 11px;")
            info.addWidget(author_label)

        meta_parts = []
        views_str = _format_views(data.get("views"))
        if views_str:
            meta_parts.append(views_str)
        dur_str = _format_duration(data.get("length", 0))
        if dur_str != "0:00":
            meta_parts.append(dur_str)
        if meta_parts:
            meta_label = QLabel(" · ".join(meta_parts))
            meta_label.setStyleSheet("font-size: 11px;")
            info.addWidget(meta_label)

        info.addStretch()
        layout.addLayout(info, stretch=1)

        self._overlay = QLabel("Copy URL", self.thumbnail)
        self._overlay.setAlignment(Qt.AlignCenter)
        self._overlay.setFixedSize(148, 84)
        self._overlay.move(0, 0)
        self._overlay.setStyleSheet(
            "background-color: rgba(0, 0, 0, 160); color: white;"
            "font-size: 12px; font-weight: bold;"
        )
        self._overlay.setCursor(QCursor(Qt.PointingHandCursor))
        self._overlay.installEventFilter(self)
        self._overlay.hide()

    def set_thumbnail(self, pixmap):
        scaled = pixmap.scaled(148, 84, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        if scaled.width() > 148 or scaled.height() > 84:
            x = (scaled.width() - 148) // 2
            y = (scaled.height() - 84) // 2
            scaled = scaled.copy(x, y, 148, 84)
        self.thumbnail.setPixmap(scaled)

    def set_selected(self, selected):
        self._selected = selected
        if selected:
            self.setFrameShadow(QFrame.Sunken)
            self.setLineWidth(2)
        else:
            self.setFrameShadow(QFrame.Raised)
            self.setLineWidth(1)
        self._apply_background()

    def _apply_background(self):
        pal = self.palette()
        if self._selected:
            pal.setColor(pal.ColorRole.Window, pal.color(pal.ColorRole.Highlight).lighter(160))
        else:
            pal = self._default_palette
        self.setPalette(pal)

    def eventFilter(self, obj, event):
        if obj is self._overlay and event.type() == event.Type.MouseButtonPress:
            if event.button() == Qt.LeftButton:
                url = self.data.get("url", "")
                if url:
                    QApplication.clipboard().setText(url)
                    self._overlay.setText("Copied!")
                    QTimer.singleShot(800, lambda: self._overlay.setText("Copy URL"))
                return True
        return super().eventFilter(obj, event)

    def enterEvent(self, event):
        if not self._selected:
            pal = self.palette()
            pal.setColor(pal.ColorRole.Window, pal.color(pal.ColorRole.Midlight))
            self.setPalette(pal)
        self._overlay.show()
        self._overlay.raise_()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._overlay.hide()
        self._apply_background()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.data)
        super().mousePressEvent(event)


class SearchPanel(QWidget):
    url_selected = Signal(str)
    thread_created = Signal(object)

    def __init__(self, settings: QSettings, parent=None):
        super().__init__(parent)
        self._threads = []
        self._search_obj = None
        self._cards = []
        self._selected_card = None
        self._net = QNetworkAccessManager(self)
        self._net.finished.connect(self._on_thumbnail_reply)
        self._thumb_map = {}
        self._settings = settings
        self._search_history = self._settings.value("search_history", []) or []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        search_row = QHBoxLayout()
        search_row.setSpacing(6)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search YouTube...")
        self.search_input.returnPressed.connect(self.do_search)
        self.search_input.setMinimumHeight(32)

        self._history_model = QStringListModel(self._search_history, self)
        self._completer = QCompleter(self._history_model, self)
        self._completer.setCaseSensitivity(Qt.CaseInsensitive)
        self._completer.setFilterMode(Qt.MatchContains)
        self._completer.setCompletionMode(QCompleter.UnfilteredPopupCompletion)
        self.search_input.setCompleter(self._completer)

        search_row.addWidget(self.search_input)

        self.search_button = QPushButton("Search")
        self.search_button.setFixedHeight(32)
        self.search_button.setFixedWidth(90)
        self.search_button.clicked.connect(self.do_search)
        search_row.addWidget(self.search_button)
        layout.addLayout(search_row)

        filter_row = QHBoxLayout()
        filter_row.setSpacing(6)
        filter_row.addWidget(QLabel("Sort:"))
        self.sort_combo = QComboBox()
        self.sort_combo.addItems(["Relevance", "Upload Date", "View Count", "Rating"])
        filter_row.addWidget(self.sort_combo)
        filter_row.addWidget(QLabel("Date:"))
        self.date_combo = QComboBox()
        self.date_combo.addItems(["Any", "Last Hour", "Today", "This Week", "This Month", "This Year"])
        filter_row.addWidget(self.date_combo)
        filter_row.addWidget(QLabel("Duration:"))
        self.duration_combo = QComboBox()
        self.duration_combo.addItems(["Any", "Under 4 min", "4-20 min", "Over 20 min"])
        filter_row.addWidget(self.duration_combo)
        filter_row.addWidget(QLabel("Quality:"))
        self.quality_combo = QComboBox()
        self.quality_combo.addItems(["Any", "HD", "4K"])
        filter_row.addWidget(self.quality_combo)
        filter_row.addStretch()
        layout.addLayout(filter_row)

        self.suggestions_label = QLabel()
        self.suggestions_label.setWordWrap(True)
        self.suggestions_label.setStyleSheet("font-size: 11px;")
        self.suggestions_label.setVisible(False)
        layout.addWidget(self.suggestions_label)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.results_container = QWidget()
        self.results_layout = QVBoxLayout(self.results_container)
        self.results_layout.setContentsMargins(0, 0, 0, 0)
        self.results_layout.setSpacing(4)
        self.results_layout.addStretch()
        self.scroll.setWidget(self.results_container)
        layout.addWidget(self.scroll, stretch=1)

        bottom_row = QHBoxLayout()
        self.load_more_button = QPushButton("Load More")
        self.load_more_button.setEnabled(False)
        self.load_more_button.setFixedWidth(140)
        self.load_more_button.clicked.connect(self.load_more)
        bottom_row.addStretch()
        bottom_row.addWidget(self.load_more_button)
        bottom_row.addStretch()
        layout.addLayout(bottom_row)

        self.status_label = QLabel("Enter a search query.")
        self.status_label.setStyleSheet("font-size: 11px;")
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label)

    def _build_filters(self):
        from pytubefix.contrib.search import Filter

        sort_map = {
            "Relevance": Filter.SortBy.RELEVANCE,
            "Upload Date": Filter.SortBy.UPLOAD_DATE,
            "View Count": Filter.SortBy.VIEW_COUNT,
            "Rating": Filter.SortBy.RATING,
        }
        date_map = {
            "Last Hour": Filter.UploadDate.LAST_HOUR,
            "Today": Filter.UploadDate.TODAY,
            "This Week": Filter.UploadDate.THIS_WEEK,
            "This Month": Filter.UploadDate.THIS_MONTH,
            "This Year": Filter.UploadDate.THIS_YEAR,
        }
        duration_map = {
            "Under 4 min": Filter.Duration.UNDER_4_MINUTES,
            "4-20 min": Filter.Duration.BETWEEN_4_20_MINUTES,
            "Over 20 min": Filter.Duration.OVER_20_MINUTES,
        }
        quality_map = {
            "HD": Filter.Features.HD,
            "4K": Filter.Features._4K,
        }

        sort_text = self.sort_combo.currentText()
        date_text = self.date_combo.currentText()
        duration_text = self.duration_combo.currentText()
        quality_text = self.quality_combo.currentText()

        has_filter = (
            sort_text != "Relevance"
            or date_text != "Any"
            or duration_text != "Any"
            or quality_text != "Any"
        )
        if not has_filter:
            return None

        f = Filter.create().type(Filter.Type.VIDEO)
        if sort_text in sort_map:
            f = f.sort_by(sort_map[sort_text])
        if date_text in date_map:
            f = f.upload_date(date_map[date_text])
        if duration_text in duration_map:
            f = f.duration(duration_map[duration_text])
        if quality_text in quality_map:
            f = f.feature([quality_map[quality_text]])
        return f

    def _clear_results(self):
        for card in self._cards:
            card.setParent(None)
            card.deleteLater()
        self._cards = []
        self._selected_card = None
        self._thumb_map = {}

    def do_search(self):
        self._completer.popup().hide()
        query = self.search_input.text().strip()
        if not query:
            return

        self._clear_results()
        self.suggestions_label.setVisible(False)
        self.search_button.setEnabled(False)
        self.load_more_button.setEnabled(False)
        self.status_label.setText(f"Searching for \"{query}\"...")
        self._search_obj = None

        if query in self._search_history:
            self._search_history.remove(query)
        self._search_history.insert(0, query)
        self._search_history = self._search_history[:6]
        self._history_model.setStringList(self._search_history)
        self._settings.setValue("search_history", self._search_history)

        filters = self._build_filters()
        thread = SearchThread(query, filters=filters)
        thread.finished.connect(self._on_search_finished)
        thread.suggestions_ready.connect(self._on_suggestions)
        thread.error.connect(self._on_search_error)
        thread.start()
        self._threads.append(thread)
        self.thread_created.emit(thread)

        self._keep_search_obj(query, filters)

    def _keep_search_obj(self, query, filters):
        from pytubefix import Search
        self._search_obj = Search(query, filters=filters)

    def _add_result_cards(self, results):
        for r in results:
            card = ResultCard(r)
            card.clicked.connect(self._on_card_clicked)
            insert_pos = self.results_layout.count() - 1
            self.results_layout.insertWidget(insert_pos, card)
            self._cards.append(card)
            thumb_url = r.get("thumbnail_url", "")
            if thumb_url:
                reply = self._net.get(QNetworkRequest(QUrl(thumb_url)))
                self._thumb_map[reply] = card

    def _on_thumbnail_reply(self, reply: QNetworkReply):
        card = self._thumb_map.pop(reply, None)
        if card is not None and reply.error() == QNetworkReply.NoError:
            data = reply.readAll()
            pixmap = QPixmap()
            pixmap.loadFromData(QByteArray(data))
            if not pixmap.isNull():
                card.set_thumbnail(pixmap)
        reply.deleteLater()

    def _on_card_clicked(self, data):
        for card in self._cards:
            card.set_selected(card.data is data)
        self._selected_card = data
        url = data.get("url", "")
        if url:
            self.url_selected.emit(url)
            self.status_label.setText(f"Loaded: {data.get('title', '')}")

    def _on_search_finished(self, results):
        self.search_button.setEnabled(True)
        self._add_result_cards(results)
        count = len(results)
        self.status_label.setText(
            f"Found {count} result{'s' if count != 1 else ''}. Click a result to load it."
        )
        self.load_more_button.setEnabled(True)

    def _on_suggestions(self, suggestions):
        if suggestions:
            self.suggestions_label.setText("Related: " + " · ".join(suggestions))
            self.suggestions_label.setVisible(True)
        else:
            self.suggestions_label.setVisible(False)

    def _on_search_error(self, msg):
        self.search_button.setEnabled(True)
        self.status_label.setText(f"Search error: {msg}")

    def load_more(self):
        if self._search_obj is None:
            return
        self.load_more_button.setEnabled(False)
        self.status_label.setText("Loading more results...")
        thread = NextPageThread(self._search_obj)
        thread.finished.connect(self._on_more_results)
        thread.error.connect(self._on_search_error)
        thread.start()
        self._threads.append(thread)
        self.thread_created.emit(thread)

    def _on_more_results(self, results):
        self._clear_results()
        self._add_result_cards(results)
        count = len(self._cards)
        self.status_label.setText(
            f"Showing {count} results. Click a result to load it."
        )
        self.load_more_button.setEnabled(True)
