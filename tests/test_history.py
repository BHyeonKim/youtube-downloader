"""app.history 단위 테스트."""
import os

from app.history import HistoryStore, make_entry


def test_history_store_creates_file(tmp_path):
    path = str(tmp_path / "history.json")
    HistoryStore(path)
    assert os.path.exists(path)


def test_add_and_list_entries(tmp_path):
    path = str(tmp_path / "history.json")
    store = HistoryStore(path)

    entry = make_entry("영상 제목", "https://youtu.be/abc", "out/영상 제목.mp4", "completed")
    store.add(entry)

    entries = store.list_entries()
    assert len(entries) == 1
    assert entries[0].title == "영상 제목"
    assert entries[0].status == "completed"


def test_search_is_case_insensitive(tmp_path):
    path = str(tmp_path / "history.json")
    store = HistoryStore(path)
    store.add(make_entry("Python Tutorial", "u1", "p1", "completed"))
    store.add(make_entry("요리 레시피", "u2", "p2", "completed"))

    results = store.search("python")
    assert len(results) == 1
    assert results[0].title == "Python Tutorial"


def test_clear_removes_all_entries(tmp_path):
    path = str(tmp_path / "history.json")
    store = HistoryStore(path)
    store.add(make_entry("t", "u", "p", "completed"))
    store.clear()
    assert store.list_entries() == []


def test_persistence_across_instances(tmp_path):
    path = str(tmp_path / "history.json")
    store1 = HistoryStore(path)
    store1.add(make_entry("t1", "u1", "p1", "completed"))

    store2 = HistoryStore(path)
    entries = store2.list_entries()
    assert len(entries) == 1
    assert entries[0].title == "t1"
