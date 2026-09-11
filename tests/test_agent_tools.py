"""Unit tests for the agent's pure file tools (no LLM, no browser, no network)."""
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import agent as A  # noqa: E402


def test_write_read_find_delete():
    d = ROOT / "_test_tmp" / "sub"
    p = d / "zzz_unittest_note.txt"
    try:
        r = A.tool_write_file({"path": str(p), "content": "hello"})
        assert r["ok"] and p.exists(), r
        rr = A.tool_read_file({"path": str(p)})
        assert rr["ok"] and "hello" in rr["data"]["content"], rr
        found = A.tool_find_file({"name": "zzz_unittest_note"})
        assert found["ok"] and any("zzz_unittest_note.txt" in m for m in found["data"]["matches"]), found
        A.tool_delete({"path": str(p)})
        assert not p.exists()
        assert A.tool_delete({"path": str(p)})["ok"]
    finally:
        A.tool_delete({"path": str(d.parent)})


def test_create_folder_and_list():
    d = Path(tempfile.mkdtemp()) / "newdir"
    assert A.tool_create_folder({"path": str(d)})["ok"]
    assert d.is_dir()
    lst = A.tool_list_dir({"path": str(d.parent)})
    assert lst["ok"] and any("newdir" in e for e in lst["data"]["entries"])


def test_screenshot_returns_path():
    r = A.tool_screenshot({})
    assert r["ok"], r
    assert Path(r["data"]["path"]).exists()


if __name__ == "__main__":
    test_write_read_find_delete()
    test_create_folder_and_list()
    test_screenshot_returns_path()
    print("ALL UNIT TESTS PASSED")
