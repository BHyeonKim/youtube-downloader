"""GUI 헤드리스 스모크 테스트 (offscreen Qt platform에서 실행).

실제 네트워크/다운로드 없이 위젯 로직만 검증한다:
- 조회 결과 테이블 채우기
- 체크박스 선택 -> 큐 추가
- 진행률/완료 시그널 처리 -> 큐 테이블 및 이력 갱신
"""
import os
import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.gui.main_window import MainWindow  # noqa: E402
from app.models import VideoInfo  # noqa: E402

HISTORY_PATH = os.path.join(os.path.dirname(__file__), ".tmp_smoke_history.json")


def main() -> None:
    if os.path.exists(HISTORY_PATH):
        os.remove(HISTORY_PATH)

    app = QApplication(sys.argv)
    win = MainWindow(history_path=HISTORY_PATH)

    # 1) 조회 결과 채우기 (fetch worker를 거치지 않고 직접 호출)
    fake_videos = [
        VideoInfo(id="v1", title="스모크 테스트 영상 1", url="https://youtu.be/v1", duration=125, uploader="테스트 채널"),
        VideoInfo(id="v2", title="스모크 테스트 영상 2", url="https://youtu.be/v2", duration=65, uploader="테스트 채널"),
    ]
    win._on_fetch_succeeded(fake_videos, "playlist")
    assert win.results_table.rowCount() == 2, "결과 테이블 행 수가 맞지 않음"
    assert win.results_table.item(0, 1).text() == "스모크 테스트 영상 1"
    assert win.results_table.item(0, 2).text() == "2:05"
    print("[OK] 조회 결과 테이블 채우기")

    # 2) 두 번째 항목 체크 해제 -> 선택된 영상은 1개만
    win.results_table.item(1, 0).setCheckState(Qt.Unchecked)
    selected = win._selected_videos()
    assert len(selected) == 1 and selected[0].id == "v1"
    print("[OK] 체크박스 선택 로직")

    # 3) 큐에 추가 (실제 다운로드는 실행하지 않고 행 추가 로직만 검증)
    from app.models import MediaFormat, Quality, QueueItem

    item = QueueItem(video=fake_videos[0], media_format=MediaFormat.VIDEO, quality=Quality.BEST, output_dir=win.output_dir)
    win._add_queue_row(item)
    assert win.queue_table.rowCount() == 1
    assert win.queue_table.item(0, 0).text() == "스모크 테스트 영상 1"
    print("[OK] 큐 테이블 행 추가")

    # 4) 진행률 시그널 처리
    win._on_download_progress(item.item_id, 42.5, "1.2 MB/s", 10)
    progress_bar = win.queue_table.cellWidget(0, 2)
    assert progress_bar.value() == 42
    assert win.queue_table.item(0, 3).text() == "1.2 MB/s"
    print("[OK] 진행률 갱신")

    # 5) 완료 시그널 처리 -> 상태 텍스트 및 이력 반영
    fake_output_path = os.path.join(win.output_dir, "스모크 테스트 영상 1.mp4")
    win._on_download_finished(item.item_id, True, fake_output_path)
    assert win.queue_table.item(0, 1).text() == "완료"
    assert win.history_table.rowCount() == 1
    assert win.history_table.item(0, 0).text() == "스모크 테스트 영상 1"
    print("[OK] 완료 처리 및 이력 반영")

    # 6) 실패 케이스
    item2 = QueueItem(video=fake_videos[1], output_dir=win.output_dir)
    win._add_queue_row(item2)
    win._on_download_finished(item2.item_id, False, "네트워크 오류")
    row2 = win.queue_rows[item2.item_id]
    assert win.queue_table.item(row2, 1).text() == "실패"
    print("[OK] 실패 처리")

    # 7) 이력 검색
    win.history_search_input.setText("영상 1")
    assert win.history_table.rowCount() == 1
    win.history_search_input.setText("")
    print("[OK] 이력 검색")

    print("\nALL GUI SMOKE CHECKS PASSED")


if __name__ == "__main__":
    main()
