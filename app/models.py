"""데이터 모델 정의: 영상 메타데이터, 다운로드 큐 항목, 상태."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum


class URLType(str, Enum):
    SINGLE = "single"
    PLAYLIST = "playlist"
    CHANNEL = "channel"
    UNKNOWN = "unknown"


class MediaFormat(str, Enum):
    VIDEO = "video"  # mp4
    AUDIO = "audio"  # mp3


class Quality(str, Enum):
    BEST = "best"
    Q2160P = "2160p"
    Q1080P = "1080p"
    Q720P = "720p"
    Q480P = "480p"
    WORST = "worst"


class DownloadStatus(str, Enum):
    QUEUED = "queued"
    DOWNLOADING = "downloading"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


@dataclass
class VideoInfo:
    """yt-dlp 메타데이터에서 추출한 영상 정보."""

    id: str
    title: str
    url: str
    duration: int | None = None  # seconds
    uploader: str | None = None
    thumbnail_url: str | None = None


@dataclass
class QueueItem:
    """다운로드 큐에 들어가는 단일 작업."""

    video: VideoInfo
    media_format: MediaFormat = MediaFormat.VIDEO
    quality: Quality = Quality.BEST
    output_dir: str = "."
    status: DownloadStatus = DownloadStatus.QUEUED
    progress: float = 0.0  # 0.0 ~ 100.0
    speed: str | None = None
    eta: int | None = None
    error_message: str | None = None
    output_path: str | None = None
    item_id: str = field(default_factory=lambda: str(uuid.uuid4()))
