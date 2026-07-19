"""Panel-level UI tests for Sequin: layout, transport, tempo tools and library dialogs.

Covers the main Sequin (drums) panel and the Metronome panel — the count-in, the tempo
trainer, the category/user-pattern filters, the volume and fill controls, the drum library
and MIDI import dialogs, and the F5 transport toggle. Most of these assert the
accessibility contract: the action has to SPEAK, because the status bar is inaudible.
"""

import pytest

wx = pytest.importorskip("wx")

from sequin.ui.drumspanel import DrumsPanel
from sequin.ui.metronomepanel import MetronomePanel
from sequin.practice.drums import PATTERN_LIBRARY


def test_drums_panel_layout(drums):
    d = drums
    assert isinstance(d, DrumsPanel)
    assert d.part_choice.GetCount() >= 1
    # 500 grooves in the dropdown; the kit dropdown holds only kits (import is a
    # separate button, so arrowing through kits never springs a folder dialog).
    assert d.groove_choice.GetCount() == len(PATTERN_LIBRARY)
    assert all("..." not in item for item in d.kit_choice.GetItems())
    assert d.import_button.GetLabel() == "&Import Drum Kit..."


def test_count_in_defers_loop_and_stop_cancels(drums, monkeypatch):
    d = drums
    if not d.player.available:
        pytest.skip("no audio on this system")
    monkeypatch.setattr(d._countin_player, "play_voice", lambda buf: True)  # force success
    d.countin_cb.SetValue(True)
    d._start()
    # The loop hasn't started yet — a count-in timer is pending and Stop is showing.
    assert d._playing and d._countin_timer is not None
    assert d.start_button.GetLabel() == "&Stop"
    d._begin_loop()                                  # timer fires
    assert d._countin_timer is None and d.player.playing
    d.stop()
    # Starting the count-in and stopping mid-count cancels the pending loop.
    d.countin_cb.SetValue(True)
    d._start()
    d.stop()
    assert d._countin_timer is None and not d._playing


def test_tempo_trainer_ramp_climbs_and_holds(drums, monkeypatch, _silence_audio):
    d = drums
    if not d.player.available:
        pytest.skip("no audio on this system")
    d.tempo_slider.SetValue(100)
    d._trainer_cfg = {"step": 5, "bars": 2, "target": 115, "continuous": False}
    d.trainer_cb.SetValue(True)
    d._playing = True
    d._begin_loop()
    assert d._trainer_bpm == 100                      # starts at the slider tempo
    seq = [d._trainer_bpm]
    for _ in range(6):
        if d._trainer_timer:
            d._trainer_timer.Stop()
            d._trainer_timer = None
        else:
            break                                     # stopped climbing (held at target)
        d._trainer_bump()
        seq.append(d._trainer_bpm)
    assert seq[-1] == 115 and d._trainer_timer is None   # reached and holds at target
    assert d.tempo_slider.GetValue() == 115              # the slider tracked the climb
    d.stop()


def test_tempo_trainer_continuous_passes_target(drums, _silence_audio):
    d = drums
    if not d.player.available:
        pytest.skip("no audio on this system")
    d.tempo_slider.SetValue(120)
    d._trainer_cfg = {"step": 10, "bars": 1, "target": 130, "continuous": True}
    d.trainer_cb.SetValue(True)
    d._playing = True
    d._begin_loop()
    for _ in range(3):
        if d._trainer_timer:
            d._trainer_timer.Stop()
            d._trainer_timer = None
        d._trainer_bump()
    assert d._trainer_bpm > 130                        # climbed past the target in endurance mode
    d.stop()
    assert not d._playing and d._trainer_timer is None


def test_category_filter_and_user_presets(drums):
    from sequin.practice.patternstore import make_line, make_record, save_user_pattern
    d = drums
    all_count = len(d._groove_entries)
    assert all_count == len(PATTERN_LIBRARY)  # built-ins, no user patterns yet
    # Filter to the Rock family only.
    d.category_choice.SetSelection(d.category_choice.FindString("Rock"))
    d._rebuild_groove_list()
    assert 0 < len(d._groove_entries) < all_count
    assert all(d.groove_choice.GetString(i).startswith("Rock")
               for i in range(d.groove_choice.GetCount()))
    # Save a mixed-line pattern under a new category; it appears in the list.
    lines = [make_line("kick"), make_line("snare")]
    lines[0]["steps"] = [0, 8]
    from sequin.practice.patternstore import lines_to_pattern
    pattern = lines_to_pattern(lines, 4, 4, 4, 1, name="My Jam")
    rec = make_record("My Jam", "Prog", 4, 4, 4, 1, lines, pattern)
    save_user_pattern(d._settings, rec)
    d._rebuild_categories()
    d.category_choice.SetSelection(d.category_choice.FindString("Prog"))
    d._rebuild_groove_list()
    assert len(d._groove_entries) == 1 and d._groove_entries[0][0] == "user"
    # Selecting it loads the pattern with composite voices and line-named parts.
    d.groove_choice.SetSelection(0)
    d._on_groove(None)
    assert d._pattern.name == "My Jam"
    assert d._pattern_voices is not None
    assert d._pattern_voices.voice("kick") is not None
    assert "Kick" in d.part_choice.GetItems()


def test_drum_volume_and_fill_style_controls(drums):
    d = drums
    assert d.volume_slider.GetValue() == 80
    d.volume_slider.SetValue(40)
    d._on_volume(None)
    assert d.volume_label.GetLabel() == "Drum volume: 40%"
    assert d.fillstyle_choice.GetStringSelection() == "As written"


def test_drum_library_dialog(drums, _silence_audio):
    from sequin.practice.patternstore import (lines_to_pattern, make_line,
                                                make_record, save_user_pattern,
                                                user_patterns)
    from sequin.ui.drumspanel import DrumLibraryDialog
    d = drums
    lines = [make_line("kick")]
    lines[0]["steps"] = [0]
    p = lines_to_pattern(lines, 4, 4, 4, 1, "Lib Test")
    save_user_pattern(d._settings, make_record("Lib Test", "Prog", 4, 4, 4, 1, lines, p))
    dlg = DrumLibraryDialog(d, d._settings, dark=True)
    try:
        assert dlg.pattern_list.GetCount() == 1
        assert dlg.pattern_list.GetString(0).startswith("Lib Test")
        # Store-backed delete reflected after reload.
        from sequin.practice.patternstore import delete_pattern
        delete_pattern(d._settings, "Lib Test")
        dlg._reload()
        assert dlg.pattern_list.GetCount() == 0
        assert user_patterns(d._settings) == []
    finally:
        dlg.Destroy()


def test_midi_import_opens_editor_and_saves(drums, monkeypatch, tmp_path,
                                            _silence_audio):
    # Importing a MIDI file must land straight in the Pattern Editor (live-tested
    # regression: it silently became the current pattern while the Groove dropdown
    # still displayed the old selection, which read as "nothing imported").
    import sequin.ui.drumspanel as dp
    from sequin.practice.midifile import pattern_to_midi
    d = drums
    midi_path = tmp_path / "beat.mid"
    midi_path.write_bytes(pattern_to_midi(d._pattern, 120, {}))

    class _FakeFileDialog:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def ShowModal(self):
            return wx.ID_OK

        def GetPath(self):
            return str(midi_path)

    monkeypatch.setattr(wx, "FileDialog", _FakeFileDialog)
    monkeypatch.setattr(dp.PatternEditorDialog, "ShowModal", lambda self: wx.ID_OK)
    d.import_midi()
    # The editor opened (seeded with the import) and its Save applied the pattern.
    assert d._pattern.name == "MIDI import"
    assert d._line_meta is not None
    assert "Kick" in d.part_choice.GetItems()
    assert any("Imported" in s for s in _silence_audio)


def test_improv_defaults_to_four_bar_cycle(drums, monkeypatch):
    # A 1-bar cycle would put a fill in every bar and wreck the meter (live-tested
    # regression); with Fill every unset, improv must run on a 4-bar cycle.
    import sequin.ui.drumspanel as dp
    captured = {}

    def fake_improv(p, cycle, cycles, seed=None, fill_amount=0.0):
        captured["cycle"], captured["cycles"] = cycle, cycles
        return p

    d = drums
    monkeypatch.setattr(dp, "improvised_loop", fake_improv)
    monkeypatch.setattr(d.player, "play", lambda wav: None)
    d.fillstyle_choice.SetSelection(1)  # Improvised
    d._render_and_play()
    assert captured["cycle"] == 4 and captured["cycles"] == 4


def test_fill_every_selector(drums):
    d = drums
    assert d._fill_every_bars() is None  # default: pattern as written
    d.fill_choice.SetSelection(4)        # 12 bars
    assert d._fill_every_bars() == 12
    from sequin.practice import expand_with_fill
    ex = expand_with_fill(d._pattern, 12)
    assert ex.bars == 12


def test_drums_start_stop_toggles(drums):
    d = drums
    from sequin.practice import NUMPY_AVAILABLE
    if not (NUMPY_AVAILABLE and d.player.available):
        pytest.skip("no audio / numpy")
    d._on_start_stop(None)
    assert d._playing
    assert d.start_button.GetLabel() == "&Stop"
    d._on_start_stop(None)
    assert not d._playing
    assert d.start_button.GetLabel() == "&Start"


def test_metronome_start_stop_toggles(frame):
    m = frame.metronome
    assert isinstance(m, MetronomePanel)
    if not m.player.available:
        pytest.skip("no audio device available")
    m._on_start_stop(None)  # start
    assert m.is_running()
    assert m.start_button.GetLabel() == "&Stop"
    m._on_start_stop(None)  # stop
    assert not m.is_running()
    assert m.start_button.GetLabel() == "&Start"


def test_metronome_odd_meter_toggle(frame):
    m = frame.metronome
    # Standard timing by default: odd-meter controls hidden.
    assert not m.grouping_text.IsShown() and not m.unit_choice.IsShown()
    m.odd_cb.SetValue(True)
    m._on_odd_toggle(None)
    assert m.grouping_text.IsShown() and m.unit_choice.IsShown()
    m.beats_choice.SetSelection(6)  # 7 beats
    m.grouping_text.SetValue("2+2+3")
    m._update_groups()
    assert m._group_starts == {0, 2, 4}
    # Turning it off resets to standard: unit 4, downbeat-only accents, hidden again.
    m.odd_cb.SetValue(False)
    m._on_odd_toggle(None)
    assert not m.grouping_text.IsShown()
    assert m._group_starts == {0}


def test_sequin_f5_toggles_transport(frame, _silence_audio):
    # F5 (routed here from the frame char hook) toggles the CURRENT tab's transport,
    # wherever focus is — no tabbing to the Start button.
    if not frame.metronome.player.available:
        pytest.skip("no audio device available")
    frame.listbook.SetSelection(1)  # Metronome tab
    frame._toggle_current_transport()
    assert frame.metronome.is_running()
    frame._toggle_current_transport()
    assert not frame.metronome.is_running()
