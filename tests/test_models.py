"""app.models 단위 테스트."""
from app.models import DownloadStatus, MediaFormat, Quality, QueueItem, VideoInfo


def test_queue_item_defaults():
    video = VideoInfo(id="abc", title="제목", url="https://youtu.be/abc")
    item = QueueItem(video=video)

    assert item.media_format == MediaFormat.VIDEO
    assert item.quality == Quality.BEST
    assert item.status == DownloadStatus.QUEUED
    assert item.progress == 0.0
    assert item.item_id  # uuid가 자동 생성됨


def test_queue_item_ids_are_unique():
    video = VideoInfo(id="abc", title="제목", url="https://youtu.be/abc")
    item1 = QueueItem(video=video)
    item2 = QueueItem(video=video)
    assert item1.item_id != item2.item_id
