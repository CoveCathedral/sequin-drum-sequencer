"""UI tests for Sequin's drum-kit surfaces.

Covers the Kit Builder (building a self-contained kit folder part by part), the Kit Sounds
dialog (per-part sample picking, cross-kit borrowing, and its spoken guard on the synth
kit), and re-voicing a saved pattern when the main Kit dropdown changes.
"""

import pytest

wx = pytest.importorskip("wx")


def test_kit_builder_builds_a_loadable_kit(frame, monkeypatch, tmp_path, _silence_audio):
    import struct
    import wave
    from sequin.ui.drumspanel import KitBuilderDialog
    from sequin.practice import ROLES
    from sequin.practice.drums import ROLE_FOLDER, load_kit_from_folder
    d = frame.drums

    def write_wav(p):
        p.parent.mkdir(parents=True, exist_ok=True)
        w = wave.open(str(p), "wb")
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(44100)
        w.writeframes(struct.pack("<200h", *([1500] * 200)))
        w.close()

    kits = tmp_path / "kits"
    kick_wav = kits / "MyPack" / "KICK" / "boom.wav"
    write_wav(kick_wav)
    monkeypatch.setattr(d, "_kits_dir", lambda: kits)

    dlg = KitBuilderDialog(d, kits, ["MyPack"], dark=True)
    monkeypatch.setattr(dlg, "EndModal", lambda code: None)
    try:
        assert set(dlg._roles) == set(ROLES)              # every part buildable
        dlg.part_choice.SetStringSelection("Kick")
        dlg._load_sources()
        assert dlg._sources[0] == "Synth"                 # defaults to synth
        dlg.source_choice.SetStringSelection("MyPack")
        dlg._load_samples()
        assert "kick" in dlg.choices                      # borrowing a kit assigns its sample
        # A blank / bad name is refused.
        seen = []
        monkeypatch.setattr(wx, "MessageBox", lambda *a, **k: seen.append(a))
        dlg.name_field.SetValue("")
        dlg._on_save(None)
        assert seen and not dlg.kit_name
        # A relative name that would escape / pollute the kits dir is refused too.
        dlg.name_field.SetValue("..")
        dlg._on_save(None)
        assert not dlg.kit_name
        dlg.name_field.SetValue("My Build")
        dlg._on_save(None)
        assert dlg.kit_name == "My Build"
    finally:
        dlg.Destroy()

    # The panel writes a self-contained folder: kick from the sample, every other part
    # baked from the synth, and it loads back with those exact roles.
    dest = d._build_kit_folder("My Build", {"kick": kick_wav})
    assert (dest / ROLE_FOLDER["kick"] / "boom.wav").exists()
    kit = load_kit_from_folder(dest)
    assert "kick" in kit.roles() and "snare" in kit.roles() and "tom2" in kit.roles()
    assert kit.voice("kick") is not None and kit.voice("tom2") is not None
    # A failed save (a source sample vanished) leaves no half-written folder behind.
    with pytest.raises(Exception):
        d._build_kit_folder("Broken", {"kick": kits / "gone.wav"})
    assert not (kits / "Broken").exists()


def test_kit_sounds_dialog(frame, tmp_path):
    import numpy as np
    import wave as wave_mod
    from sequin.ui.drumspanel import KitSoundsDialog

    def write_wav(path, n):
        pcm = (0.3 * np.sin(np.arange(n) / 5) * 32767).astype("<i2")
        w = wave_mod.open(str(path), "wb")
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(44100)
        w.writeframes(pcm.tobytes()); w.close()

    # A dedicated kits folder: the dialog scans the kit's SIBLINGS for cross-kit
    # sourcing, so the parent directory must be controlled, not pytest's shared root.
    home = tmp_path / "kits" / "My Kit"
    (home / "KICK").mkdir(parents=True)
    write_wav(home / "KICK" / "a.wav", 4000)
    write_wav(home / "KICK" / "b.wav", 4000)
    dlg = KitSoundsDialog(frame.drums, home, {}, dark=True)
    try:
        assert dlg.part_choice.GetCount() == 1  # just Kick
        assert dlg.source_choice.GetCount() == 1  # no siblings -> just this kit
        assert "This kit" in dlg.source_choice.GetString(0)
        assert dlg.sample_choice.GetCount() == 2
        # Selecting a sample records the choice for that part.
        dlg.sample_choice.SetSelection(1)
        dlg._on_sample(None)
        assert dlg.choices["kick"] == "b.wav"
        dlg._stop_preview()
    finally:
        dlg.Destroy()


def test_kit_sounds_cross_kit_sources(frame, tmp_path):
    import numpy as np
    import wave as wave_mod
    from sequin.ui.drumspanel import KitSoundsDialog

    def write_wav(path, n):
        pcm = (0.3 * np.sin(np.arange(n) / 5) * 32767).astype("<i2")
        w = wave_mod.open(str(path), "wb")
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(44100)
        w.writeframes(pcm.tobytes()); w.close()

    kits = tmp_path / "kits"
    home = kits / "Kit A"
    (home / "KICK").mkdir(parents=True)
    write_wav(home / "KICK" / "own.wav", 4000)
    other = kits / "Kit B"
    (other / "KICK").mkdir(parents=True)
    write_wav(other / "KICK" / "loan.wav", 4000)
    (other / "808").mkdir()
    write_wav(other / "808" / "sub.wav", 4000)

    dlg = KitSoundsDialog(frame.drums, home, {}, dark=True)
    try:
        # The Part list is the union: Kick (both kits) plus 808 (only Kit B has one).
        assert dlg.part_choice.GetCount() == 2
        # Kick can be sourced from either kit; borrowing stores "Kit/file.wav".
        assert dlg._sources == ["Kit A", "Kit B"]
        dlg.source_choice.SetSelection(1)
        dlg._load_samples()
        dlg.sample_choice.SetSelection(0)
        dlg._on_sample(None)
        assert dlg.choices["kick"] == "Kit B/loan.wav"
        # The 808 part exists only in Kit B, so that's its only source (no dead end).
        dlg.part_choice.SetSelection(1)
        dlg._load_sources()
        assert dlg._sources == ["Kit B"]
        dlg.sample_choice.SetSelection(0)
        dlg._on_sample(None)
        assert dlg.choices["808"] == "Kit B/sub.wav"
        # Reopening with saved hybrid choices lands source AND sample back where saved.
        dlg._stop_preview()
        dlg2 = KitSoundsDialog(frame.drums, home, dict(dlg.choices), dark=True)
        try:
            assert dlg2._current_source() == "Kit B"
            files = dlg2._source_files()
            assert files[dlg2.sample_choice.GetSelection()].name == "loan.wav"
        finally:
            dlg2.Destroy()
    finally:
        dlg.Destroy()


def test_kit_sounds_guard_for_synth(frame, monkeypatch):
    # With the synth kit active, the button explains itself in a SPOKEN dialog —
    # a status-bar message is inaudible to a screen reader (live-tested regression).
    shown = {}
    monkeypatch.setattr(wx, "MessageBox",
                        lambda msg, *a, **k: shown.setdefault("msg", msg))
    d = frame.drums
    assert d._kit_dir is None
    d._on_kit_sounds(None)
    assert "synth kit" in shown["msg"].lower()


def test_kit_change_revoices_saved_pattern(frame):
    # Regression: a saved pattern's follow-global lines must re-voice when the main
    # Kit dropdown changes (they used to be frozen to the kit active at save time).
    import numpy as np
    from sequin.practice import DrumKit
    from sequin.practice.patternstore import (lines_to_pattern, make_line,
                                                make_record, save_user_pattern)
    d = frame.drums
    lines = [make_line("kick")]
    lines[0]["steps"] = [0, 8]
    p = lines_to_pattern(lines, 4, 4, 4, 1, "Saved")
    save_user_pattern(d._settings, make_record("Saved", "Prog", 4, 4, 4, 1, lines, p))
    d._rebuild_categories(); d._rebuild_groove_list()
    idx = next(i for i, (k, _r) in enumerate(d._groove_entries) if k == "user")
    d.groove_choice.SetSelection(idx); d._on_groove(None)
    before = np.array(d._pattern_voices.voice("kick")[:1500])
    d._set_kit(DrumKit("Fake", {"kick": np.full(1500, 0.6, dtype=np.float32)}))
    after = np.array(d._pattern_voices.voice("kick")[:1500])
    assert not np.array_equal(before, after)
