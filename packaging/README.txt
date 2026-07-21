Sequin 1.0.0 - the accessible step sequencer
============================================

Sequin is a screen-reader-first, keyboard-only drum machine and step
sequencer for blind and low-vision musicians. It is built and tested
with NVDA, and designed non-visually from the ground up: the spoken
tracker grid is the interface.


SETUP
-----

1. Extract the whole "Sequin" folder somewhere - your Desktop is fine.
   Keep the folder together: Sequin.exe needs the files beside it.
   (If you are reading this, you have probably already done this part.)

2. Open the Sequin folder and run Sequin.exe.

3. The first launch takes a few extra seconds while the built-in
   synthesizer builds its drum voices. Every launch after that is quick.

No installer, no Python, nothing else to set up.


IF WINDOWS SHOWS A WARNING ON FIRST RUN
---------------------------------------

Windows SmartScreen may show a dialog saying "Windows protected your
PC". That is normal for a new app that is not yet signed - nothing is
wrong.

With NVDA: press Tab until you hear "More info, link" and press Enter.
Then press Tab until you hear "Run anyway, button" and press Enter.
This only happens once.


THE MANUAL
----------

The full user manual ships inside the app:

  Press Alt to open the menus, arrow right to Help, arrow down to
  User Manual, and press Enter. It opens in your browser, structured
  with headings so you can navigate it section by section.

The same manual is also online at:

  https://github.com/CoveCathedral/sequin-drum-sequencer/blob/main/docs/user-manual.md


QUICK START
-----------

Pick a groove from the Groove list and press Start. A few keys worth
knowing from the first minute:

  F5      starts or stops the loop from anywhere in the window
  Ctrl+D  opens a blank Pattern Editor from anywhere
  F1      inside the Pattern Editor, speaks that grid's full key list


ADDING DRUM KITS
----------------

Sequin makes sound out of the box with Spangle, its built-in drum
synthesizer. To add sample kits of your own: use Import Drum Kit inside
the app, or put a folder named Samples next to Sequin.exe with one
folder per kit inside it. The manual's drum kit chapter explains the
folder layout, and how naming samples "loud", "medium" and "soft" gives
a kit real dynamic layers.


ABOUT
-----

Sequin is free software under the GNU Affero General Public License,
version 3 or later. Copyright 2026 Kaylea Fox. Anything you make with
it is yours.

Source code:
  https://github.com/CoveCathedral/sequin-drum-sequencer

Found a bug, or have an idea? Open an issue at the source page -
screen reader testing feedback is especially welcome.
