"""Pattern Editor dialog: the grid, its keyboard language, and what it speaks.

Covers the tracker-style grid (one row per line, a shared cursor on owned arrow keys),
dynamics/chance/ornaments, meter and polymeter, per-line tuning/volume/choke, fills,
undo/redo, the visual track, feel (swing/humanize), audition and save. Nearly every
assertion here is an accessibility assertion: the action must SPEAK, because a blind
user has no other channel for what just changed.
"""

import pytest

wx = pytest.importorskip("wx")

from sequin.practice.patternstore import build_line_kit

from helpers import Key


def _grid_dialog(frame):
    from sequin.ui.drumspanel import PatternEditorDialog
    d = frame.drums
    return PatternEditorDialog(d, d._pattern.copy(), d._current_lines(), d._kits_dir(),
                               set(), d.player, d.bpm, dark=True, settings=d._settings)


def _line_index(dlg, line_id):
    return next(i for i, ln in enumerate(dlg.lines) if ln["id"] == line_id)


def test_grid_rows_one_per_line(frame):
    dlg = _grid_dialog(frame)
    try:
        assert dlg.grid_list.GetCount() == len(dlg.lines)
        assert dlg.grid_list.GetString(0).startswith("Kick:")
        assert "sample" in dlg.grid_list.GetString(0)
    finally:
        dlg.Destroy()


def test_grid_up_down_moves_lines_and_speaks(frame, _silence_audio):
    spoken = _silence_audio
    dlg = _grid_dialog(frame)
    try:
        dlg.grid_list.SetSelection(0)
        dlg._on_grid_key(Key(wx.WXK_DOWN))
        assert dlg.grid_list.GetSelection() == 1
        assert spoken[-1].startswith("Snare:") and "Cursor:" in spoken[-1]
        dlg._on_grid_key(Key(wx.WXK_UP))
        assert dlg.grid_list.GetSelection() == 0
        assert spoken[-1].startswith("Kick:")
        dlg._on_grid_key(Key(wx.WXK_UP))  # clamped at the top
        assert dlg.grid_list.GetSelection() == 0
    finally:
        dlg.Destroy()


def test_grid_add_and_delete_line(frame, _silence_audio):
    from sequin.practice.patternstore import make_line
    dlg = _grid_dialog(frame)
    try:
        before = len(dlg.lines)
        ln = make_line("kick", None, None, existing=dlg.lines)  # stacked synth kick
        assert ln["id"] == "kick 2"
        dlg.lines.append(ln)
        dlg._rebuild_line_kit()
        dlg._rebuild_rows()
        assert dlg._line_kit.voice("kick 2") is not None
        # Toggle a hit on the stacked line, then delete it.
        dlg.grid_list.SetSelection(len(dlg.lines) - 1)
        dlg._cursor = 4
        dlg._on_grid_key(Key(wx.WXK_SPACE))
        assert 4 in dlg.pattern.hits["kick 2"]
        dlg._on_grid_key(Key(wx.WXK_DELETE))
        assert len(dlg.lines) == before
        assert "kick 2" not in dlg.pattern.hits
    finally:
        dlg.Destroy()


def test_grid_cursor_speaks_positions(frame, _silence_audio):
    spoken = _silence_audio
    dlg = _grid_dialog(frame)
    try:
        dlg._on_grid_key(Key(wx.WXK_RIGHT))                          # +1 step
        dlg._on_grid_key(Key(wx.WXK_RIGHT, ctrl=True))               # +1 beat
        dlg._on_grid_key(Key(wx.WXK_RIGHT, ctrl=True, shift=True))   # +1 bar (clamped)
        assert dlg._cursor == dlg.pattern.steps - 1
        assert spoken[-3:] == ["Beat 1.2, empty", "Beat 2.2, empty", "Beat 4.4, empty"]
        dlg._on_grid_key(Key(wx.WXK_HOME))
        assert dlg._cursor == 0 and spoken[-1].startswith("Beat 1")
    finally:
        dlg.Destroy()


def test_grid_space_cycles_dynamics(frame, _silence_audio):
    # Space cycles off -> on -> accent -> ghost -> off, each spoken.
    from sequin.practice import LEVEL_ACCENT, LEVEL_GHOST
    spoken = _silence_audio
    dlg = _grid_dialog(frame)
    try:
        idx = _line_index(dlg, "kick")
        dlg.grid_list.SetSelection(idx)
        dlg._cursor = 2
        dlg._on_grid_key(Key(wx.WXK_SPACE))
        assert 2 in dlg.pattern.hits["kick"] and "Kick on" in spoken[-1]
        dlg._on_grid_key(Key(wx.WXK_SPACE))
        assert dlg.pattern.level_of("kick", 2) == LEVEL_ACCENT
        assert "Kick accent" in spoken[-1]
        dlg._on_grid_key(Key(wx.WXK_SPACE))
        assert dlg.pattern.level_of("kick", 2) == LEVEL_GHOST
        assert "Kick ghost" in spoken[-1]
        dlg._on_grid_key(Key(wx.WXK_SPACE))
        assert 2 not in dlg.pattern.hits.get("kick", []) and "Kick off" in spoken[-1]
        assert dlg.pattern.level_of("kick", 2) is None
        # The row label reflects the (restored) hit count.
        assert dlg.grid_list.GetString(idx).startswith("Kick: 2 hits")
        # The cursor speaks the dynamic state too.
        dlg._on_grid_key(Key(wx.WXK_SPACE))  # on
        dlg._on_grid_key(Key(wx.WXK_SPACE))  # accent
        dlg._on_grid_key(Key(wx.WXK_LEFT))
        dlg._on_grid_key(Key(wx.WXK_RIGHT))
        assert spoken[-1].endswith("accent")
    finally:
        dlg.Destroy()


def test_grid_number_keys_set_chance(frame, _silence_audio):
    # Number keys give the cursor hit a play chance: 5 = 50%, 0 = always. Spoken,
    # in the row label and cursor state, cleared when the hit is turned off.
    spoken = _silence_audio
    dlg = _grid_dialog(frame)
    try:
        idx = _line_index(dlg, "kick")
        dlg.grid_list.SetSelection(idx)
        dlg._cursor = 0                              # the Rock kick has a hit at 0
        dlg._on_grid_key(Key(ord("5")))
        assert dlg.pattern.chance_of("kick", 0) == 50
        assert "50 percent chance" in spoken[-1]
        assert "(1 by chance)" in dlg.grid_list.GetString(idx)
        assert dlg._state_at("kick", 0).endswith("50 percent chance")
        dlg._on_grid_key(Key(ord("0")))             # back to always
        assert dlg.pattern.chance_of("kick", 0) is None
        assert "always plays" in spoken[-1]
        # On an empty step, the key explains itself instead of doing nothing.
        dlg._cursor = 1
        dlg._on_grid_key(Key(ord("5")))
        assert "No hit at this step" in spoken[-1]
        assert dlg.pattern.chance_of("kick", 1) is None
        # Turning a chance hit off clears its chance with it.
        dlg._cursor = 0
        dlg._on_grid_key(Key(ord("3")))
        for _ in range(4):                           # cycle to off from any dynamic
            if 0 not in dlg.pattern.hits.get("kick", []):
                break
            dlg._on_grid_key(Key(wx.WXK_SPACE))
        assert 0 not in dlg.pattern.hits.get("kick", [])
        assert not dlg.pattern.probs
    finally:
        dlg.Destroy()


def test_grid_f_cycles_ornaments(frame, _silence_audio):
    # F cycles plain -> flam -> drag -> roll -> plain on the cursor hit, spoken.
    spoken = _silence_audio
    dlg = _grid_dialog(frame)
    try:
        idx = _line_index(dlg, "snare")
        dlg.grid_list.SetSelection(idx)
        dlg._cursor = 4                              # the Rock snare backbeat
        for expect in ("flam", "drag", "roll"):
            dlg._on_grid_key(Key(ord("F")))
            assert dlg.pattern.ornament_of("snare", 4) == expect
            assert expect in spoken[-1]
        assert "(1 ornamented)" in dlg.grid_list.GetString(idx)
        assert "roll" in dlg._state_at("snare", 4)
        dlg._on_grid_key(Key(ord("F")))             # back to plain
        assert dlg.pattern.ornament_of("snare", 4) is None
        assert "plain stroke" in spoken[-1]
        # No hit -> the key explains itself.
        dlg._cursor = 1
        dlg._on_grid_key(Key(ord("F")))
        assert "No hit at this step" in spoken[-1]
    finally:
        dlg.Destroy()


def test_grid_speak_rhythm_and_step_audition(frame, _silence_audio):
    spoken = _silence_audio
    dlg = _grid_dialog(frame)
    try:
        # R reads the current line's rhythm as beat positions (Rock kick: 1 and 3).
        dlg.grid_list.SetSelection(_line_index(dlg, "kick"))
        dlg._on_grid_key(Key(ord("R")))
        assert spoken[-1].startswith("Kick, 2 hits:")
        assert "Beat 1" in spoken[-1] and "Beat 3" in spoken[-1]
        # S names everything on the cursor step across lines (step 0: kick + hihat).
        dlg._cursor = 0
        dlg._on_grid_key(Key(ord("S")))
        assert spoken[-1].startswith("Beat 1:")
        assert "Kick" in spoken[-1] and "Hi-hat" in spoken[-1]
        # An empty step says so instead of going quiet.
        dlg._cursor = 1
        dlg._on_grid_key(Key(ord("S")))
        assert spoken[-1].endswith(": nothing")
        # A line with no hits reads as such.
        dlg.pattern.hits.pop("kick")
        dlg._on_grid_key(Key(ord("R")))
        assert spoken[-1] == "Kick: no hits"
    finally:
        dlg.Destroy()


def test_editor_undo_redo(frame, _silence_audio):
    spoken = _silence_audio
    dlg = _grid_dialog(frame)
    try:
        idx = _line_index(dlg, "kick")
        dlg.grid_list.SetSelection(idx)
        # A step edit undoes and redoes, spoken with what it was.
        dlg._cursor = 1
        dlg._on_grid_key(Key(wx.WXK_SPACE))
        assert 1 in dlg.pattern.hits["kick"]
        dlg._undo_last()
        assert 1 not in dlg.pattern.hits["kick"] and "Undone: step change" in spoken[-1]
        dlg._redo_last()
        assert 1 in dlg.pattern.hits["kick"] and "Redone: step change" in spoken[-1]
        # A line-property edit (tuning) undoes too, and the kit is rebuilt.
        dlg._change_tune(2)
        assert dlg.lines[idx]["tune"] == 2
        dlg._undo_last()
        assert not dlg.lines[idx].get("tune")
        # A meter change restores the whole shape.
        steps_before = dlg.pattern.steps
        dlg.bars_choice.SetSelection(1)  # 2 bars
        dlg._on_meter(None)
        assert dlg.pattern.steps == steps_before * 2
        dlg._undo_last()
        assert dlg.pattern.steps == steps_before
        # A new edit clears the redo branch; an empty stack says so.
        dlg._on_grid_key(Key(wx.WXK_SPACE))
        assert not dlg._redo
        for _ in range(len(dlg._undo) + 1):
            dlg._undo_last()
        assert "Nothing to undo" in spoken[-1]
    finally:
        dlg.Destroy()


def test_grid_polymeter_line_length(frame, _silence_audio):
    # Minus/plus set a line's own loop length; the cursor stays inside that line's cycle.
    spoken = _silence_audio
    dlg = _grid_dialog(frame)
    try:
        dlg.grid_list.SetSelection(_line_index(dlg, "kick"))
        base = dlg.pattern.steps
        for _ in range(base - 7):
            dlg._on_grid_key(Key(ord("-")))       # shrink kick to 7 steps
        assert dlg.pattern.line_length("kick") == 7
        assert dlg.pattern.is_polymetric()
        assert "length 7 steps" in spoken[-1]
        assert "length 7 steps" in dlg.grid_list.GetString(_line_index(dlg, "kick"))
        # The cursor is clamped to the kick's 7-step cycle.
        dlg._cursor = 0
        for _ in range(20):
            dlg._on_grid_key(Key(wx.WXK_RIGHT))
        assert dlg._cursor == 6
        # Lengthening back to the pattern length un-polymeters it.
        for _ in range(base - 7):
            dlg._on_grid_key(Key(ord("=")))
        assert dlg.pattern.line_length("kick") == base
        assert not dlg.pattern.is_polymetric()
    finally:
        dlg.Destroy()


def test_grid_meter_change(frame):
    dlg = _grid_dialog(frame)
    try:
        dlg.beats_choice.SetSelection(6)   # 7 beats
        dlg.unit_choice.SetSelection(2)    # /8
        dlg.grid_choice.SetSelection(1)    # eighth grid
        dlg.bars_choice.SetSelection(0)    # 1 bar
        dlg._on_meter(None)
        assert dlg.pattern.meter_label() == "7/8"
        assert dlg.pattern.steps == 7
        assert dlg._cursor < dlg.pattern.steps  # cursor clamped into range
    finally:
        dlg.Destroy()


def test_grid_change_preserves_meter_and_speaks_it(frame, _silence_audio):
    # The user's report: "change the grid and it locks to 4/4." Changing the grid is a
    # subdivision change, NOT a meter change — the time signature must survive, and a
    # blind user must hear it reaffirmed (never silently assumed to be 4/4).
    dlg = _grid_dialog(frame)
    try:
        dlg.beats_choice.SetSelection(6)   # 7/8 first
        dlg.unit_choice.SetSelection(2)
        dlg._on_meter(None)
        assert dlg.pattern.meter_label() == "7/8"
        _silence_audio.clear()
        dlg.grid_choice.SetSelection(2)    # now change ONLY the grid
        dlg._on_meter(None)
        assert dlg.pattern.meter_label() == "7/8"      # meter did NOT lock to 4/4
        assert "7/8" in _silence_audio[-1]             # and NVDA said so
        assert "4/4" not in _silence_audio[-1]
    finally:
        dlg.Destroy()


def test_line_tuning_shifts_and_speaks(frame, _silence_audio):
    dlg = _grid_dialog(frame)
    try:
        dlg.grid_list.SetSelection(0)
        line = dlg._current_line()
        _silence_audio.clear()
        dlg._change_tune(2)                      # up a whole step
        assert line["tune"] == 2
        assert "tuned +2" in _silence_audio[-1]
        assert "tuned +2" in dlg._row_label(line)
        dlg._change_tune(-3)                      # now a semitone below base
        assert line["tune"] == -1
        # Tuning bakes into the audio: the line's voice actually changes length.
        base_kit = build_line_kit([{**line, "tune": 0}], dlg._kits_dir, base_kit=dlg._base_kit)
        assert len(dlg._line_kit.voice(line["id"])) != len(base_kit.voice(line["id"]))
    finally:
        dlg.Destroy()


def test_line_volume_trims_and_speaks(frame, _silence_audio):
    import numpy as np
    dlg = _grid_dialog(frame)
    try:
        dlg.grid_list.SetSelection(0)
        line = dlg._current_line()
        loud = float(np.max(np.abs(dlg._line_kit.voice(line["id"]))))
        _silence_audio.clear()
        dlg._change_gain(-6)
        assert line["gain_db"] == -6
        assert "-6 dB" in _silence_audio[-1] and "volume" in _silence_audio[-1]
        assert "volume -6 dB" in dlg._row_label(line)
        quiet = float(np.max(np.abs(dlg._line_kit.voice(line["id"]))))
        assert quiet < loud                         # the baked voice really got quieter
    finally:
        dlg.Destroy()


def test_pattern_editor_fill_span(frame, monkeypatch, _silence_audio):
    from sequin.ui.drumspanel import _FillOptionsDialog
    dlg = _grid_dialog(frame)
    try:
        monkeypatch.setattr(_FillOptionsDialog, "ShowModal", lambda self: wx.ID_OK)
        monkeypatch.setattr(_FillOptionsDialog, "values", lambda self: (100, False))
        monkeypatch.setattr(_FillOptionsDialog, "Destroy", lambda self: None)
        # ; and ' mark a span, L fills it.
        dlg._cursor = 4
        dlg._on_grid_key(Key(ord(";")))
        dlg._cursor = 12
        dlg._on_grid_key(Key(ord("'")))
        assert dlg._mark_start == 4 and dlg._mark_end == 12
        n_before = len(dlg.lines)
        dlg._on_grid_key(Key(ord("L")))
        # The fill added melodic content + a resolving crash, and gave new parts their own
        # lines so they survive Save.
        assert "crash" in dlg.pattern.hits
        assert any(ln["id"] == "crash" for ln in dlg.lines)
        assert dlg._mark_start is None and dlg._mark_end is None   # markers consumed
        # No orphan hits: every part the fill placed has a line (so it saves).
        have = {ln["id"] for ln in dlg.lines}
        assert all(r in have for r in dlg.pattern.hits)
        # It's undoable — the fill and its new lines both revert.
        dlg._undo_last()
        assert "crash" not in dlg.pattern.hits and len(dlg.lines) == n_before
    finally:
        dlg.Destroy()


def test_pattern_editor_fill_respects_line_limit(frame, monkeypatch, _silence_audio):
    from sequin.ui.drumspanel import PatternEditorDialog, _FillOptionsDialog
    from sequin.practice.patternstore import MAX_LINES, make_line
    from sequin.practice.drums import Pattern
    d = frame.drums
    lines = []
    for _ in range(MAX_LINES - 2):                 # already near the cap
        lines.append(make_line("perc", existing=lines))
    dlg = PatternEditorDialog(d, Pattern("t", 16, 4, {}, 4, 4, 1), lines, d._kits_dir(),
                              set(), d.player, d.bpm, dark=True, settings=d._settings)
    try:
        monkeypatch.setattr(_FillOptionsDialog, "ShowModal", lambda self: wx.ID_OK)
        monkeypatch.setattr(_FillOptionsDialog, "values", lambda self: (100, False))
        monkeypatch.setattr(_FillOptionsDialog, "Destroy", lambda self: None)
        dlg._do_fill()                             # whole-pattern fill, only 2 line slots left
        assert len(dlg.lines) == MAX_LINES         # the cap holds
        # No orphan hits: the parts that couldn't get a line were dropped, so what plays
        # equals what saves (no silent loss).
        have = {ln["id"] for ln in dlg.lines}
        assert all(r in have for r in dlg.pattern.hits)
    finally:
        dlg.Destroy()


def test_line_choke_group_cycles_and_speaks(frame, _silence_audio):
    dlg = _grid_dialog(frame)
    try:
        dlg.grid_list.SetSelection(0)
        line = dlg._current_line()
        _silence_audio.clear()
        dlg._cycle_choke()
        assert line["choke"] == 1
        assert "choke group 1" in _silence_audio[-1]
        assert "choke group 1" in dlg._row_label(line)
        # Cycling past the max wraps back to no group.
        from sequin.practice.patternstore import MAX_CHOKE_GROUP
        for _ in range(MAX_CHOKE_GROUP):
            dlg._cycle_choke()
        assert line["choke"] == 0
        assert "no choke group" in _silence_audio[-1]
    finally:
        dlg.Destroy()


def test_line_tuning_clamps_to_range(frame, _silence_audio):
    dlg = _grid_dialog(frame)
    try:
        dlg.grid_list.SetSelection(0)
        line = dlg._current_line()
        for _ in range(40):                      # push well past the limit
            dlg._change_tune(1)
        assert line["tune"] == 24                 # MAX_TUNE, not higher
    finally:
        dlg.Destroy()


def test_grid_none_silences_part(frame):
    dlg = _grid_dialog(frame)
    try:
        dlg.silenced.add("kick")
        assert "kick" not in dlg._effective_pattern().hits  # silenced parts don't render
        kick = dlg.lines[_line_index(dlg, "kick")]
        assert dlg._sample_desc(kick) == "silent"
    finally:
        dlg.Destroy()


def test_grid_save_flow(frame):
    # Simulate the panel's save path without ShowModal.  A tom line isn't shown by
    # default now (the full kit curates to used + core parts), so add an empty one
    # to toggle a fresh hit onto.
    from sequin.ui.drumspanel import PatternEditorDialog
    from sequin.practice.patternstore import make_line
    d = frame.drums
    lines = d._current_lines()
    lines.append(make_line("tom", existing=lines))
    dlg = PatternEditorDialog(d, d._pattern.copy(), lines, d._kits_dir(),
                              set(), d.player, d.bpm, dark=True, settings=d._settings)
    try:
        dlg.grid_list.SetSelection(_line_index(dlg, "tom"))
        dlg._cursor = 1
        dlg._on_grid_key(Key(wx.WXK_SPACE))
        edited, lines = dlg.pattern, [dict(ln) for ln in dlg.lines]
    finally:
        dlg.Destroy()
    d._pattern = edited
    d._line_meta = lines
    d._rebuild_parts()
    assert 1 in d._pattern.hits["tom"]
    assert "Tom 3 (mid)" in d.part_choice.GetItems()


def test_grid_char_hook_routes_enter_and_p(frame, monkeypatch, _silence_audio):
    # A dialog steals Enter (default button) before a list's key handler runs, so
    # grid keys route via the dialog char hook (live-tested regression: Enter and P
    # were dead in the grid).
    dlg = _grid_dialog(frame)
    try:
        monkeypatch.setattr(wx.Window, "FindFocus", staticmethod(lambda: dlg.grid_list))
        opened = []
        monkeypatch.setattr(dlg, "_sample_options", lambda: opened.append(True))
        dlg._on_char_hook(Key(wx.WXK_RETURN))
        assert opened == [True]
        dlg._on_char_hook(Key(ord("P")))
        # Preview speaks the line, plus its musical note when the sound is pitched.
        spoken = _silence_audio[-1]
        assert spoken.startswith("Kick")
        # Non-grid keys fall through to normal dialog handling.
        tab = Key(wx.WXK_TAB)
        tab.skipped = False
        tab.Skip = lambda: setattr(tab, "skipped", True)
        dlg._on_char_hook(tab)
        assert tab.skipped
    finally:
        dlg.Destroy()


def test_editor_audition_has_feel_but_stays_short(frame):
    # Regression: the editor auditions with swing/humanize (feel) but does NOT apply
    # the Improvised arrangement, which would balloon a 1-bar groove into a ~16-bar,
    # 40-second loop that reads as "slow / feel gone".
    import io
    import wave
    from sequin.ui.drumspanel import PatternEditorDialog
    d = frame.drums
    d.fillstyle_choice.SetSelection(1)  # improvised on the main tab
    dlg = PatternEditorDialog(d, d._pattern.copy(), d._current_lines(), d._kits_dir(),
                              set(), d.player, d.bpm, dark=True, settings=d._settings,
                              base_kit=d._kit)
    try:
        dlg.swing_slider.SetValue(40)
        dlg._on_feel(None)
        assert dlg.pattern.swing == pytest.approx(0.4)  # feel lives on the pattern now
        wav = dlg._render()
        w = wave.open(io.BytesIO(wav))
        secs = w.getnframes() / w.getframerate()
        assert secs == pytest.approx(dlg.pattern.loop_seconds(dlg._bpm), rel=0.05)
        assert secs < 10                               # the pattern's own length, not 40+
    finally:
        dlg.Destroy()


def test_editor_growing_bars_repeats_pattern(frame):
    dlg = _grid_dialog(frame)
    try:
        kicks_before = list(dlg.pattern.hits["kick"])
        dlg.bars_choice.SetSelection(3)  # 4 bars
        dlg._on_meter(None)
        assert dlg.pattern.bars == 4
        # No silent bars: the last bar contains the same kicks as the first.
        per_bar = dlg.pattern.steps // 4
        last_bar = [s - 3 * per_bar for s in dlg.pattern.hits["kick"] if s >= 3 * per_bar]
        assert last_bar == kicks_before
    finally:
        dlg.Destroy()


def test_swing_humanize_live_in_the_editor_and_save_with_the_pattern(frame):
    d = frame.drums
    # Feel moved OFF the main tab (it declutters + belongs with the groove).
    assert not hasattr(d, "swing_slider") and not hasattr(d, "humanize_slider")
    from sequin.ui.drumspanel import PatternEditorDialog
    dlg = PatternEditorDialog(d, d._pattern.copy(), d._current_lines(), d._kits_dir(),
                              set(), d.player, d.bpm, dark=True, settings=d._settings)
    try:
        # Sliders start at the groove's own feel. Built-in grooves now carry an idiomatic
        # feel (see GENRE_FEEL in drums.py), so mirror the pattern rather than assuming zero.
        assert dlg.swing_slider.GetValue() == round(dlg.pattern.swing * 100)
        assert dlg.humanize_slider.GetValue() == round(dlg.pattern.humanize * 100)
        if dlg.pattern.swing == 0:
            assert "straight" in dlg.swing_label.GetLabel()
        dlg.swing_slider.SetValue(60)
        dlg.humanize_slider.SetValue(30)
        dlg._on_feel(None)
        # The sliders write straight into the pattern, so feel travels with Save.
        assert dlg.pattern.swing == pytest.approx(0.6)
        assert dlg.pattern.humanize == pytest.approx(0.3)
        assert dlg.swing_label.GetLabel() == "Swing: 60%"
        assert dlg.humanize_label.GetLabel() == "Humanize: 30%"
        # Reopening on that groove restores the sliders from the pattern.
        dlg2 = PatternEditorDialog(d, dlg.pattern.copy(), d._current_lines(), d._kits_dir(),
                                   set(), d.player, d.bpm, dark=True, settings=d._settings)
        try:
            assert dlg2.swing_slider.GetValue() == 60
            assert dlg2.humanize_slider.GetValue() == 30
        finally:
            dlg2.Destroy()
    finally:
        dlg.Destroy()


def test_visual_track_toggles_paints_and_persists(frame, _silence_audio):
    dlg = _grid_dialog(frame)
    try:
        vt = dlg.visual_track
        assert not vt.IsShown()                       # off by default
        assert not vt.AcceptsFocus()                  # display-only, never in tab order
        dlg.visual_cb.SetValue(True)
        dlg._on_toggle_visual(None)
        assert vt.IsShown()
        assert dlg._settings.get("show_visual_track") is True   # preference persisted
        vt.refresh_view()
        w, h = vt.GetVirtualSize()
        assert w > vt.GUTTER and h > 0                # sized to the pattern
        # It paints to a DC without error (proves the draw path is sound headless).
        import wx
        bmp = wx.Bitmap(max(1, w), max(1, h))
        mdc = wx.MemoryDC(bmp)
        vt._paint(mdc)
        mdc.SelectObject(wx.NullBitmap)
    finally:
        dlg.Destroy()


def test_visual_track_opens_shown_when_remembered(frame, _silence_audio):
    d = frame.drums
    d._settings.set("show_visual_track", True)
    dlg = _grid_dialog(frame)
    try:
        assert dlg.visual_cb.GetValue() and dlg.visual_track.IsShown()
    finally:
        dlg.Destroy()
        d._settings.set("show_visual_track", False)
