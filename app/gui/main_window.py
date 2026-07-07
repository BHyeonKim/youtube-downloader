"""메인 GUI 윈도우.

URL 입력 -> 조회 -> 목록/옵션 선택 -> 다운로드 큐 -> 진행률 -> 이력 순서로
PRD의 사용자 흐름을 그대로 구현한다.
"""
from __future__ import annotations

import os
import subprocess
import sys

from PySide6.QtCore import Qt, QThreadPool
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.gui.workers import DownloadRunnable, FetchRunnable
from app.history import HistoryStore, make_entry
from app.models import DownloadStatus, MediaFormat, QueueItem, Quality, VideoInfo

DEFAULT_HISTORY_PATH = os.path.join(os.path.expanduser("~"), ".youtube_downloader", "history.json")
DEFAULT_OUTPUT_DIR = os.path.join(os.path.expanduser("~"), "Downloads", "YouTubeDownloader")

_QUALITY_LABELS = [
    ("최고 화질", Quality.BEST),
    ("2160p", Quality.Q2160P),
    ("1080p", Quality.Q1080P),
    ("720p", Quality.Q720P),
    ("480p", Quality.Q480P),
    ("최저 화질", Quality.WORST),
]

_FORMAT_LABELS = [
    ("영상 (mp4)", MediaFormat.VIDEO),
    ("오디오만 (mp3)", MediaFormat.AUDIO),
]


def format_duration(seconds: int | None) -> str:
    if seconds is None:
        return "-"
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h:d}:{m:02d}:{s:02d}"
    return f"{m:d}:{s:02d}"


def open_containing_folder(path: str) -> None:
    if not path:
        return
    if sys.platform.startswith("win"):
        if os.path.exists(path):
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
        else:
            os.startfile(os.path.dirname(path) or ".")  # noqa: S606
    else:
        subprocess.Popen(["xdg-open", os.path.dirname(path) or "."])


class MainWindow(QMainWindow):
    def __init__(self, history_path: str = DEFAULT_HISTORY_PATH):
        super().__init__()
        self.setWindowTitle("YouTube Downloader")
        self.resize(900, 650)

        self.history_store = HistoryStore(history_path)
        self.output_dir = DEFAULT_OUTPUT_DIR
        self.current_videos: list[VideoInfo] = []
        self.queue_items: dict[str, QueueItem] = {}
        self.queue_rows: dict[str, int] = {}
        self._runnables: list = []  # GC 방지를 위해 참조 유지

        self.thread_pool = QThreadPool.globalInstance()
        self.thread_pool.setMaxThreadCount(2)

        self._build_ui()
        self._refresh_history_table()

    # ------------------------------------------------------------------
    # UI 구성
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        central = QWidget()
        root_layout = QVBoxLayout(central)

        # URL 입력 영역
        url_row = QHBoxLayout()
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("유튜브 영상 / 재생목록 / 채널 URL을 입력하세요")
        self.fetch_button = QPushButton("조회")
        self.fetch_button.clicked.connect(self._on_fetch_clicked)
        url_row.addWidget(self.url_input)
        url_row.addWidget(self.fetch_button)
        root_layout.addLayout(url_row)

        self.tabs = QTabWidget()
        root_layout.addWidget(self.tabs)

        self.tabs.addTab(self._build_download_tab(), "다운로드")
        self.tabs.addTab(self._build_history_tab(), "이력")

        self.status_label = QLabel("대기 중")
        root_layout.addWidget(self.status_label)

        self.setCentralWidget(central)

    def _build_download_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        layout.addWidget(QLabel("조회 결과"))
        self.results_table = QTableWidget(0, 4)
        self.results_table.setHorizontalHeaderLabels(["선택", "제목", "길이", "업로더"])
        self.results_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.results_table.setSelectionMode(QAbstractItemView.NoSelection)
        layout.addWidget(self.results_table)

        options_row = QHBoxLayout()
        self.format_combo = QComboBox()
        for label, _ in _FORMAT_LABELS:
            self.format_combo.addItem(label)
        options_row.addWidget(QLabel("포맷"))
        options_row.addWidget(self.format_combo)

        self.quality_combo = QComboBox()
        for label, _ in _QUALITY_LABELS:
            self.quality_combo.addItem(label)
        options_row.addWidget(QLabel("화질"))
        options_row.addWidget(self.quality_combo)

        options_row.addWidget(QLabel("동시 다운로드"))
        self.concurrency_spin = QSpinBox()
        self.concurrency_spin.setRange(1, 5)
        self.concurrency_spin.setValue(2)
        self.concurrency_spin.valueChanged.connect(self.thread_pool.setMaxThreadCount)
        options_row.addWidget(self.concurrency_spin)

        self.output_dir_label = QLabel(self._short_path(self.output_dir))
        self.output_dir_button = QPushButton("저장 경로 선택")
        self.output_dir_button.clicked.connect(self._on_choose_output_dir)
        options_row.addWidget(self.output_dir_label)
        options_row.addWidget(self.output_dir_button)

        layout.addLayout(options_row)

        self.download_button = QPushButton("다운로드 시작")
        self.download_button.clicked.connect(self._on_download_clicked)
        layout.addWidget(self.download_button)

        layout.addWidget(QLabel("다운로드 큐"))
        self.queue_table = QTableWidget(0, 5)
        self.queue_table.setHorizontalHeaderLabels(["제목", "상태", "진행률", "속도", "남은시간"])
        self.queue_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        layout.addWidget(self.queue_table)

        return tab

    def _build_history_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        search_row = QHBoxLayout()
        self.history_search_input = QLineEdit()
        self.history_search_input.setPlaceholderText("제목으로 검색")
        self.history_search_input.textChanged.connect(self._refresh_history_table)
        search_row.addWidget(self.history_search_input)
        layout.addLayout(search_row)

        self.history_table = QTableWidget(0, 3)
        self.history_table.setHorizontalHeaderLabels(["제목", "상태", "완료 시각"])
        self.history_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.history_table.itemDoubleClicked.connect(self._on_history_row_activated)
        layout.addWidget(self.history_table)

        layout.addWidget(QLabel("행을 더블클릭하면 저장된 폴더를 엽니다."))
        return tab

    @staticmethod
    def _short_path(path: str) -> str:
        return path if len(path) <= 40 else "..." + path[-37:]

    # ------------------------------------------------------------------
    # 조회 (Fetch)
    # ------------------------------------------------------------------
    def _on_fetch_clicked(self) -> None:
        url = self.url_input.text().strip()
        if not url:
            QMessageBox.warning(self, "입력 필요", "URL을 입력해 주세요.")
            return

        self.fetch_button.setEnabled(False)
        self.status_label.setText("조회 중...")
        runnable = FetchRunnable(url)
        runnable.signals.succeeded.connect(self._on_fetch_succeeded)
        runnable.signals.failed.connect(self._on_fetch_failed)
        self._runnables.append(runnable)
        self.thread_pool.start(runnable)

    def _on_fetch_succeeded(self, videos: list[VideoInfo], url_type: str) -> None:
        self.fetch_button.setEnabled(True)
        self.current_videos = videos
        self.status_label.setText(f"조회 완료: {len(videos)}개 항목 ({url_type})")
        self._populate_results_table(videos)

    def _on_fetch_failed(self, message: str) -> None:
        self.fetch_button.setEnabled(True)
        self.status_label.setText("조회 실패")
        QMessageBox.critical(self, "조회 실패", message)

    def _populate_results_table(self, videos: list[VideoInfo]) -> None:
        self.results_table.setRowCount(len(videos))
        for row, video in enumerate(videos):
            check_item = QTableWidgetItem()
            check_item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            check_item.setCheckState(Qt.Checked)
            self.results_table.setItem(row, 0, check_item)
            self.results_table.setItem(row, 1, QTableWidgetItem(video.title))
            self.results_table.setItem(row, 2, QTableWidgetItem(format_duration(video.duration)))
            self.results_table.setItem(row, 3, QTableWidgetItem(video.uploader or "-"))

    # ------------------------------------------------------------------
    # 저장 경로
    # ------------------------------------------------------------------
    def _on_choose_output_dir(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, "저장 경로 선택", self.output_dir)
        if chosen:
            self.output_dir = chosen
            self.output_dir_label.setText(self._short_path(chosen))

    # ------------------------------------------------------------------
    # 다운로드
    # ------------------------------------------------------------------
    def _selected_videos(self) -> list[VideoInfo]:
        selected = []
        for row in range(self.results_table.rowCount()):
            check_item = self.results_table.item(row, 0)
            if check_item is not None and check_item.checkState() == Qt.Checked:
                selected.append(self.current_videos[row])
        return selected

    def _on_download_clicked(self) -> None:
        selected = self._selected_videos()
        if not selected:
            QMessageBox.warning(self, "선택 필요", "다운로드할 항목을 선택해 주세요.")
            return

        os.makedirs(self.output_dir, exist_ok=True)

        media_format = _FORMAT_LABELS[self.format_combo.currentIndex()][1]
        quality = _QUALITY_LABELS[self.quality_combo.currentIndex()][1]

        for video in selected:
            item = QueueItem(
                video=video,
                media_format=media_format,
                quality=quality,
                output_dir=self.output_dir,
            )
            self._add_queue_row(item)
            self._start_download(item)

    def _add_queue_row(self, item: QueueItem) -> None:
        row = self.queue_table.rowCount()
        self.queue_table.insertRow(row)
        self.queue_table.setItem(row, 0, QTableWidgetItem(item.video.title))
        self.queue_table.setItem(row, 1, QTableWidgetItem("대기 중"))

        progress_bar = QProgressBar()
        progress_bar.setRange(0, 100)
        progress_bar.setValue(0)
        self.queue_table.setCellWidget(row, 2, progress_bar)

        self.queue_table.setItem(row, 3, QTableWidgetItem("-"))
        self.queue_table.setItem(row, 4, QTableWidgetItem("-"))

        self.queue_items[item.item_id] = item
        self.queue_rows[item.item_id] = row

    def _start_download(self, item: QueueItem) -> None:
        runnable = DownloadRunnable(item)
        runnable.signals.progress.connect(self._on_download_progress)
        runnable.signals.finished.connect(self._on_download_finished)
        self._runnables.append(runnable)
        self.thread_pool.start(runnable)

    def _on_download_progress(self, item_id: str, progress: float, speed: str, eta) -> None:
        row = self.queue_rows.get(item_id)
        if row is None:
            return
        self.queue_table.item(row, 1).setText("다운로드 중")
        self.queue_table.cellWidget(row, 2).setValue(int(progress))
        self.queue_table.item(row, 3).setText(speed or "-")
        self.queue_table.item(row, 4).setText(f"{eta}s" if eta else "-")

    def _on_download_finished(self, item_id: str, success: bool, message: str) -> None:
        row = self.queue_rows.get(item_id)
        item = self.queue_items.get(item_id)
        if row is None or item is None:
            return

        if success:
            self.queue_table.item(row, 1).setText("완료")
            self.queue_table.cellWidget(row, 2).setValue(100)
            entry = make_entry(
                title=item.video.title,
                url=item.video.url,
                output_path=message,
                status=DownloadStatus.COMPLETED.value,
            )
            self.history_store.add(entry)
            self._refresh_history_table()
        else:
            self.queue_table.item(row, 1).setText("실패")
            self.queue_table.item(row, 1).setToolTip(message)

    # ------------------------------------------------------------------
    # 이력
    # ------------------------------------------------------------------
    def _refresh_history_table(self) -> None:
        keyword = self.history_search_input.text().strip() if hasattr(self, "history_search_input") else ""
        entries = self.history_store.search(keyword) if keyword else self.history_store.list_entries()
        entries = list(reversed(entries))  # 최신순

        self.history_table.setRowCount(len(entries))
        for row, entry in enumerate(entries):
            self.history_table.setItem(row, 0, QTableWidgetItem(entry.title))
            self.history_table.setItem(row, 1, QTableWidgetItem(entry.status))
            self.history_table.setItem(row, 2, QTableWidgetItem(entry.finished_at))
            self.history_table.item(row, 0).setData(Qt.UserRole, entry.output_path)

    def _on_history_row_activated(self, table_item: QTableWidgetItem) -> None:
        row = table_item.row()
        path_item = self.history_table.item(row, 0)
        path = path_item.data(Qt.UserRole) if path_item else None
        if path:
            open_containing_folder(path)
