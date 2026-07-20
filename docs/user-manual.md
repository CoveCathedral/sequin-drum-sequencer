# Sequin User Manual

Welcome to **Sequin** — a screen-reader-first, keyboard-only drum machine and step
sequencer for blind and low-vision musicians. It was designed non-visually from the ground
up and built and tested with **NVDA**: the spoken tracker grid *is* the interface, not a
label bolted onto a visual one.

This manual is written for keyboard and screen-reader use throughout. Every feature works
without a mouse and announces itself, and the manual is structured with heading levels so
you can navigate it the way you navigate the app — by jumping between headings.

Sequin also ships **inside FreedomHawk** (an accessible editor for the Line 6 Firehawk FX
guitar pedal); this manual covers the standalone app.

## Getting started

### The easy way: the shared build

If someone gave you `Sequin-v1.0-windows.zip`, you don't need Python or any install:

1. Unzip it anywhere (your Desktop is fine).
2. Open the `Sequin` folder and run **`Sequin.exe`**.

That's the whole setup. Sequin opens with a built-in **synth kit** that needs no sound
files, so it makes noise immediately.

### What you need

- **Windows.**
- A screen reader — Sequin is built and tested with **NVDA**. Spoken feedback also works
  through Windows' own speech (SAPI) when NVDA isn't running.
- Speakers or headphones (Sequin plays through your default Windows output device).

### Running from source (for developers)

From the project folder, in a terminal:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
.venv\Scripts\python -m sequin
```

Or double-click **`Sequin.bat`**. After updating the code, **restart the app** — a running
copy keeps using the code it launched with.

## The main window

Sequin has **two tabs** down the left side, with each tab's controls to the right:

- **Sequin** — the drum machine and step sequencer (this is where you'll spend your time).
- **Metronome** — a full accessible metronome.

### Moving around

- **Up/Down arrows** on the tab list move between the two tabs; **Tab** moves into a tab's
  controls; **Shift+Tab** moves back; **Escape** closes dialogs.
- **F5** plays or stops the current tab's loop **from anywhere in the window** — so you
  never have to tab to the Start button. It speaks the new state ("Drum loop started…",
  "Metronome stopped"), and a tab with no loop says so.
- **Ctrl+D** opens a blank **Pattern Editor** from anywhere.
- **Alt** opens the menus: **Tools**, **Settings**, **Help**. Every menu item shows its
  own shortcut.
- **F1** inside the Pattern Editor speaks that grid's key list.

### The menus

- **Tools** — Play or Stop This Tab (F5), Pattern Editor (Ctrl+D), Pattern Library, Song
  Builder, Export Loop as WAV, Export/Import Pattern, Export as MIDI, Import MIDI File, and
  Exit (Alt+F4).
- **Settings** — **Dark Mode**, a high-contrast dark theme with large white labels (on by
  default); the choice persists.
- **Help** — this **User Manual**, and **About Sequin**.

## The Metronome

- **Tempo**: 30–300 BPM (spoken as real BPM). **Tap Tempo** sets it from your taps.
- **Beats per measure** and **Subdivision** (quarters, eighths, triplets, sixteenths).
- For odd meters, check **Non-standard meter** to reveal the beat unit and an **Accent
  grouping** field: type `2+2+3` for a 7/8 and the click accents each group's start.
  Unchecking returns to standard timing.
- The metronome **keeps running while you work in the Sequin tab** — press Stop, press F5
  again, or close the app to end it.

## Sequin — the drum machine

The short version: pick a kit and a groove, press Start, and jam — then go as deep as you
like. The complete guide to sample libraries and kit folders is in
[`docs/drum-kits.md`](drum-kits.md); this is the tour.

### Choosing and building kits

Right under the top of the Sequin tab:

- **Kit** — a dropdown: the built-in **synth kit** (works with no files — powered by
  **Spangle**, Sequin's own drum synthesizer), plus any drum-kit folders you've added.
- **Build Kit…** — make a **new kit from scratch**, part by part. Type a name, pick a part
  (kick, snare, hi-hat, …), then choose **Synth** (the built-in voice) or any kit you have
  to borrow a sample from — arrow through the samples to hear each one. Parts you leave on
  Synth keep the synth voice. Save writes a real, self-contained kit folder you can then
  select, edit in Kit Sounds, and share.
- **Import Drum Kit…** — load a kit folder from anywhere on disk. A kit is a folder with
  subfolders named `KICK`, `SNARE`, `HIHAT`, etc., each holding `.wav` files (see the
  drum-kits guide). Missing parts fall back to the synth voice rather than going silent.
- **Kit Sounds…** — choose which sample each part uses, by ear: pick a part, arrow through
  its samples (each plays as you land on it), Save. The **From kit** dropdown sources a part
  from **any other kit** — build a hybrid (this kit's kick, another's snare), or borrow a
  part this kit doesn't have (an 808 for a kit that shipped none). Hybrids save with the kit
  and come back whenever you select it.

You can also drop kits in without the Import dialog: put a `Samples` folder next to
`Sequin.exe` (or in your working folder), with one subfolder per kit.

### The groove and the loop

- **Category** — filter the grooves by genre family, including categories you create.
- **Groove** — 500 built-in patterns spanning ~60 genres (rock, metal, funk, hip-hop, trap,
  house, techno, drum & bass, reggae, latin, jazz, odd meters, and many more) plus your
  saved ones. Names ending in "fill" include a drum fill.
- **Fill every** — stretch the groove so the fill only comes around every 2–16 bars.
- **Fill style** — "As written", or **Improvised**: freshly generated fills every time,
  varying length and density, always on the meter.
- **Tempo** and **Drum volume** sliders (both spoken as real values). (Swing and Humanize
  live in the Pattern Editor now, saved with each groove — see below.)
- **Part** + **Mute this part** — silence any part live without erasing its steps.
- **Count-in** — when checked, Start plays one accented bar of clicks at your tempo and
  meter before the loop, so you can come in on the downbeat. Stop during it cancels.
- **Tempo trainer** + **Trainer Options…** — when checked, the loop starts at the current
  tempo and **speeds up as you play**, announcing each new BPM. In **Trainer Options** set
  how much it climbs (BPM per step), how often (bars per step), the target, and whether to
  **keep climbing past the target** (endurance mode) or stop and hold there (a defined
  ramp). Great for pushing a fill from slow to fast, hands-free.
- **Start/Stop** — the loop keeps playing across tabs, like the metronome. **F5** toggles
  it from anywhere.

## The Pattern Editor

Open with **Edit Pattern…** on the Sequin tab, or press **Ctrl+D anywhere** for a blank
one. It's a tracker-style grid: one line per drum, and a time cursor on the arrow keys with
**every move spoken** ("Bar 2, Beat 3.2, hit"):

- **Up/Down** — move between lines. **Left/Right** — move by step; **Ctrl** by beat;
  **Ctrl+Shift** by bar; **Home/End** — start and end.
- **Space** — cycle the step: **on → accent → ghost → off**, each spoken. Accents hit
  harder and ghosts whisper, so grooves get real dynamics. **Enter** — this line's sample
  options (any sample from its kit, the automatic default, or None to silence it).
  **Delete** — remove a line. **P** — preview the line's sound. **F1** — speak the key list.
- **Minus / Plus** (`-` / `+`) — set this line's own **loop length** for polymeter: give the
  kick 7 steps while the hats stay at 16 and the parts phase against each other and realign
  — the stacked-meter prog/djent feel. The pulse stays shared, and each line is edited as
  its own loop.
- **Brackets** (`[` / `]`) — **tune** this line down / up a semitone (Shift for a whole
  octave), so an 808 or tom sits in your key. The resulting **note is spoken** ("Kick tuned
  +2, A1"), `P` speaks the note a line plays, and the row shows its tuning. Sequin estimates
  each sample's key by ear, so you can tune to a target pitch without seeing anything; noise
  sounds (hats, cymbals) simply report no key.
- **Comma / Period** (`,` / `.`) — set this line's **volume** in decibels (Shift for a 6 dB
  step), spoken as you go. Balance the parts — pull a boomy or octave-dropped kick back so
  it doesn't wash out the rest. It saves with the pattern; the main tab's **Drum volume**
  still rides the overall level on top.
- **C** — cycle this line's **choke group** (none → 1–4 → none). Lines in the same group cut
  each other's ring, like a closed hat choking an open hat: put both hats in group 1 and
  each closed hit silences the open hat's tail. Works for cymbal chokes too. Saved with the
  pattern.
- **Number keys** (`1`–`9`, `0`) — set the cursor hit's **play chance**: 5 makes it a 50%
  "sometimes" hit that **rolls fresh on every pass**, so the loop varies itself like a real
  drummer decorating a groove. 0 returns it to always. Spoken everywhere the cursor reads,
  counted in the row ("8 hits (2 by chance)"), and saved with the pattern. Songs re-roll
  every repeat of a section.
- **F** — cycle the cursor hit's **ornament**: **flam** (a soft grace stroke just before),
  **drag** (two — a ruff), **roll** (the stroke rebounds across its step, a ratchet), then
  back to plain. Spoken, saved with the pattern; grace strokes follow the hit's tuning,
  volume, dynamics, feel, and chance.
- **Semicolon / Apostrophe** (`;` / `'`) — mark the **start / end of a span** across all
  lines; **L** then drops an **improvised fill** across that span (or the whole pattern if
  nothing is marked), asking how busy the fill is and whether it may spill past the end.
- **Ctrl+Z / Ctrl+Y** — **undo / redo** any edit (steps, dynamics, chances, ornaments,
  tuning, volume, chokes, line length, meter changes, swing/humanize, add/remove line,
  sample picks, Load Groove), up to 100 steps. Spoken with what changed ("Undone: step
  change").
- **R** — read the current line's **whole rhythm** as beat positions ("Kick, 2 hits: Beat 1;
  Beat 3"). **S** — name and play **everything on the cursor step** across all lines ("Beat
  2.2: Kick, Hi-hat ghost"); an empty step says "nothing". **Alt+P** — play/pause the
  audition without leaving the grid.
- **Add Line…** — stack drums and mix libraries: any part, following the kit, from synth, or
  from any kit you have, up to 24 lines.
- The **time signature** lives here: beats per bar, beat unit, grid resolution, bars (1–4).
  Odd meters welcome — 5/4, 7/8, whatever you play. Growing the bar count repeats your music
  into the new bars.
- **Swing** and **Humanize** sliders (0–100%) set this groove's **feel**, and it **saves
  with the pattern** — a shuffle keeps its shuffle. Swing delays the off-beats toward a
  triplet shuffle; humanize adds subtle per-hit timing and volume drift so the loop isn't
  stamped out. The feel follows the groove everywhere: the editor's Play, main-tab playback,
  WAV export, and per-section in songs.
- **Play/Pause** auditions while you edit; **Save** applies; **Save as Preset…** stores the
  pattern under a category (pick one or type a new one); **Load Groove…** pulls any built-in
  or saved pattern into the editor; **Cancel**/Escape discards.
- **Show visual track** — a checkbox that reveals a large, high-contrast picture of the grid
  for usable vision: one row per line, bright cells for hits, **yellow for accents**, **dim
  blue for ghosts**, gridlines on the beats and bars, and a **red box on the cursor**. It's
  display-only — the list above stays the thing you operate, so the screen-reader workflow
  is unchanged — and the setting is remembered between sessions.

## Song mode (the Song Builder)

**Tools → Song Builder…** chains grooves into a full arrangement — intro, verse, chorus,
bridge, and so on. It has three tabs:

- **Arrange** — the list of **sections** (each a groove + repeats) with a high-contrast
  visual timeline beneath. Up/Down select, **Left/Right change the repeats** (Left removes
  one; **Shift steps by half a loop**, so a verse can run x2.5), **Alt+Up / Alt+Down
  reorder**, **Delete** removes, **E** edits — each spoken, with the running song length.
  The selected section has its own **Edit Section** (tweak its groove; stored inline in the
  song), **Tempo** (its own BPM — build speed into the chorus), **Kit** (verse on one kit,
  chorus on another), **Swing** (a per-section override of the groove's own feel), and
  **Fills** + **Fill amount** (**Improvised** ends every repeat in a freshly generated fill;
  amount makes them longer and busier). All of them apply **live while the song plays**.
  **Bulk edit with M:** press **M** to mark a section (spoken, with the running count). To
  change several at once — say sections 3 and 4 both need 140 BPM — mark them, then **with
  the cursor on one of the marked sections** set the Tempo once; the change hits **every
  marked section**. On an **unmarked** section those controls change just that one. Repeats,
  reorder, Delete and Edit always act on the section under the cursor. M again unmarks.
- **Add** — filter the **Category** to a genre first, pick the **Groove**, set Repeats (plus
  starting Swing/Fills), press **Add Section**. **Insert at** chooses where the new section
  lands — the end of the song (the default) or before any existing section. **Preview
  Groove** (or **Alt+V**) loops the picked groove so you can hear it before adding.
- **My Songs** — a list of your saved arrangements: Load one into Arrange, Play it, or
  Delete it; plus Save Current Song and Export as WAV.
- **Beat Editor** — opens the whole song on one spoken tracker grid for fine, beat-by-beat
  editing across every section. The cursor climbs by musical unit (Left/Right = step, Shift =
  beat, Ctrl = bar, Ctrl+Shift or Page Up/Down = section, Home/End = the song's ends,
  Up/Down = parts), each move spoken as "section, repeat, bar, beat". Space cycles a hit, F
  its ornament, Add Line brings in any kit part, and "Edit this repeat only" varies a single
  repeat (it splits off as its own section). **`[`** and **`]`** mark a span and **`L`**
  drops an improvised fill across it; **`T`** sets the section's tempo. Press F1 in the
  editor for the full key list.
- **Keyboard, from anywhere in the dialog:** **Alt+1/2/3** jump between the tabs, **Alt+P**
  plays or stops the song, **Alt+V** previews — all without moving your focus.

**Play** (at the bottom) renders the whole song end to end (gapless, sections can even be in
different meters) and **plays it through once, then ends**.

**Polymeter at section ends:** by default a line with its own odd length keeps cycling
through its section and is **cut off cleanly at the section's end**, so the next section
always starts on its own count. Want the old loose behavior for deliberately weird
composing? Check **"Polymeter lines push past section ends"** on the Arrange tab; the choice
is saved with the song. (Sections set to **Improvised** fills always fit their own length.)

**Your work is guarded:** closing the Song Builder with an unsaved arrangement asks whether
to save first, and loading a saved song over unsaved work asks before replacing it.

Sections reference grooves by name, so **save a pattern as a preset first** if you want your
own groove in a song.

## Managing and sharing patterns (the Tools menu)

- **Pattern Library…** — rename, delete, or recategorize your saved patterns, and rename
  whole categories.
- **Export Loop as WAV…** — the loop exactly as it plays, as an audio file.
- **Export / Import Pattern…** — patterns as small files you can trade with others (feel,
  chances, and ornaments travel with them).
- **Export as MIDI…** — a standard `.mid` any DAW opens, meter included.
- **Import MIDI File…** — reads a MIDI file's drums and opens them **straight in the Pattern
  Editor**: Play to hear it, tweak, Save to keep it.

## Keyboard reference

| Keys | Action |
|------|--------|
| Up/Down (tab list) | Move between the Sequin and Metronome tabs |
| Tab / Shift+Tab | Move between controls |
| F5 | Play or stop the current tab's loop, from anywhere |
| Ctrl+D | Open a blank Pattern Editor, from anywhere |
| Alt | Open the menus (Tools, Settings, Help) |
| Escape | Close a dialog |
| Alt+F4 | Exit |
| F1 (in the Pattern Editor) | Speak the grid's key list |

In the **Pattern Editor** grid: Up/Down lines · Left/Right step · Ctrl+Left/Right beat ·
Ctrl+Shift+Left/Right bar · Home/End · Space cycle on/accent/ghost/off · F ornament ·
`-`/`+` line length (polymeter) · `[`/`]` tune the line (Shift = octave) · `,`/`.` line
volume · C choke group · `1`–`0` play chance · `;`/`'` mark a fill span, L drop a fill ·
Enter sample options · Delete remove line · P preview (speaks the note) · R read the rhythm ·
S read the cursor step · Alt+P play/pause · Ctrl+Z / Ctrl+Y undo / redo.

## Troubleshooting

- **A button seems to do nothing** — it should never happen (everything speaks); if it does,
  report it. Make sure you restarted the app after an update.
- **No drum or metronome sound** — check Windows' output device and volume mixer; Sequin
  plays through the default output device.
- **Spoken grid navigation is silent** — Sequin speaks through the `accessible_output2`
  package. In the shared `.exe` build it's included; from source, reinstall dependencies
  with `.venv\Scripts\python -m pip install -e .`.
- **A drum kit loads with missing parts** — the kit folder needs subfolders named KICK,
  SNARE, HIHAT, etc., containing `.wav` files; see [`docs/drum-kits.md`](drum-kits.md).
  Missing parts fall back to the synth kit rather than going silent.
- **The Groove dropdown doesn't show my edited pattern's name** — after editing, your
  working pattern is what plays even though the dropdown still names the last selected
  groove. Save it as a preset to give it a name in the list.

## Getting help and contributing

Sequin is free software:
[github.com/CoveCathedral/sequin-drum-sequencer](https://github.com/CoveCathedral/sequin-drum-sequencer).
Issues and pull requests are welcome — screen-reader testing feedback most of all.

**Licensing.** Copyright © 2026 Kaylea Fox, under the GNU Affero General Public License v3
or later. **You may use Sequin for anything, including paid work** — gig with it, record and
sell your music, teach with it. If you distribute a modified version, you must share your
source under the same license and keep the credit. If you want to use Sequin in a
closed-source or commercial product, a separate commercial license can be arranged — get in
touch.
