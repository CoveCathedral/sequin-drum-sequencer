# Kits go here

Drop drum-kit folders in this `Samples/` directory and Sequin picks them up automatically:

```
Samples/
└── My Kit/
    ├── KICK/      kick_01.wav, ...
    ├── SNARE/     snare.wav
    ├── HIHAT/     closed_hat.wav
    ├── OPENHAT/   open_hat.wav
    ├── 808/       808_C.wav
    └── ...
```

Folder names are matched loosely (plurals, spaces, keywords) — see `docs/drum-kits.md` for
the full list of parts and how the matcher works, and how to **build a kit from scratch**
or mix a hybrid inside the app.

**Sample kits are not committed to this repository** — they may be copyrighted. This folder
is git-ignored except for this README; bring your own kits.
