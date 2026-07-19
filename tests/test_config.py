"""Tests for the JSON-backed AppSettings store.

This one file holds all of a user's patterns and songs, so the store must survive a corrupt
or wrong-shaped file rather than reset the library or crash every launch.
"""

import json

from sequin.config import AppSettings


def test_set_persists_and_reloads(tmp_path):
    f = tmp_path / "settings.json"
    AppSettings(path=f).set("bpm", 128)
    assert AppSettings(path=f).get("bpm") == 128


def test_non_dict_file_reads_as_empty_not_crash(tmp_path):
    # A settings.json that isn't a JSON object must not make .data a list/int (whose .get
    # would raise during panel construction and brick every launch) — treat it as empty.
    f = tmp_path / "settings.json"
    f.write_text("[1, 2, 3]", encoding="utf-8")
    s = AppSettings(path=f)
    assert s.data == {}
    assert s.get("anything") is None          # .get must not raise


def test_corrupt_main_falls_back_to_backup(tmp_path):
    f = tmp_path / "settings.json"
    s = AppSettings(path=f)
    s.set("kept", "value")        # first save (no .bak yet)
    s.set("kept2", "value2")      # second save rotates the prior good file to .bak
    f.write_text("{ this is not json", encoding="utf-8")   # corrupt the main file
    recovered = AppSettings(path=f)
    assert recovered.get("kept") == "value"   # recovered from the backup


def test_save_is_atomic_and_keeps_a_backup(tmp_path):
    f = tmp_path / "settings.json"
    s = AppSettings(path=f)
    s.set("a", 1)
    s.set("a", 2)                 # overwrite; the previous file becomes settings.json.bak
    assert f.exists() and (tmp_path / "settings.json.bak").exists()
    assert json.loads(f.read_text(encoding="utf-8"))["a"] == 2
    assert json.loads((tmp_path / "settings.json.bak").read_text(encoding="utf-8"))["a"] == 1
