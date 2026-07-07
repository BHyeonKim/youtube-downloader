"""다운로드 이력을 로컬 JSON 파일로 저장/조회한다."""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone


@dataclass
class HistoryEntry:
    title: str
    url: str
    output_path: str
    status: str
    finished_at: str  # ISO 8601


class HistoryStore:
    """JSON 파일 기반의 단순 이력 저장소."""

    def __init__(self, path: str):
        self.path = path
        if not os.path.exists(self.path):
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
            self._write_all([])

    def _read_all(self) -> list[dict]:
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def _write_all(self, entries: list[dict]) -> None:
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(entries, f, ensure_ascii=False, indent=2)

    def add(self, entry: HistoryEntry) -> None:
        entries = self._read_all()
        entries.append(asdict(entry))
        self._write_all(entries)

    def list_entries(self) -> list[HistoryEntry]:
        return [HistoryEntry(**e) for e in self._read_all()]

    def search(self, keyword: str) -> list[HistoryEntry]:
        keyword_lower = keyword.lower()
        return [e for e in self.list_entries() if keyword_lower in e.title.lower()]

    def clear(self) -> None:
        self._write_all([])


def make_entry(title: str, url: str, output_path: str, status: str) -> HistoryEntry:
    return HistoryEntry(
        title=title,
        url=url,
        output_path=output_path,
        status=status,
        finished_at=datetime.now(timezone.utc).isoformat(),
    )
