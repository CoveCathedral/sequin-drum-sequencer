# Spangle — Sequin's drum synthesizer

**Spangle** is the engine behind Sequin's built-in synth kit. The name keeps the family
resemblance: a *spangle* is another word for a sequin — and cymbals are shiny metal
discs, which is what this engine renders best.

It lives in [`src/sequin/practice/drums.py`](../src/sequin/practice/drums.py) (the
`synth_*` voices and their primitives) with pitch analysis in
[`pitch.py`](../src/sequin/practice/pitch.py). In the app it appears in the Kit list as
**"Synth (built-in)"** — that label is persisted inside saved songs and kit choices, so
it stays as-is even though the engine has a name.

## What it is

Every part of the full standard kit, synthesized — no sample files:

- **Membranes** (kick, five toms, 808): modal banks on the classic non-integer
  circular-membrane ratios, a fast exponential strike-bend, stick/beater transients,
  even-harmonic warmth. The toms run 220→87 Hz, evenly log-spaced, so the set reads as
  one instrument.
- **Wires** (snare, rimshot, clap): the snare couples its wire buzz to the head's motion
  — filtered through the drum's own resonant bands, amplitude-modulated by the body,
  roughened by random flutter — because "sine tones + separate smooth noise" is
  precisely the 1980s-drum-machine sound. Three voicings (tight/fat/crisp) come from one
  model; **fat is the shipped default** (chosen by ear).
- **Metals** (hats, cymbals, bells): the hats share the measured TR-808 six-oscillator
  comb (800/540/522.7/369.6/304.4/205.3 Hz), carved differently per hat. Cymbals are
  dense random inharmonic partial banks — hundreds of partials, each with its own decay,
  high modes dying first — independently seeded per cymbal. Bells (ride bell, cowbell)
  use real bell-mode tables with dominant, tunable fundamentals.
- **Colour** (tambourine, shaker, perc, fx): discrete jingle clouds, motion-shaped
  noise, a minimal pitched woodblock, and an accelerating riser.

## Design principles

1. **Offline, once.** Voices render once and cache (~2.4 s for the whole kit, then
   instant). That budget is the whole advantage: a crash can afford ~400 partials and
   every filter is a clean FFT-domain shape. Spend compute freely; spend code
   complexity carefully.
2. **Deterministic.** Every voice is seeded. The same build sounds identical forever.
3. **Pitch contracts.** Pitched voices keep a clean, detectable fundamental — a blind
   musician tunes them *by ear* against the spoken note readout — and the five toms stay
   strictly ordered high→low. Hats and cymbals never report a key (a spoken-UX rule,
   enforced per role in `pitch.py`).
4. **No baked dynamics.** Accent/ghost gain and ±12-semitone tuning are applied
   downstream, so each voice ships as one neutral one-shot.

## Where it's headed

Planned growth, in step with the audio-engine roadmap:

- **Per-dynamic variants** — synthesized soft/medium/loud strikes per part (not just
  gain), riding the same accent→loud / ghost→soft mapping planned for sample-kit layers.
- **Round-robin variation** — seeded micro-variants so consecutive hits aren't the
  identical waveform.
- **More parts and characters** — alternate kicks/snares/cymbal types (the voicing-knob
  pattern the snare uses is the template: one model, many voicings).

## Licensing & provenance

- Spangle is **part of Sequin**: `AGPL-3.0-or-later`, **copyright © 2026 Kaylea Fox** —
  the repo's [LICENSE](../LICENSE) covers it fully. If it ever spins out as its own
  project (as Sequin did from FreedomHawk), it carries the same license and copyright
  with it.
- **All code is original.** The synthesis *techniques* come from public DSP literature
  and are cited as lineage, not copied as code: Gordon Reid's *Synth Secrets* series
  (Sound on Sound) for the classic percussion recipes, published TR-808 circuit analyses
  for the measured oscillator and envelope values, and standard acoustics references
  (circular-membrane mode ratios, bell mode tables). Circuit constants and physical
  ratios are facts; the implementation is ours.
- **Sounds you render are yours.** The AGPL covers the *code*. Audio produced with
  Spangle — loops, songs, WAV exports, kits baked by the Kit Builder — belongs to the
  musician who made it, with no strings.
