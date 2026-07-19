"""Song Builder UI tests: arranging sections, per-section properties, marking and
bulk edits, saved songs, the unsaved-work close guard, and polymeter containment.

These assert Sequin's accessibility contract as much as its behaviour — actions must
speak, controls must stay operable by keyboard, and destructive prompts must default
to the safe answer.
"""

import pytest

wx = pytest.importorskip("wx")

from sequin.practice.patternstore import resolve_pattern_by_name


def test_song_builder_add_reorder_repeats_render(frame, _silence_audio):
    from sequin.ui.drumspanel import SongDialog
    d = frame.drums
    dlg = SongDialog(d, d, dark=True)
    try:
        # Tabbed layout: Arrange / Add / Songs & Export, plus a display-only timeline.
        assert dlg.notebook.GetPageCount() == 3
        assert not dlg.song_track.AcceptsFocus()
        # Category filter narrows the groove picker (500 grooves is a lot to scroll).
        all_grooves = dlg.groove.GetCount()
        dlg.category.SetStringSelection("Rock")
        dlg._rebuild_grooves()
        assert 0 < dlg.groove.GetCount() < all_grooves
        dlg.category.SetStringSelection("All categories")
        dlg._rebuild_grooves()
        assert dlg.groove.GetCount() == all_grooves

        dlg.groove.SetStringSelection("Rock")
        dlg.repeats.SetSelection(2)          # 3 repeats
        dlg._add()
        dlg.groove.SetStringSelection("Funk")
        dlg.repeats.SetSelection(0)          # 1 repeat
        dlg._add()
        assert [(s["pattern"], s["repeats"]) for s in dlg._sections] == [("Rock", 3), ("Funk", 1)]
        dlg.list.SetSelection(0)
        dlg._change_repeats(1)               # Left/Right edits the selected section
        assert dlg._sections[0]["repeats"] == 4
        # Per-section tempo: the selected section can override the song tempo.
        dlg.sec_tempo.SetStringSelection("150")
        dlg._on_section_tempo(None)
        assert dlg._sections[0]["tempo"] == 150
        dlg._move(1)                         # Alt+Down reorders
        assert [s["pattern"] for s in dlg._sections] == ["Funk", "Rock"]
        # Visual timeline: one block per section, sized by length, selection marked.
        dlg.list.SetSelection(1)
        blocks = dlg._section_blocks()
        assert [label.split(" x")[0] for label, _, _ in blocks] == ["Funk", "Rock"]
        assert blocks[1][2] and not blocks[0][2]           # the selected block is flagged
        assert all(secs > 0 for _, secs, _ in blocks)      # resolved -> real lengths
        if d.player.available:
            assert dlg._render() is not None  # renders the whole song without error
        dlg._remove()
        assert [s["pattern"] for s in dlg._sections] == ["Funk"]
    finally:
        dlg.Destroy()


def test_song_builder_section_swing_and_fills(frame, _silence_audio):
    from sequin.ui.drumspanel import SongDialog
    d = frame.drums
    dlg = SongDialog(d, d, dark=True)
    try:
        dlg.groove.SetStringSelection("Rock")
        dlg.repeats.SetSelection(2)                  # 3 repeats
        dlg._add()
        dlg.list.SetSelection(0)
        # Swing override, settable on the fly from the Arrange row.
        dlg.sec_swing.SetSelection(1 + 6)            # 60%
        dlg._on_section_swing(None)
        assert dlg._sections[0]["swing"] == 60
        # Improvised fills: each repeat becomes a cycle ending in a fresh fill, so
        # the resolved section is one long pattern (same total length), repeats 1.
        dlg.sec_fill.SetSelection(1)
        dlg._on_section_fill(None)
        dlg.sec_fill_amt.SetStringSelection("75%")
        dlg._on_section_fill_amount(None)
        assert dlg._sections[0]["fill"] == "improv"
        assert dlg._sections[0]["fill_amount"] == 75
        base = resolve_pattern_by_name("Rock", d._settings)
        (pattern, reps, _bpm, _kit), = dlg._resolved()
        assert reps == 1 and pattern.steps == base.steps * 3
        assert pattern.swing == pytest.approx(0.6)   # the override rode along
        assert "swing 60%" in dlg._section_label(dlg._sections[0])
        assert "improvised fills 75%" in dlg._section_label(dlg._sections[0])
        # The props row reflects a reopened selection (round-trip through sync).
        dlg._sync_section_props()
        assert dlg.sec_swing.GetStringSelection() == "60%"
        assert dlg.sec_fill.GetSelection() == 1
        assert dlg.sec_fill_amt.GetStringSelection() == "75%"
        # Alt+1/2/3 tab jumps land on each tab (spoken; focus follows async).
        dlg._goto_tab(1)
        assert dlg.notebook.GetSelection() == 1
        dlg._goto_tab(0)
        assert dlg.notebook.GetSelection() == 0
        # The Add tab can seed swing/fills for the next section.
        dlg.add_swing.SetSelection(1 + 3)            # 30%
        dlg.add_fill.SetSelection(1)
        dlg.repeats.SetSelection(0)                  # 1 repeat
        dlg.groove.SetStringSelection("Funk")
        dlg._add()
        assert dlg._sections[1]["swing"] == 30 and dlg._sections[1]["fill"] == "improv"
        # Shift+Right extends by HALF a loop; spoken as "and a half"; renders shorter.
        dlg.list.SetSelection(1)
        dlg._sections[1]["fill"] = None              # halves render exactly sans fills
        dlg._change_repeats(0.5)
        assert dlg._sections[1]["repeats"] == 1.5
        assert "x1.5" in dlg._section_label(dlg._sections[1])
        assert dlg._say_reps(1.5) == "1 and a half repeats"
        assert dlg._say_reps(0.5) == "half a repeat"
        assert dlg._say_reps(2) == "2 repeats"
        funk = resolve_pattern_by_name("Funk", d._settings)
        blocks = dlg._section_blocks()
        assert blocks[1][1] == pytest.approx(funk.loop_seconds(d.bpm) * 1.5)
        dlg._change_repeats(-1)                      # back down through the half
        assert dlg._sections[1]["repeats"] == 0.5
        dlg._change_repeats(-1)                      # clamps at half a repeat
        assert dlg._sections[1]["repeats"] == 0.5
    finally:
        dlg.Destroy()


def test_song_builder_preview_groove_before_adding(frame, _silence_audio):
    from sequin.ui.drumspanel import SongDialog
    d = frame.drums
    if not d.player.available:
        pytest.skip("no audio device available")
    dlg = SongDialog(d, d, dark=True)
    try:
        dlg.groove.SetStringSelection("Rock")
        assert not dlg._previewing
        dlg._preview_groove()                       # audition the selected groove, looping
        assert dlg._previewing and "Stop" in dlg.preview_btn.GetLabel()
        dlg._preview_groove()                       # press again to stop
        assert not dlg._previewing and "Groove" in dlg.preview_btn.GetLabel()
        # Adding a section stops a running preview (it's a section now, not an audition).
        dlg._preview_groove()
        assert dlg._previewing
        dlg._add()
        assert not dlg._previewing and len(dlg._sections) == 1
    finally:
        dlg.Destroy()


def test_song_builder_my_songs_and_plays_once(frame, monkeypatch, _silence_audio):
    from sequin.ui.drumspanel import SongDialog
    from sequin.practice.patternstore import make_song_record, save_song
    d = frame.drums
    loops = []
    monkeypatch.setattr(d.player, "play", lambda wav, loop=True: loops.append(loop))
    monkeypatch.setattr(d.player, "stop", lambda: None)
    dlg = SongDialog(d, d, dark=True)
    try:
        assert [dlg.notebook.GetPageText(i) for i in range(3)] == ["Arrange", "Add", "My Songs"]
        # My Songs lists saved arrangements; Load restores them into Arrange.
        save_song(d._settings, make_song_record(
            "Verse Jam", [{"pattern": "Rock", "repeats": 2}, {"pattern": "Funk", "repeats": 1}]))
        dlg._rebuild_songs()
        assert dlg.songs_list.GetString(0) == "Verse Jam"
        dlg.songs_list.SetSelection(0)
        dlg._load_selected()
        assert [(s["pattern"], s["repeats"]) for s in dlg._sections] == [("Rock", 2), ("Funk", 1)]
        # A song plays through ONCE (not looped — that was the tail-looping bug) and ends.
        dlg._play_selected()
        assert loops == [False] and dlg._end_timer is not None and dlg._playing
        dlg._song_ended()
        assert not dlg._playing and dlg.play_btn.GetLabel() == "&Play"
        dlg._delete_selected()
        assert dlg.songs_list.GetCount() == 0
    finally:
        dlg._stop()
        dlg.Destroy()


def test_song_builder_insert_position(frame, _silence_audio):
    from sequin.ui.drumspanel import SongDialog
    d = frame.drums
    dlg = SongDialog(d, d, dark=True)
    try:
        dlg.groove.SetStringSelection("Rock")
        dlg.repeats.SetSelection(0)
        dlg._add()
        dlg.groove.SetStringSelection("Funk")
        dlg._add()
        # The Add tab's position dropdown tracks the arrangement: end + before each.
        assert dlg.add_pos.GetString(0) == "End of song"
        assert dlg.add_pos.GetCount() == 3
        assert dlg.add_pos.GetString(1).startswith("Before 1: Rock")
        # "Before 1" inserts at the start of the song and selects what landed.
        dlg.add_pos.SetSelection(1)
        dlg.groove.SetStringSelection("Funk")
        dlg._add()
        assert [s["pattern"] for s in dlg._sections] == ["Funk", "Rock", "Funk"]
        assert dlg.list.GetSelection() == 0
        # Back to the predictable default so a stale choice can't surprise later.
        assert dlg.add_pos.GetSelection() == 0 and dlg.add_pos.GetCount() == 4
        # The property row must follow the NEW selection, not the kept index — else
        # NVDA would read one section's tempo while edits landed on another. Give the
        # first section a distinctive tempo, then insert a default section before the
        # second and confirm the Tempo control reflects the inserted (default) section.
        dlg.list.SetSelection(0)
        dlg.sec_tempo.SetStringSelection("150")
        dlg._on_section_tempo(None)                  # section 0 now 150 BPM
        dlg.add_pos.SetSelection(2)                  # Before 2
        dlg.groove.SetStringSelection("Rock")
        dlg._add()
        assert dlg.list.GetSelection() == 1
        assert dlg._sections[1].get("tempo") is None
        assert dlg.sec_tempo.GetStringSelection() == "Song tempo"
    finally:
        dlg.Destroy()


def test_song_builder_mark_and_bulk_edit(frame, _silence_audio):
    from sequin.ui.drumspanel import SongDialog
    d = frame.drums
    dlg = SongDialog(d, d, dark=True)
    try:
        for name in ("Rock", "Funk", "Rock"):
            dlg.groove.SetStringSelection(name)
            dlg._add()
        # Marking is a transient selection, NOT an edit to the song.
        before = dlg._state_key()
        dlg.list.SetSelection(0)
        dlg._toggle_mark()
        dlg.list.SetSelection(2)
        dlg._toggle_mark()                          # cursor ends on the last marked one
        assert dlg._marked_count() == 2
        assert dlg._sections[0].get("_sel") and dlg._sections[2].get("_sel")
        assert dlg._state_key() == before          # marks don't dirty the song
        assert "marked" in dlg.list.GetString(0) and "marked" in dlg.list.GetString(2)
        # Cursor is ON a marked section (2): the edit reaches every marked section.
        assert dlg._sections[2].get("_sel")
        dlg.sec_tempo.SetStringSelection("150")
        dlg._on_section_tempo(None)
        assert [s.get("tempo") for s in dlg._sections] == [150, None, 150]
        # Safety (the reviewed footgun): with the cursor on an UNMARKED section, marks
        # elsewhere are ignored — the edit lands ONLY on the cursor section, never
        # silently on a marked one you're not looking at.
        dlg.list.SetSelection(1)                    # unmarked middle section
        dlg.sec_swing.SetSelection(1 + 5)           # 50%
        dlg._on_section_swing(None)
        assert [s.get("swing") for s in dlg._sections] == [None, 50, None]
        assert dlg._sections[0].get("swing") is None and dlg._sections[2].get("swing") is None
        # A lone mark (not under the cursor) is likewise ignored — edit hits the cursor.
        dlg.list.SetSelection(2)
        dlg._toggle_mark()                          # only section 0 stays marked now
        assert dlg._marked_count() == 1
        dlg.list.SetSelection(1)                    # cursor on unmarked section 1
        dlg.sec_kit.SetStringSelection(dlg.sec_kit.GetString(1))
        dlg._on_section_kit(None)
        assert dlg._sections[1].get("kit") and dlg._sections[0].get("kit") is None
    finally:
        dlg.Destroy()


def test_song_builder_unsaved_close_guard(frame, monkeypatch, _silence_audio):
    from sequin.ui.drumspanel import SongDialog
    from sequin.practice.patternstore import delete_song, make_song_record, save_song
    d = frame.drums
    dlg = SongDialog(d, d, dark=True)
    try:
        ended = []
        monkeypatch.setattr(dlg, "EndModal", lambda code: ended.append(code))
        # The close prompt is a self-labeled MessageDialog (Save / Don't Save / Cancel),
        # not a bare Yes/No box — stub its ShowModal so it never really pops.
        close = {"answer": wx.ID_CANCEL, "calls": 0}
        monkeypatch.setattr(wx.MessageDialog, "ShowModal",
                            lambda self: (close.__setitem__("calls", close["calls"] + 1),
                                          close["answer"])[1])
        # An empty song just closes — no prompt to annoy.
        dlg._on_close(None)
        assert ended == [wx.ID_CANCEL] and close["calls"] == 0
        ended.clear()
        # An unsaved arrangement prompts; Cancel stays in the Song Builder.
        dlg.groove.SetStringSelection("Rock")
        dlg._add()
        close["answer"] = wx.ID_CANCEL
        dlg._on_close(None)
        assert close["calls"] == 1 and ended == []
        # Don't Save closes.
        close["answer"] = wx.ID_NO
        dlg._on_close(None)
        assert ended == [wx.ID_CANCEL]
        ended.clear()
        # Loading over an unsaved song asks too, and the discard prompt defaults to the
        # SAFE answer (No) so a reflexive Enter can't wipe the work — assert wx.NO_DEFAULT
        # is in the style. Declining (No) leaves the current song untouched.
        save_song(d._settings, make_song_record(
            "Other", [{"pattern": "Funk", "repeats": 1}]))
        dlg._rebuild_songs()
        dlg.songs_list.SetStringSelection("Other")
        box = {"answer": wx.NO, "styles": []}
        monkeypatch.setattr(wx, "MessageBox",
                            lambda *a, **k: (box["styles"].append(
                                a[2] if len(a) > 2 else k.get("style", 0)),
                                box["answer"])[1])
        dlg._load_selected()                          # answers NO -> keep current
        assert [s["pattern"] for s in dlg._sections] == ["Rock"]
        assert box["styles"] and (box["styles"][-1] & wx.NO_DEFAULT)
        box["answer"] = wx.YES
        dlg._load_selected()
        assert [s["pattern"] for s in dlg._sections] == ["Funk"]
        # A just-loaded song counts as saved: closing needs no prompt now.
        close["calls"] = 0
        dlg._on_close(None)
        assert ended == [wx.ID_CANCEL] and close["calls"] == 0
        delete_song(d._settings, "Other")
    finally:
        dlg.Destroy()


def test_song_builder_polymeter_containment_toggle(frame, monkeypatch, _silence_audio):
    from sequin.ui.drumspanel import SongDialog
    from sequin.practice.patternstore import delete_song, make_song_record, save_song
    d = frame.drums
    dlg = SongDialog(d, d, dark=True)
    try:
        # Contained is the default: an odd-length line never pushes the next section.
        assert not dlg.poly_tails.GetValue() and not dlg._poly_tails
        dlg.poly_tails.SetValue(True)
        dlg._on_poly_tails(None)
        assert dlg._poly_tails
        # The song-wide choice rides the song record and comes back on load.
        save_song(d._settings, make_song_record(
            "Loose", [{"pattern": "Rock", "repeats": 1}], poly_tails=True))
        dlg._rebuild_songs()
        dlg.poly_tails.SetValue(False)
        dlg._poly_tails = False
        dlg.songs_list.SetStringSelection("Loose")
        monkeypatch.setattr(wx, "MessageBox", lambda *a, **k: wx.YES)
        dlg._load_selected()
        assert dlg._poly_tails and dlg.poly_tails.GetValue()
        delete_song(d._settings, "Loose")
        # The timeline measures a section with the SAME resolution the audio uses, so an
        # improvised-fill section's block is its rendered (nominal) length, never a
        # polymetric LCM that the audio wouldn't play.
        from sequin.practice.drums import section_seconds
        from sequin.practice.patternstore import normalize_section
        dlg._sections = [normalize_section(
            {"pattern": "Rock", "repeats": 2, "fill": "improv"})]
        dlg._rebuild()
        r = dlg._resolve_one(dlg._sections[0])
        (_, secs, _), = dlg._section_blocks()
        assert secs == pytest.approx(
            section_seconds(r[0], r[1], r[2], not dlg._poly_tails), abs=0.001)
    finally:
        dlg.Destroy()
