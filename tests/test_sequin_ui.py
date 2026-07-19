"""Standalone Sequin UI smoke test: the app frame and its panels construct and react.

Fixtures (wx.App, frame, drums, _silence_audio) live in conftest.py, shared with the
per-feature UI suites (pattern editor, song builder, beat editor, kits).
"""

import pytest
import wx

from sequin.practice.patternstore import resolve_pattern_by_name
from sequin.ui.drumspanel import (
    DrumsPanel,
    PatternEditorDialog,
    SongBeatEditorDialog,
    SongDialog,
)


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


def test_feel_edit_after_undo_clears_stale_redo(frame):
    # Regression: coalescing feel edits must not leave a stale redo entry that Ctrl+Y would
    # replay over the change (the earlier stack-top heuristic did; the run flag fixes it).
    d = frame.drums
    dlg = PatternEditorDialog(d, d._pattern.copy(), d._current_lines(), d._kits_dir(),
                              set(), d.player, d.bpm, dark=True, settings=d._settings)
    try:
        dlg.swing_slider.SetValue(30)          # a feel sweep -> one undo entry, redo cleared
        dlg._on_feel(None)
        assert dlg.pattern.swing == pytest.approx(0.3)
        dlg.grid_list.SetSelection(0)          # a non-feel edit
        dlg._cursor = 2
        dlg._toggle_hit()
        dlg._undo_last()                        # undo the hit -> it becomes redoable
        assert dlg._redo, "the undone hit should be on the redo stack"
        dlg.swing_slider.SetValue(50)          # a fresh feel edit must invalidate that redo
        dlg._on_feel(None)
        assert dlg.pattern.swing == pytest.approx(0.5)
        assert not dlg._redo, "a new feel edit must clear redo (no phantom Ctrl+Y replay)"
    finally:
        dlg.Destroy()


def test_beat_editor_unresolved_warning_does_not_interrupt_focus(frame, monkeypatch):
    # Regression: the "N sections can't be edited here" warning must be spoken via CallAfter
    # with interrupt=False, so NVDA's dialog/focus announcement isn't cut off mid-word.
    from sequin.ui import speech
    calls = []
    monkeypatch.setattr(speech, "speak",
                        lambda text, interrupt=True: calls.append((text, interrupt)))
    d = frame.drums
    dlg = SongBeatEditorDialog(
        d, d, [{"pattern": "Rock", "repeats": 1},
               {"pattern": "NoSuchGroove_zzz", "repeats": 1}], dark=True)
    try:
        wx.Yield()                              # let the CallAfter'd warning fire
        warnings = [c for c in calls if "can't be edited here" in c[0]]
        assert warnings, "an unresolvable section should trigger a spoken warning"
        assert warnings[0][1] is False, "the warning must not interrupt the focus announcement"
    finally:
        dlg._stop()
        dlg.Destroy()


def test_beat_editor_keeps_unresolvable_sections_and_per_section_feel(frame):
    # Regression for two audit fixes: (#14) the audition resolves each section's own tempo
    # and swing, and (#4) Save rebuilds the whole song in order — a section whose groove is
    # missing is carried through in place, never silently dropped.
    d = frame.drums
    sections = [
        {"pattern": "Rock", "repeats": 1, "tempo": 100, "swing": 60},
        {"pattern": "NoSuchGroove_zzz", "repeats": 2},   # groove missing -> unresolvable
        {"pattern": "Rock", "repeats": 1},
    ]
    dlg = SongBeatEditorDialog(d, d, sections, dark=True)
    try:
        assert len(dlg._entries) == 2 and dlg._unresolved == 1
        pat, _reps, bpm, _kit = dlg._resolved()[0]     # first Rock, with its overrides
        assert bpm == 100
        assert pat.swing == pytest.approx(0.6)
        dlg.EndModal = lambda code: None               # not shown modally; skip the real call
        dlg._on_save()
        assert [s["pattern"] for s in dlg.result_sections] == \
            ["Rock", "NoSuchGroove_zzz", "Rock"]
    finally:
        dlg._stop()
        dlg.Destroy()
