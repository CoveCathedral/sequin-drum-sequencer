# Sequin — the accessible step sequencer

**Sequin is a screen-reader-first, keyboard-only step sequencer and drum machine, designed
non-visually from the ground up.** The spoken tracker grid *is* the interface — not a
visual surface being narrated after the fact. It's built and tested with **NVDA**, for
blind and low-vision musicians.

There isn't much like it. Where accessible music tools usually add a screen-reader layer on
top of a sighted DAW (OSARA over Reaper, and the like), Sequin was made non-visual first:
every control is a native widget that announces its name, value and role, every cursor move
and edit is spoken, and it's fully operable by keyboard alone.

Sequin ships inside the **FreedomHawk** accessible guitar-pedal controller and runs
standalone from this repo.

## What it does

- **Tracker-grid pattern editor** — one row per drum part, a shared time cursor on the
  arrow keys (step / beat / bar), every position and hit spoken directly. Accents, ghost
  notes, per-hit play *chance*, ornaments (flams, drags, rolls), per-line tuning and volume,
  choke groups, and per-line polymeter (parts looping at different lengths).
- **A full standard kit** — kick, snare, rimshot, claps, closed / pedal / open hats, five
  toms, two crashes, splash, china, ride and ride bell, cowbell, tambourine, shaker, 808 and
  perc — with a built-in synth voice for every part, so it plays before you load a thing.
- **500 built-in grooves** across ~60 genres, plus improvised fills (rule-bound randomness).
- **Song Builder** — chain grooves into an arrangement with per-section tempo, kit, swing
  and fills; and a **song-wide beat editor** to edit the whole arrangement on one grid.
- **Kit tools** — import a kit folder, mix a hybrid kit by ear (Kit Sounds), or **build a
  kit from scratch** part by part.
- **A metronome** with odd/prog meters, tap tempo, and a tempo trainer.
- **Sharing** — WAV export, portable `.fhdrum.json` pattern files, and dependency-free
  MIDI import/export.

## Run it

```
pip install -e .[dev]     # or: pip install -e .
python -m sequin          # or run Sequin.bat on Windows
```

Kits live under `Samples/<KitName>/<ROLE>/*.wav` (see `docs/drum-kits.md`). Third-party
sample kits are **not** redistributed here — only the explanatory `Samples/README.md` is
tracked.

## Build a shareable Windows app

```
pip install pyinstaller
python scripts/build_exe.py        # -> dist/Sequin/Sequin.exe
```

Produces a self-contained `dist/Sequin/` folder — zip it and share. It bundles the NVDA
speech bridge and the manual, and ships **synth-only** (no sample audio, so it's small and
carries no third-party kits). A user adds kits with **Import**, **Build Kit**, or by dropping
a `Samples/<KitName>/<ROLE>/*.wav` folder next to `Sequin.exe`.

## Tests

```
pip install -e .[dev]
pytest
```

## License

MIT — see `LICENSE`.
