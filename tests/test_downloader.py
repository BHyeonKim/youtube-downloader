"""app.downloader 단위 테스트. 네트워크 호출은 모두 모킹한다."""
from unittest.mock import MagicMock, patch

import pytest

from app.downloader import (
    DownloadError,
    build_format_string,
    build_ydl_opts,
    classify_url,
    download_item,
    fetch_playlist_entries,
    fetch_video_info,
    is_supported_url,
)
from app.models import DownloadStatus, MediaFormat, Quality, QueueItem, URLType, VideoInfo


# ---------------------------------------------------------------------------
# is_supported_url / classify_url
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://www.youtube.com/watch?v=abc123", True),
        ("https://youtu.be/abc123", True),
        ("https://music.youtube.com/watch?v=abc123", True),
        ("https://vimeo.com/12345", False),
        ("not-a-url", False),
    ],
)
def test_is_supported_url(url, expected):
    assert is_supported_url(url) is expected


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://www.youtube.com/watch?v=abc123", URLType.SINGLE),
        ("https://youtu.be/abc123", URLType.SINGLE),
        ("https://www.youtube.com/playlist?list=PLxyz", URLType.PLAYLIST),
        ("https://www.youtube.com/channel/UCxyz", URLType.CHANNEL),
        ("https://www.youtube.com/@somechannel", URLType.CHANNEL),
        ("https://www.youtube.com/@somechannel/videos", URLType.CHANNEL),
        ("https://www.youtube.com/c/somechannel", URLType.CHANNEL),
        ("https://www.youtube.com/user/somechannel", URLType.CHANNEL),
        ("https://www.youtube.com/", URLType.UNKNOWN),
        ("https://vimeo.com/12345", URLType.UNKNOWN),
    ],
)
def test_classify_url(url, expected):
    assert classify_url(url) == expected


# ---------------------------------------------------------------------------
# build_format_string / build_ydl_opts
# ---------------------------------------------------------------------------

def test_build_format_string_audio():
    assert build_format_string(MediaFormat.AUDIO, Quality.BEST) == "bestaudio/best"


def test_build_format_string_video_best():
    assert build_format_string(MediaFormat.VIDEO, Quality.BEST) == "bestvideo+bestaudio/best"


def test_build_format_string_video_height_capped():
    result = build_format_string(MediaFormat.VIDEO, Quality.Q720P)
    assert "height<=720" in result


def test_build_ydl_opts_audio_has_mp3_postprocessor():
    item = QueueItem(
        video=VideoInfo(id="abc", title="t", url="https://youtu.be/abc"),
        media_format=MediaFormat.AUDIO,
        quality=Quality.BEST,
        output_dir="out",
    )
    opts = build_ydl_opts(item)
    assert opts["postprocessors"][0]["preferredcodec"] == "mp3"
    assert "ffmpeg_location" in opts


def test_build_ydl_opts_video_has_merge_format():
    item = QueueItem(
        video=VideoInfo(id="abc", title="t", url="https://youtu.be/abc"),
        media_format=MediaFormat.VIDEO,
        quality=Quality.Q1080P,
        output_dir="out",
    )
    opts = build_ydl_opts(item)
    assert opts["merge_output_format"] == "mp4"


# ---------------------------------------------------------------------------
# fetch_video_info / fetch_playlist_entries (yt_dlp.YoutubeDL 모킹)
# ---------------------------------------------------------------------------

def _fake_ydl(info_return):
    fake = MagicMock()
    fake.__enter__.return_value = fake
    fake.__exit__.return_value = False
    fake.extract_info.return_value = info_return
    return fake


def test_fetch_video_info_maps_fields():
    fake_info = {
        "id": "abc123",
        "title": "테스트 영상",
        "webpage_url": "https://www.youtube.com/watch?v=abc123",
        "duration": 120,
        "uploader": "테스트 채널",
        "thumbnail": "https://example.com/thumb.jpg",
    }
    with patch("app.downloader.yt_dlp.YoutubeDL", return_value=_fake_ydl(fake_info)):
        video = fetch_video_info("https://www.youtube.com/watch?v=abc123")

    assert video.id == "abc123"
    assert video.title == "테스트 영상"
    assert video.duration == 120
    assert video.uploader == "테스트 채널"


def test_fetch_video_info_raises_on_none():
    with patch("app.downloader.yt_dlp.YoutubeDL", return_value=_fake_ydl(None)):
        with pytest.raises(DownloadError):
            fetch_video_info("https://www.youtube.com/watch?v=missing")


def test_fetch_playlist_entries_filters_none_and_maps():
    fake_info = {
        "entries": [
            {"id": "v1", "title": "영상1", "url": "https://www.youtube.com/watch?v=v1"},
            None,
            {"id": "v2", "title": "영상2", "url": "https://www.youtube.com/watch?v=v2"},
        ]
    }
    with patch("app.downloader.yt_dlp.YoutubeDL", return_value=_fake_ydl(fake_info)):
        videos = fetch_playlist_entries("https://www.youtube.com/playlist?list=PLxyz")

    assert len(videos) == 2
    assert [v.id for v in videos] == ["v1", "v2"]


# ---------------------------------------------------------------------------
# download_item
# ---------------------------------------------------------------------------

def test_download_item_success_updates_status():
    item = QueueItem(
        video=VideoInfo(id="abc", title="t", url="https://youtu.be/abc"),
        output_dir="out",
    )

    def fake_ydl_ctor(opts):
        fake = MagicMock()
        fake.__enter__.return_value = fake
        fake.__exit__.return_value = False

        def fake_extract_info(url, download=True):
            opts["progress_hooks"][0]({"status": "downloading", "downloaded_bytes": 50, "total_bytes": 100})
            opts["progress_hooks"][0]({"status": "finished", "filename": "out/t.f137.mp4"})
            return {"requested_downloads": [{"filepath": "out/t.mp4"}]}

        fake.extract_info.side_effect = fake_extract_info
        return fake

    with patch("app.downloader.yt_dlp.YoutubeDL", side_effect=fake_ydl_ctor):
        download_item(item)

    assert item.status == DownloadStatus.COMPLETED
    assert item.progress == 100.0
    assert item.output_path == "out/t.mp4"


def test_download_item_failure_sets_failed_status():
    item = QueueItem(
        video=VideoInfo(id="abc", title="t", url="https://youtu.be/abc"),
        output_dir="out",
    )

    fake = MagicMock()
    fake.__enter__.return_value = fake
    fake.__exit__.return_value = False
    fake.extract_info.side_effect = RuntimeError("network error")

    with patch("app.downloader.yt_dlp.YoutubeDL", return_value=fake):
        with pytest.raises(DownloadError):
            download_item(item)

    assert item.status == DownloadStatus.FAILED
    assert "network error" in item.error_message


def test_download_item_calls_progress_callback():
    item = QueueItem(
        video=VideoInfo(id="abc", title="t", url="https://youtu.be/abc"),
        output_dir="out",
    )
    seen_statuses = []

    def fake_ydl_ctor(opts):
        fake = MagicMock()
        fake.__enter__.return_value = fake
        fake.__exit__.return_value = False

        def fake_extract_info(url, download=True):
            opts["progress_hooks"][0]({"status": "downloading", "downloaded_bytes": 10, "total_bytes": 100})
            return {"requested_downloads": [{"filepath": "out/t.mp4"}]}

        fake.extract_info.side_effect = fake_extract_info
        return fake

    with patch("app.downloader.yt_dlp.YoutubeDL", side_effect=fake_ydl_ctor):
        download_item(item, progress_callback=lambda i: seen_statuses.append(i.status))

    assert DownloadStatus.DOWNLOADING in seen_statuses
    assert seen_statuses[-1] == DownloadStatus.COMPLETED
