"""Standalone Sequin UI smoke test: the app frame and its panels construct and react.

Skips automatically if a wx display cannot be created.  (The deep per-feature UI tests —
pattern editor, song builder, beat editor, kit builder — currently live with FreedomHawk's
integration suite and exercise this same code through its main frame; they migrate here
during the audit pass.)
"""

import pytest

wx = pytest.importorskip("wx")

try:
    _APP = wx.App(False)
except Exception:  # pragma: no cover - no GUI available
    pytest.skip("no wx display available", allow_module_level=True)

from sequin.app import SequinFrame
from sequin.practice.patternstore import resolve_pattern_by_name
from sequin.ui.drumspanel import DrumsPanel, PatternEditorDialog, SongDialog


@pytest.fixture(autouse=True)
def _silence_audio(monkeypatch):
    from sequin.ui import speech
    spoken: list[str] = []
    monkeypatch.setattr(speech, "speak", lambda text, interrupt=True: spoken.append(text))
    yield spoken
    try:
        import winsound
        winsound.PlaySound(None, 0)
    except Exception:  # pragma: no cover - non-Windows / no audio
        pass


@pytest.fixture()
def frame(tmp_path, monkeypatch):
    # Isolate the settings file so tests never touch the real one.
    import sequin.config as cfg
    monkeypatch.setattr(cfg, "_config_dir", lambda app_name="Sequin": tmp_path)
    f = SequinFrame()
    yield f
    f.drums.dispose()
    f.metronome.dispose()
    f.Destroy()
    wx.SafeYield()


def test_frame_builds_with_both_tabs(frame):
    assert frame.listbook.GetPageCount() == 2
    assert isinstance(frame.drums, DrumsPanel)
    # The transport (F5) toggles the current tab without error.
    frame._toggle_current_transport()


def test_drums_panel_has_the_full_kit_and_grooves(frame):
    d = frame.drums
    assert d._kit is not None                      # the synth kit is always present
    assert len(d.groove_choice.GetItems()) > 100   # the built-in library populated
    # The full standard kit is reachable in the Part chooser.
    assert d.kit_choice.GetCount() >= 1


def test_pattern_editor_round_trips_an_edit(frame, monkeypatch):
    d = frame.drums
    dlg = PatternEditorDialog(d, d._pattern.copy(), d._current_lines(), d._kits_dir(),
                              set(), d.player, d.bpm, dark=True, settings=d._settings)
    try:
        line = dlg.lines[0]
        dlg.grid_list.SetSelection(0)
        dlg._cursor = 1
        dlg._toggle_hit()
        assert 1 in dlg.pattern.hits.get(line["id"], [])
    finally:
        dlg.Destroy()


def test_song_builder_opens_and_adds_a_section(frame):
    d = frame.drums
    dlg = SongDialog(d, d, dark=True)
    try:
        dlg.groove.SetStringSelection("Rock")
        dlg._add()
        assert [s["pattern"] for s in dlg._sections] == ["Rock"]
        assert resolve_pattern_by_name("Rock", d._settings) is not None
    finally:
        dlg._stop()
        dlg.Destroy()
