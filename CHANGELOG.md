# Sequin changelog

## 1.0.0 — 2026-07-20

The first official release. Sequin is a screen-reader-first, keyboard-only step sequencer
and drum machine for blind and low-vision musicians, designed non-visually from the ground
up and built and tested with NVDA. The spoken tracker grid *is* the interface.

### What's in 1.0

- **The spoken tracker grid** — one row per drum part, a time cursor on the arrow keys
  (step / beat / bar), every move and edit spoken. Accents and ghost notes, per-hit play
  chance ("sometimes" hits that re-roll every pass), ornaments (flams, drags, rolls),
  per-line tuning by ear (with the note spoken), per-line volume, choke groups, and
  per-line polymeter.
- **500 built-in grooves** across ~60 genres, each with idiomatic feel — swing where the
  style swings, ghost-note chatter where funk breathes, ornamented fills that run down the
  toms — plus a Showcase category that demonstrates the engine, and improvised fills that
  never play the same twice.
- **Spangle, Sequin's own drum synthesizer** — a full standard kit (five toms, two crashes,
  splash, china, ride and bell, cowbell, tambourine, shaker, 808 and more) synthesized from
  drum physics: modal membranes, real cymbal partial banks, the classic 808 metal comb.
  Sequin makes sound the moment it opens, no sample files needed.
- **Your own kits** — import any folder of WAV samples. Kits with `loud/medium/soft`
  variants get true **dynamic layers** (accents are different recordings, not just louder),
  numbered takes **round-robin** so nothing machine-guns, missing parts fall back to the
  synth, and missing tom sizes are derived from the kit's own toms so fills always run the
  full rack. Build hybrid kits by ear (Kit Sounds) or from scratch (Build Kit).
- **Song mode** — chain grooves into arrangements with per-section tempo, kit, swing and
  fills; edit the whole song beat-by-beat on one spoken grid; bulk-edit marked sections.
- **Studio-grade rendering** — stereo with a real kit image (hats left, ride right, toms
  sweeping across), windowed-sinc resampling for clean tuning, dithered 16-bit output with
  soft-knee limiting. WAV export, portable pattern files, and MIDI import/export.
- **Practice tools** — a full metronome with odd meters, tap tempo, count-in, and a tempo
  trainer that speeds up as you play.

### Accessibility, because it is the point

Every control is a native widget that announces its name, value and role. Every keypress
gives a spoken result — including the no-ops. Playback stops before dialogs speak so audio
never talks over NVDA. Everything works from the keyboard alone.

### License

Free software: GNU AGPL-3.0-or-later, copyright © 2026 Kaylea Fox. Use it for anything —
gig with it, record with it, teach with it. Sounds you make with it are yours.
