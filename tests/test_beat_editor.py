"""Song Beat Editor tests: navigation, editing, repeat splitting, markers/fill,
per-section tempo, and play modes — the accessibility contract for Sequin's
song-level beat surface.
"""

import pytest

from helpers import Key

wx = pytest.importorskip("wx")


def test_song_beat_editor_navigate_edit_and_save(frame, monkeypatch, _silence_audio):
    from sequin.ui.drumspanel import SongBeatEditorDialog
    from sequin.practice.patternstore import normalize_section, resolve_section_pattern
    d = frame.drums
    sections = [normalize_section({"pattern": "Rock", "repeats": 2}),
                normalize_section({"pattern": "Funk", "repeats": 1})]
    dlg = SongBeatEditorDialog(d, d, sections, dark=True)
    monkeypatch.setattr(dlg, "EndModal", lambda code: None)   # not shown modally in tests
    try:
        rock = resolve_section_pattern(sections[0], d._settings)
        funk = resolve_section_pattern(sections[1], d._settings)
        # One grid across both sections, mixed lengths allowed.
        assert dlg._grid.total_steps == rock.steps * 2 + funk.steps
        assert "kick" in dlg._parts and "snare" in dlg._parts   # union of used + core
        # End lands in the Funk section; Home back to the top.
        dlg._pos = dlg._grid.end()
        assert dlg._grid.section_of(dlg._pos) == 1
        # Char-hook navigation (routes only while the grid has focus).
        monkeypatch.setattr(wx.Window, "FindFocus", staticmethod(lambda: dlg.grid_list))
        dlg._pos = 0
        dlg._on_char_hook(Key(wx.WXK_RIGHT))
        assert dlg._pos == 1
        dlg._on_char_hook(Key(wx.WXK_RIGHT, shift=True))       # +1 beat
        assert dlg._pos == 1 + rock.steps_per_beat
        # Edit: put a snare hit at an empty step in the first section (all-repeats scope).
        dlg.grid_list.SetSelection(dlg._parts.index("snare"))
        dlg._pos = 2
        dlg._toggle()
        assert 2 in dlg._entries[0]["pattern"].hits["snare"] and dlg._entries[0]["dirty"]
        # Save writes the edited section back as an inline pattern.
        dlg._on_save()
        assert dlg.result_sections is not None
        edited = resolve_section_pattern(dlg.result_sections[0], d._settings)
        assert 2 in edited.hits["snare"]
        assert dlg.result_sections[1].get("inline") is None     # untouched section stays a reference
    finally:
        dlg.Destroy()


def test_song_beat_editor_add_line_and_split_repeat(frame, monkeypatch, _silence_audio):
    from sequin.ui.drumspanel import SongBeatEditorDialog
    from sequin.practice.patternstore import normalize_section, resolve_section_pattern
    d = frame.drums
    sections = [normalize_section({"pattern": "Rock", "repeats": 3})]
    dlg = SongBeatEditorDialog(d, d, sections, dark=True)
    monkeypatch.setattr(dlg, "EndModal", lambda code: None)   # not shown modally in tests
    try:
        rock = resolve_section_pattern(sections[0], d._settings)
        # Add Line brings a new kit part into the whole song.
        from sequin.practice import ROLES
        assert "cowbell" not in dlg._parts
        avail = [r for r in ROLES if r not in dlg._parts]
        monkeypatch.setattr(wx.SingleChoiceDialog, "ShowModal", lambda self: wx.ID_OK)
        monkeypatch.setattr(wx.SingleChoiceDialog, "GetSelection",
                            lambda self: avail.index("cowbell"))
        dlg._add_line()
        assert "cowbell" in dlg._parts
        # "Edit this repeat only": editing the 2nd repeat splits it off as its own section.
        dlg.scope_cb.SetValue(True)
        dlg.grid_list.SetSelection(dlg._parts.index("cowbell"))
        dlg._pos = rock.steps + 0            # top of repeat 2 (0-based repeat 1)
        dlg._toggle()
        assert len(dlg._entries) == 3        # before x1, variant x1, after x1
        assert [e["section"].get("repeats") for e in dlg._entries] == [1, 1, 1]
        # The cowbell hit lands only on the split-off variant, not the other repeats.
        assert dlg._entries[1]["pattern"].hits.get("cowbell") == [0]
        assert "cowbell" not in dlg._entries[0]["pattern"].hits
        dlg._on_save()
        assert len(dlg.result_sections) == 3
    finally:
        dlg.Destroy()


def test_song_beat_editor_markers_fill_and_tempo(frame, monkeypatch, _silence_audio):
    from sequin.ui.drumspanel import SongBeatEditorDialog, _FillOptionsDialog
    from sequin.practice.patternstore import normalize_section
    d = frame.drums
    sections = [normalize_section({"pattern": "Rock", "repeats": 2})]
    dlg = SongBeatEditorDialog(d, d, sections, dark=True)
    monkeypatch.setattr(dlg, "EndModal", lambda code: None)
    try:
        # Markers: [ then ] across a span (steps 8..12 of the pattern).
        dlg._pos = 8
        dlg._set_mark("start")
        dlg._pos = 12
        dlg._set_mark("end")
        assert dlg._mark_a == (0, 8) and dlg._mark_b == (0, 12)
        # L fills that span — stub the options dialog to complexity 100, no spill.
        monkeypatch.setattr(_FillOptionsDialog, "ShowModal", lambda self: wx.ID_OK)
        monkeypatch.setattr(_FillOptionsDialog, "values", lambda self: (100, False))
        monkeypatch.setattr(_FillOptionsDialog, "Destroy", lambda self: None)
        dlg._do_fill()
        assert dlg._entries[0]["dirty"]
        # A no-spill fill resolves with a crash on the downbeat at the span's end (13).
        assert 13 in dlg._entries[0]["pattern"].hits.get("crash", [])
        # Clearing the markers, L fills the whole section — a descending tom appears.
        dlg._mark_a = dlg._mark_b = None
        dlg._do_fill()
        pat = dlg._entries[0]["pattern"]
        assert any(r in pat.hits for r in ("tom1", "tom2", "tom", "tom4", "tom5", "snare"))
        # T sets the section tempo — stub the choice dialog to pick 150.
        monkeypatch.setattr(wx.SingleChoiceDialog, "ShowModal", lambda self: wx.ID_OK)
        monkeypatch.setattr(wx.SingleChoiceDialog, "GetStringSelection", lambda self: "150")
        dlg._do_tempo()
        assert dlg._entries[0]["section"]["tempo"] == 150
        dlg._on_save()
        assert dlg.result_sections[0]["tempo"] == 150
        assert dlg.result_sections[0].get("inline") is not None   # the fill was saved
    finally:
        dlg.Destroy()


def test_song_beat_editor_fill_honors_this_repeat_scope(frame, monkeypatch, _silence_audio):
    from sequin.ui.drumspanel import SongBeatEditorDialog, _FillOptionsDialog
    from sequin.practice.patternstore import normalize_section, resolve_section_pattern
    d = frame.drums
    sections = [normalize_section({"pattern": "Rock", "repeats": 3})]
    dlg = SongBeatEditorDialog(d, d, sections, dark=True)
    monkeypatch.setattr(dlg, "EndModal", lambda code: None)
    monkeypatch.setattr(_FillOptionsDialog, "ShowModal", lambda self: wx.ID_OK)
    monkeypatch.setattr(_FillOptionsDialog, "values", lambda self: (80, False))
    monkeypatch.setattr(_FillOptionsDialog, "Destroy", lambda self: None)
    try:
        rock = resolve_section_pattern(sections[0], d._settings)
        # "Edit this repeat only" + L must split the repeat off, not overwrite all three.
        dlg.scope_cb.SetValue(True)
        dlg._pos = rock.steps          # repeat 2
        dlg._do_fill()
        assert len(dlg._entries) == 3          # before x1, variant x1, after x1 — split happened
        assert [e["section"].get("repeats") for e in dlg._entries] == [1, 1, 1]
        # The fill (a resolving crash lands in the variant) is only on the split-off repeat.
        assert "crash" in dlg._entries[1]["pattern"].hits
        assert "crash" not in dlg._entries[0]["pattern"].hits
    finally:
        dlg.Destroy()


def test_song_beat_editor_play_modes(frame, monkeypatch, _silence_audio):
    from sequin.ui.drumspanel import SongBeatEditorDialog
    from sequin.practice.patternstore import normalize_section
    d = frame.drums
    if not d.player.available:
        pytest.skip("no audio device available")
    sections = [normalize_section({"pattern": "Rock", "repeats": 2}),
                normalize_section({"pattern": "Funk", "repeats": 1})]
    dlg = SongBeatEditorDialog(d, d, sections, dark=True)
    calls = []
    monkeypatch.setattr(d.player, "play", lambda wav, loop=True: calls.append((len(wav), loop)))
    monkeypatch.setattr(d.player, "stop", lambda: None)
    monkeypatch.setattr(d, "stop", lambda: None)
    try:
        # Play the whole song: once (loop=False), from the top.
        dlg._play_song(from_here=False)
        assert dlg._playing and calls[-1][1] is False and dlg._end_timer is not None
        whole_len = calls[-1][0]
        dlg._stop()
        assert not dlg._playing and dlg._end_timer is None
        # Play from the cursor: a later position yields a shorter clip than the whole song.
        dlg._pos = dlg._grid.total_steps - 2      # near the end
        dlg._play_song(from_here=True)
        assert dlg._playing and calls[-1][1] is False
        assert calls[-1][0] < whole_len           # from-here is shorter than the whole song
        dlg._song_ended()
        assert not dlg._playing
        # Play section loops.
        dlg._play_section()
        assert dlg._playing and calls[-1][1] is True
        dlg._stop()
    finally:
        dlg.Destroy()


def test_song_beat_editor_edit_then_split_keeps_earlier_edits(frame, monkeypatch, _silence_audio):
    from sequin.ui.drumspanel import SongBeatEditorDialog
    from sequin.practice.patternstore import normalize_section, resolve_section_pattern
    d = frame.drums
    sections = [normalize_section({"pattern": "Rock", "repeats": 3})]
    dlg = SongBeatEditorDialog(d, d, sections, dark=True)
    monkeypatch.setattr(dlg, "EndModal", lambda code: None)
    try:
        # 1) All-repeats edit: add a snare at an empty step (applies to every repeat).
        dlg.grid_list.SetSelection(dlg._parts.index("snare"))
        dlg._pos = 2
        dlg._toggle()
        assert 2 in dlg._entries[0]["pattern"].hits["snare"]
        # 2) Now split off the 2nd repeat and edit only it — the earlier snare must survive
        #    on every piece (the split was the bug that used to discard it).
        rock = resolve_section_pattern(sections[0], d._settings)
        dlg.scope_cb.SetValue(True)
        dlg._pos = rock.steps + 4                 # repeat 2, a fresh step
        dlg._toggle()
        assert len(dlg._entries) == 3
        for e in dlg._entries:                    # the all-repeats snare is on all pieces
            assert 2 in e["pattern"].hits.get("snare", [])
        dlg._on_save()
        for s in dlg.result_sections:
            assert 2 in resolve_section_pattern(s, d._settings).hits["snare"]
    finally:
        dlg.Destroy()


def test_song_beat_editor_leaves_untouched_inline_intact(frame, monkeypatch, _silence_audio):
    # Opening the editor and saving without editing a section must NOT re-serialize its
    # inline (which would drop per-line kit/sample/tune/volume/choke).
    from sequin.ui.drumspanel import SongBeatEditorDialog
    from sequin.practice.patternstore import make_line, make_record, normalize_section
    from sequin.practice.drums import Pattern
    d = frame.drums
    rich = make_record("Chorus", "Song", 4, 4, 4, 1,
                       [dict(make_line("808"), sample="my808.wav", tune=2, choke=3)],
                       Pattern("x", 16, 4, {"808": [0, 8]}))
    sections = [normalize_section({"pattern": "Chorus", "repeats": 1, "inline": rich})]
    dlg = SongBeatEditorDialog(d, d, sections, dark=True)
    monkeypatch.setattr(dlg, "EndModal", lambda code: None)
    try:
        assert not dlg._entries[0]["dirty"]           # untouched -> not dirty
        dlg._on_save()
        line = next(ln for ln in dlg.result_sections[0]["inline"]["lines"]
                    if ln["id"] == "808")
        assert line["sample"] == "my808.wav" and line["tune"] == 2 and line["choke"] == 3
    finally:
        dlg.Destroy()
