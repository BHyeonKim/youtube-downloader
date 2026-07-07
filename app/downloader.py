"""yt-dlp를 감싸는 핵심 다운로드 로직.

GUI에 의존하지 않는 순수 로직으로 분리해 단위 테스트가 가능하도록 구성한다.
네트워크 호출은 모두 ``yt_dlp.YoutubeDL`` 을 통해서만 이뤄지므로,
테스트에서는 ``app.downloader.yt_dlp.YoutubeDL`` 을 모킹해 검증한다.
"""
from __future__ import annotations

import os
from urllib.parse import parse_qs, urlparse

import imageio_ffmpeg
import yt_dlp

from app.models import DownloadStatus, MediaFormat, Quality, QueueItem, URLType, VideoInfo

_QUALITY_HEIGHT = {
    Quality.Q2160P: 2160,
    Quality.Q1080P: 1080,
    Quality.Q720P: 720,
    Quality.Q480P: 480,
}

_YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
}


class DownloadError(Exception):
    """다운로드 실패 시 발생하는 예외."""


def is_supported_url(url: str) -> bool:
    """유튜브 도메인인지 여부만 확인한다 (형식 유효성 검사)."""
    try:
        host = urlparse(url).netloc.lower()
    except ValueError:
        return False
    return any(host == h or host.endswith("." + h) for h in _YOUTUBE_HOSTS)


def classify_url(url: str) -> URLType:
    """URL을 단일 영상 / 재생목록 / 채널 / 알 수 없음으로 분류한다."""
    if not is_supported_url(url):
        return URLType.UNKNOWN

    parsed = urlparse(url)
    path = parsed.path or "/"
    query = parse_qs(parsed.query)

    if parsed.netloc.lower() == "youtu.be":
        return URLType.SINGLE if len(path.strip("/")) > 0 else URLType.UNKNOWN

    if path == "/playlist" and "list" in query:
        return URLType.PLAYLIST

    if path == "/watch" and "v" in query:
        return URLType.SINGLE

    if (
        path.startswith("/channel/")
        or path.startswith("/c/")
        or path.startswith("/user/")
        or path.startswith("/@")
    ):
        return URLType.CHANNEL

    return URLType.UNKNOWN


def get_ffmpeg_location() -> str:
    """imageio-ffmpeg가 번들로 제공하는 ffmpeg 실행 파일 경로를 반환한다."""
    return imageio_ffmpeg.get_ffmpeg_exe()


def build_format_string(media_format: MediaFormat, quality: Quality) -> str:
    """yt-dlp의 -f 포맷 선택 문자열을 구성한다."""
    if media_format == MediaFormat.AUDIO:
        return "bestaudio/best"

    if quality == Quality.BEST:
        return "bestvideo+bestaudio/best"
    if quality == Quality.WORST:
        return "worstvideo+worstaudio/worst"

    height = _QUALITY_HEIGHT[quality]
    return f"bestvideo[height<={height}]+bestaudio/best[height<={height}]"


def build_ydl_opts(item: QueueItem, progress_hook=None) -> dict:
    """QueueItem 설정을 기반으로 yt-dlp 옵션 딕셔너리를 구성한다."""
    opts: dict = {
        "format": build_format_string(item.media_format, item.quality),
        "outtmpl": os.path.join(item.output_dir, "%(title)s.%(ext)s"),
        "ffmpeg_location": get_ffmpeg_location(),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "restrictfilenames": False,
    }

    if item.media_format == MediaFormat.AUDIO:
        opts["postprocessors"] = [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ]
    else:
        opts["merge_output_format"] = "mp4"

    if progress_hook is not None:
        opts["progress_hooks"] = [progress_hook]

    return opts


def _info_to_video(info: dict) -> VideoInfo:
    video_id = info.get("id") or ""
    url = info.get("webpage_url") or info.get("url") or f"https://www.youtube.com/watch?v={video_id}"
    return VideoInfo(
        id=video_id,
        title=info.get("title") or "(제목 없음)",
        url=url,
        duration=info.get("duration"),
        uploader=info.get("uploader") or info.get("channel"),
        thumbnail_url=info.get("thumbnail"),
    )


def fetch_video_info(url: str) -> VideoInfo:
    """단일 영상의 메타데이터를 조회한다."""
    opts = {"quiet": True, "no_warnings": True, "skip_download": True, "noplaylist": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    if info is None:
        raise DownloadError("영상 정보를 가져오지 못했습니다.")
    return _info_to_video(info)


def fetch_playlist_entries(url: str) -> list[VideoInfo]:
    """재생목록 또는 채널 URL에서 포함된 영상 목록을 (가볍게) 조회한다."""
    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": "in_playlist",
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    if info is None:
        raise DownloadError("목록 정보를 가져오지 못했습니다.")

    entries = info.get("entries") or []
    return [_info_to_video(entry) for entry in entries if entry]


def _format_speed(speed_bytes_per_sec: float | None) -> str | None:
    if not speed_bytes_per_sec:
        return None
    mb = speed_bytes_per_sec / (1024 * 1024)
    if mb >= 1:
        return f"{mb:.1f} MB/s"
    kb = speed_bytes_per_sec / 1024
    return f"{kb:.1f} KB/s"


def download_item(item: QueueItem, progress_callback=None) -> None:
    """QueueItem 하나를 실제로 다운로드하고 item의 상태/진행률을 갱신한다.

    실패 시 ``item.status`` 를 FAILED로 설정하고 ``DownloadError`` 를 raise한다.
    """

    def hook(d: dict) -> None:
        status = d.get("status")
        if status == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            downloaded = d.get("downloaded_bytes", 0)
            item.progress = (downloaded / total * 100) if total else item.progress
            item.speed = _format_speed(d.get("speed"))
            item.eta = d.get("eta")
            item.status = DownloadStatus.DOWNLOADING
        elif status == "finished":
            item.progress = 100.0
        if progress_callback:
            progress_callback(item)

    item.status = DownloadStatus.DOWNLOADING
    opts = build_ydl_opts(item, progress_hook=hook)
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(item.video.url, download=True)
        item.output_path = _extract_final_path(info)
        item.status = DownloadStatus.COMPLETED
    except Exception as exc:  # yt_dlp는 다양한 예외 타입을 던질 수 있음
        item.status = DownloadStatus.FAILED
        item.error_message = str(exc)
        raise DownloadError(str(exc)) from exc
    finally:
        if progress_callback:
            progress_callback(item)


def _extract_final_path(info: dict | None) -> str | None:
    """다운로드/후처리(병합, 오디오 추출) 완료 후 최종 파일 경로를 추출한다.

    영상+오디오 병합이나 mp3 변환이 일어나면 progress_hooks가 보고하는
    파일명은 병합/변환 전 임시 파일이므로, yt-dlp가 반환하는
    ``requested_downloads`` 에서 최종 경로를 읽어야 한다.
    """
    if not info:
        return None
    requested = info.get("requested_downloads")
    if requested:
        last = requested[-1]
        return last.get("filepath") or last.get("_filename")
    return info.get("filepath") or info.get("_filename")
