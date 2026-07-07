"""QThreadPool 기반 백그라운드 작업(조회/다운로드) 정의.

UI 스레드를 막지 않기 위해 네트워크 조회와 다운로드를 모두
QRunnable로 감싸고, Qt 시그널로 결과를 메인 스레드에 전달한다.
"""
from __future__ import annotations

from PySide6.QtCore import QObject, QRunnable, Signal

from app.downloader import DownloadError, classify_url, download_item, fetch_playlist_entries, fetch_video_info
from app.models import QueueItem, URLType


class FetchSignals(QObject):
    succeeded = Signal(object, str)  # list[VideoInfo], url_type.value
    failed = Signal(str)


class FetchRunnable(QRunnable):
    """URL을 분류하고 메타데이터(단일 영상 또는 목록)를 조회한다."""

    def __init__(self, url: str):
        super().__init__()
        self.url = url
        self.signals = FetchSignals()

    def run(self) -> None:
        url_type = classify_url(self.url)
        try:
            if url_type == URLType.SINGLE:
                videos = [fetch_video_info(self.url)]
            elif url_type in (URLType.PLAYLIST, URLType.CHANNEL):
                videos = fetch_playlist_entries(self.url)
            else:
                self.signals.failed.emit(
                    "지원하지 않는 URL 형식입니다. 유튜브 영상/재생목록/채널 URL을 입력해 주세요."
                )
                return
            self.signals.succeeded.emit(videos, url_type.value)
        except Exception as exc:  # yt-dlp가 던지는 다양한 예외를 사용자 메시지로 변환
            self.signals.failed.emit(str(exc))


class DownloadSignals(QObject):
    progress = Signal(str, float, str, object)  # item_id, progress(%), speed, eta
    finished = Signal(str, bool, str)  # item_id, success, output_path_or_error


class DownloadRunnable(QRunnable):
    """QueueItem 하나를 다운로드하는 작업 단위."""

    def __init__(self, item: QueueItem):
        super().__init__()
        self.item = item
        self.signals = DownloadSignals()

    def run(self) -> None:
        def on_progress(item: QueueItem) -> None:
            self.signals.progress.emit(item.item_id, item.progress, item.speed or "", item.eta)

        try:
            download_item(self.item, progress_callback=on_progress)
            self.signals.finished.emit(self.item.item_id, True, self.item.output_path or "")
        except DownloadError as exc:
            self.signals.finished.emit(self.item.item_id, False, str(exc))
