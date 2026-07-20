"""Drum looper engine: synth voices, real-sample loading, and loop rendering.

The pedal never had a drum machine; this adds one to the app.  It is UI-free and
uses numpy for audio.

**Timing compensator.**  Samples differ wildly in length (a clap is short, an 808
rings for a second), so timing must not depend on sample length.  Instead the whole
loop is *pre-mixed* into one buffer: each hit's audio is written at the exact sample
offset of its beat, and voices are summed (true polyphony).  Anything ringing past
the loop end wraps back to the start, so the loop is seamless and every hit's attack
lands precisely on the meter regardless of how long the sample is.  The finished
buffer is looped by the OS (``winsound`` ``SND_LOOP``), the same way the tuner holds
a tone.

Sounds come from the built-in synth kit (no files needed) or a user's own kit — a
folder of ``ROLE`` subfolders (KICK, SNARE, HIHAT, ...) of ``.wav`` files.  See
``docs/drum-kits.md``.
"""

from __future__ import annotations

import io
import math
import os
import random
import struct
import tempfile
import wave
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

try:
    import numpy as np
except ImportError:  # numpy drives all the audio maths
    np = None

try:
    import winsound
except ImportError:  # non-Windows (tests still exercise the pure functions)
    winsound = None

NUMPY_AVAILABLE = np is not None
RATE = 44100
_MAX_SAMPLE_SECONDS = 4.0  # cap any one voice so a long sample can't bloat the loop

#: Canonical drum roles, in display order (top of the kit to the bottom).  This is the
#: full standard kit — every part a complex arrangement (prog included) might reach for.
#: The legacy roles "tom" (the mid tom) and "crash" (crash 1) are kept as-is so the shipped
#: groove library and any saved patterns/songs render unchanged; the extra toms and cymbals
#: are new roles added around them.
ROLES = [
    "kick", "snare", "rimshot", "clap",
    "hihat", "pedalhat", "openhat",
    "tom1", "tom2", "tom", "tom4", "tom5",          # 5 toms: high -> floor ("tom" = mid)
    "crash", "crash2", "splash", "china",
    "ride", "ridebell",
    "cowbell", "tambourine", "shaker",
    "808", "perc", "fx",
]

#: Friendly labels for the roles.
ROLE_LABELS = {
    "kick": "Kick", "snare": "Snare", "rimshot": "Rimshot / cross-stick", "clap": "Clap",
    "hihat": "Hi-hat (closed)", "pedalhat": "Hi-hat (pedal)", "openhat": "Open hat",
    "tom1": "Tom 1 (high)", "tom2": "Tom 2", "tom": "Tom 3 (mid)", "tom4": "Tom 4",
    "tom5": "Floor tom",
    "crash": "Crash 1", "crash2": "Crash 2", "splash": "Splash", "china": "China",
    "ride": "Ride", "ridebell": "Ride bell",
    "cowbell": "Cowbell", "tambourine": "Tambourine", "shaker": "Shaker",
    "808": "808 / sub", "perc": "Perc", "fx": "FX",
}

#: The tom roles, high to low — the fill engine rolls down these.
TOM_ROLES = ["tom1", "tom2", "tom", "tom4", "tom5"]

#: The folder name to write for each role when saving a kit (the Kit Builder), chosen so
#: ``folder_to_role`` maps it straight back to the same role.
ROLE_FOLDER = {
    "kick": "KICK", "snare": "SNARE", "rimshot": "RIMSHOT", "clap": "CLAP",
    "hihat": "HIHAT", "pedalhat": "PEDALHAT", "openhat": "OPENHAT",
    "tom1": "TOM1", "tom2": "TOM2", "tom": "TOM3", "tom4": "TOM4", "tom5": "TOM5",
    "crash": "CRASH", "crash2": "CRASH2", "splash": "SPLASH", "china": "CHINA",
    "ride": "RIDE", "ridebell": "RIDEBELL", "cowbell": "COWBELL",
    "tambourine": "TAMBOURINE", "shaker": "SHAKER", "808": "808", "perc": "PERC",
    "fx": "FX",
}

#: A sensible starting set of lines for a fresh/loaded pattern, so the editor isn't a wall
#: of 24 empty parts — the rest of the full kit is one "Add Line" away.
CORE_ROLES = ["kick", "snare", "hihat", "openhat"]

#: Folder names (upper-cased) mapped to canonical roles when loading a user kit.
#: Exact aliases — especially short ones a keyword scan can't safely infer (OH, CH).
FOLDER_ROLE_MAP = {
    "KICK": "kick", "KICKS": "kick",
    "SNARE": "snare", "SNARES": "snare", "SNAP": "clap", "SNAPS": "clap",
    "RIMSHOT": "rimshot", "RIM": "rimshot", "SIDESTICK": "rimshot", "CROSSSTICK": "rimshot",
    "HIHAT": "hihat", "HAT": "hihat", "HATS": "hihat", "CH": "hihat", "CLOSEDHAT": "hihat",
    "PEDALHAT": "pedalhat", "PEDAL": "pedalhat", "PH": "pedalhat",
    "OPENHAT": "openhat", "OH": "openhat", "OPEN": "openhat",
    "CLAP": "clap", "CLAPS": "clap",
    "PERC": "perc", "PERCUSSION": "perc",
    "808": "808", "808S": "808", "BASS": "808", "SUB": "808",
    "TOM": "tom", "TOMS": "tom", "RACKTOM": "tom1", "HITOM": "tom1", "HIGHTOM": "tom1",
    "MIDTOM": "tom", "LOWTOM": "tom4", "FLOORTOM": "tom5", "FLOOR": "tom5",
    # A clean numbered scheme (exact matches beat the "TOM" keyword) so all five toms
    # round-trip through folder names — needed for kits the Kit Builder writes.
    "TOM1": "tom1", "TOM2": "tom2", "TOM3": "tom", "TOM4": "tom4", "TOM5": "tom5",
    "RIDE": "ride", "RIDEBELL": "ridebell", "BELL": "ridebell",
    "CRASH": "crash", "CRASH2": "crash2", "CYMBAL": "crash",
    "SPLASH": "splash", "CHINA": "china",
    "COWBELL": "cowbell", "COW": "cowbell", "TAMBOURINE": "tambourine", "TAMB": "tambourine",
    "SHAKER": "shaker", "MARACAS": "shaker",
    "FX": "fx",
}

#: Keyword fallback for the endless real-world folder names sample packs invent
#: ("Organic Percussions", "Closed Hats", "808 Bass", "Impacts"): the first group whose
#: keyword appears ANYWHERE in the name wins, so order is most-specific first.  Loops and
#: textures land in FX (rarely triggered) so they don't crowd out real one-shot defaults.
_ROLE_KEYWORDS = [
    (("LOOP",), "fx"),                                              # any *loop* -> keep aside
    (("OPENHAT", "OPEN HAT", "OPEN-HAT"), "openhat"),
    (("PEDALHAT", "PEDAL HAT", "PEDAL-HAT"), "pedalhat"),
    (("808",), "808"),
    (("KICK",), "kick"),
    (("RIMSHOT", "RIM", "SIDESTICK", "CROSSSTICK", "CROSS STICK"), "rimshot"),
    (("SNARE",), "snare"),
    (("CLAP", "SNAP"), "clap"),
    (("FLOOR TOM", "FLOORTOM", "FLOOR"), "tom5"),
    (("HIGH TOM", "HITOM", "RACK TOM", "RACKTOM"), "tom1"),
    (("TOM",), "tom"),
    (("RIDE BELL", "RIDEBELL"), "ridebell"),
    (("RIDE",), "ride"),
    (("CHINA",), "china"),
    (("SPLASH",), "splash"),
    (("CRASH", "CYMBAL"), "crash"),
    (("COWBELL", "COW BELL"), "cowbell"),
    (("TAMBOURINE", "TAMB"), "tambourine"),
    (("SHAKER", "MARACAS"), "shaker"),
    (("CONGA", "BONGO", "CLAVE", "WOODBLOCK", "TRIANGLE", "DJEMBE", "PERC"), "perc"),
    (("HIHAT", "HI-HAT", "HI HAT", "HAT"), "hihat"),
    (("SUB", "BASS"), "808"),
    (("TEXTURE", "IMPACT", "ATMOS", "RISER", "SWEEP", "UPLIFT", "DOWNLIFT",
      "NOISE", "DRONE", "AMBIENT", "STAB", "FX"), "fx"),
]


def folder_to_role(name: str) -> str | None:
    """Map a kit subfolder (or role-named file) to a canonical role.

    Exact aliases win; then the same name with a trailing 's' dropped (Kicks, Snaps);
    then a keyword found anywhere in the name, so packs that name folders "Organic
    Percussions", "Closed Hats" or "808 Bass" still land in the right part.  Returns
    None only when nothing recognisable is present.
    """
    key = " ".join(name.strip().upper().replace("_", " ").replace("-", " ").split())
    compact = key.replace(" ", "")
    if compact in FOLDER_ROLE_MAP:
        return FOLDER_ROLE_MAP[compact]
    if compact.endswith("S") and compact[:-1] in FOLDER_ROLE_MAP:
        return FOLDER_ROLE_MAP[compact[:-1]]
    for keywords, role in _ROLE_KEYWORDS:
        if any(kw.replace(" ", "") in compact for kw in keywords):
            return role
    return None


# -- WAV loading (handles int 8/16/24/32, float 32/64, any rate, mono/stereo) ------

def _trim(data: bytes, width: int) -> bytes:
    """Whole samples only — a stray trailing byte must not make np.frombuffer raise."""
    return data[: (len(data) // width) * width]


def _decode_pcm(data: bytes, audio_format: int, bits: int):
    if audio_format == 1:  # integer PCM
        if bits == 8:
            return (np.frombuffer(data, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
        if bits == 16:
            return np.frombuffer(_trim(data, 2), dtype="<i2").astype(np.float32) / 32768.0
        if bits == 24:
            b = np.frombuffer(data, dtype=np.uint8)
            usable = (len(b) // 3) * 3
            b = b[:usable].reshape(-1, 3).astype(np.int32)
            val = b[:, 0] | (b[:, 1] << 8) | (b[:, 2] << 16)
            val = np.where(val & 0x800000, val - 0x1000000, val)
            return val.astype(np.float32) / float(2 ** 23)
        if bits == 32:
            return (np.frombuffer(_trim(data, 4), dtype="<i4").astype(np.float64)
                    / float(2 ** 31)).astype(np.float32)
    elif audio_format == 3:  # IEEE float
        if bits == 32:
            return np.frombuffer(_trim(data, 4), dtype="<f4").astype(np.float32)
        if bits == 64:
            return np.frombuffer(_trim(data, 8), dtype="<f8").astype(np.float32)
    raise ValueError(f"unsupported WAV: format {audio_format}, {bits}-bit")


def load_wav_float(path) -> tuple["np.ndarray", int]:
    """Load a WAV as mono float32 in [-1, 1] plus its sample rate. Robust to format."""
    raw = Path(path).read_bytes()
    if raw[:4] != b"RIFF" or raw[8:12] != b"WAVE":
        raise ValueError("not a RIFF/WAVE file")
    fmt = data = None
    pos, n = 12, len(raw)
    while pos + 8 <= n:
        cid = raw[pos:pos + 4]
        size = struct.unpack("<I", raw[pos + 4:pos + 8])[0]
        start = pos + 8
        if cid == b"fmt ":
            fmt = raw[start:start + size]
        elif cid == b"data":
            data = raw[start:start + size]
        pos = start + size + (size & 1)  # chunks are word-aligned
    if fmt is None or data is None:
        raise ValueError("missing fmt or data chunk")
    audio_format, channels, rate, _byte_rate, _block, bits = struct.unpack("<HHIIHH", fmt[:16])
    if audio_format == 0xFFFE and len(fmt) >= 26:  # WAVE_FORMAT_EXTENSIBLE
        audio_format = struct.unpack("<H", fmt[24:26])[0]
    x = _decode_pcm(data, audio_format, bits)
    channels = max(1, channels)
    if channels > 1:
        usable = (len(x) // channels) * channels
        x = x[:usable].reshape(-1, channels).mean(axis=1)
    return x.astype(np.float32), rate


_SINC_HALF = 16       # taps per side at unit rate (widened when reading faster = downsampling)
_KAISER_BETA = 8.6    # ~80 dB stopband — clean enough that the window is never the artifact


def _sinc_read(x: "np.ndarray", step: float, n_out: int) -> "np.ndarray":
    """Read *x* at fractional positions ``n * step`` with a Kaiser-windowed sinc.

    This is the one resampling core: rate conversion reads at src/dst, pitch shifting
    reads at 2^(semitones/12).  Linear interpolation (the old core) rolls off highs and
    aliases on pitched-DOWN 808s and toms — exactly the material the tuning feature is
    for — so the upgrade is audible where it matters.  When reading faster than unity the
    kernel widens and its cutoff drops to the new Nyquist (anti-aliasing decimation).
    Ends are treated as silence, which is correct for one-shot hits.  Deterministic.
    """
    if len(x) < 4 or n_out <= 0:          # degenerate input: linear is exact enough
        t = np.arange(max(1, n_out)) * step
        return np.interp(t, np.arange(len(x)), x).astype(np.float32)
    cutoff = min(1.0, 1.0 / step)
    half = min(256, int(np.ceil(_SINC_HALF / cutoff)))
    taps = np.arange(-half + 1, half + 1, dtype=np.float64)
    xp = np.concatenate([np.zeros(half, np.float32), x.astype(np.float32),
                         np.zeros(half + 1, np.float32)])
    out = np.empty(n_out, dtype=np.float32)
    # Chunk the (n_out x taps) work so an 8-second cymbal doesn't balloon memory.
    for a in range(0, n_out, 32768):
        b = min(n_out, a + 32768)
        pos = np.arange(a, b, dtype=np.float64) * step
        i0 = np.floor(pos).astype(np.int64)
        t = taps[None, :] - (pos - i0)[:, None]
        win = np.i0(_KAISER_BETA * np.sqrt(np.clip(1.0 - (t / half) ** 2, 0.0, 1.0)))
        w = np.sinc(cutoff * t) * win
        w /= w.sum(axis=1, keepdims=True)     # unity gain at every read position
        out[a:b] = (xp[i0[:, None] + (taps.astype(np.int64) + half)[None, :]]
                    * w).sum(axis=1).astype(np.float32)
    return out


def resample(x: "np.ndarray", src_rate: int, dst_rate: int) -> "np.ndarray":
    if src_rate == dst_rate or len(x) == 0:
        return x.astype(np.float32)
    n_out = max(1, int(round(len(x) * dst_rate / src_rate)))
    return _sinc_read(x, src_rate / dst_rate, n_out)


def load_sample(path, rate: int = RATE) -> "np.ndarray":
    """Load, downmix, resample to *rate*, and cap the length of a sample file."""
    x, src = load_wav_float(path)
    x = resample(x, src, rate)
    return x[: int(_MAX_SAMPLE_SECONDS * rate)]


# -- synth voices (no files needed) ----------------------------------------------

def _norm(x: "np.ndarray", peak: float = 0.9) -> "np.ndarray":
    m = float(np.max(np.abs(x))) if len(x) else 0.0
    if m > 0:
        x = x / m * peak
    return x.astype(np.float32)


def _t(seconds: float, rate: int) -> "np.ndarray":
    return np.linspace(0, seconds, int(rate * seconds), endpoint=False, dtype=np.float64)


def synth_kick(rate: int = RATE) -> "np.ndarray":
    t = _t(0.18, rate)
    freq = 45.0 + 120.0 * np.exp(-t * 32.0)           # pitch drop ~165 -> 45 Hz
    phase = 2 * np.pi * np.cumsum(freq) / rate
    body = np.sin(phase) * np.exp(-t * 18.0)
    click = np.exp(-t * 450.0) * 0.6                  # beater transient
    return _norm(0.9 * body + click)


def synth_snare(rate: int = RATE) -> "np.ndarray":
    t = _t(0.2, rate)
    rng = np.random.default_rng(1)
    tone = np.sin(2 * np.pi * 180.0 * t) * np.exp(-t * 22.0)
    noise = (rng.random(len(t)) * 2 - 1) * np.exp(-t * 16.0)
    return _norm(0.4 * tone + 0.85 * noise)


def synth_hihat(rate: int = RATE) -> "np.ndarray":
    t = _t(0.05, rate)
    rng = np.random.default_rng(2)
    noise = rng.random(len(t)) * 2 - 1
    noise = np.diff(noise, prepend=0.0)               # crude high-pass -> metallic
    return _norm(noise * np.exp(-t * 90.0))


def synth_openhat(rate: int = RATE) -> "np.ndarray":
    t = _t(0.3, rate)
    rng = np.random.default_rng(3)
    noise = rng.random(len(t)) * 2 - 1
    noise = np.diff(noise, prepend=0.0)
    return _norm(noise * np.exp(-t * 9.0))


def synth_clap(rate: int = RATE) -> "np.ndarray":
    t = _t(0.25, rate)
    rng = np.random.default_rng(4)
    noise = rng.random(len(t)) * 2 - 1
    env = np.zeros(len(t))
    for delay in (0.0, 0.010, 0.020):                 # three quick bursts + a tail
        k = int(delay * rate)
        env[k:] += np.exp(-(t[: len(t) - k]) * 120.0)
    env += 0.4 * np.exp(-t * 18.0)
    return _norm(noise * env)


def synth_808(rate: int = RATE) -> "np.ndarray":
    t = _t(0.6, rate)
    freq = 52.0 + 30.0 * np.exp(-t * 20.0)            # slight drop into a sub tone
    phase = 2 * np.pi * np.cumsum(freq) / rate
    return _norm(np.sin(phase) * np.exp(-t * 5.0))


def synth_tom(rate: int = RATE, base: float = 90.0, decay: float = 12.0,
              secs: float = 0.25) -> "np.ndarray":
    """A pitched tom.  *base* is the settled fundamental (high tom ~150, floor ~70); the
    pitch drops from twice that as the head rings, like a real struck drum."""
    t = _t(secs, rate)
    freq = base + base * np.exp(-t * 9.0)
    phase = 2 * np.pi * np.cumsum(freq) / rate
    return _norm(np.sin(phase) * np.exp(-t * decay))


#: The five toms, high to low, as (role, settled-fundamental-Hz, decay, seconds).
#: The mid tom uses the exact pre-expansion synth_tom defaults (90 Hz, decay 12, 0.25 s)
#: so the legacy "tom" role stays byte-identical for the shipped library and saved patterns.
_TOM_VOICES = {
    "tom1": (150.0, 14.0, 0.22),   # high rack tom
    "tom2": (118.0, 13.0, 0.24),
    "tom":  (90.0, 12.0, 0.25),    # legacy mid tom — unchanged from before the expansion
    "tom4": (74.0, 11.0, 0.30),
    "tom5": (60.0, 9.0, 0.38),     # floor tom
}


def synth_rimshot(rate: int = RATE) -> "np.ndarray":
    """A tight side-stick / rimshot: a short woody tone with a sharp click, very short."""
    t = _t(0.06, rate)
    tone = np.sin(2 * np.pi * 420.0 * t) * np.exp(-t * 55.0)
    click = np.exp(-t * 800.0) * 0.7
    return _norm(0.6 * tone + click, 0.85)


def synth_pedalhat(rate: int = RATE) -> "np.ndarray":
    """A closed pedal hi-hat: like the closed hat but shorter and a touch duller."""
    t = _t(0.04, rate)
    rng = np.random.default_rng(11)
    noise = np.diff(rng.random(len(t)) * 2 - 1, prepend=0.0)
    return _norm(noise * np.exp(-t * 120.0), 0.8)


def synth_crash2(rate: int = RATE) -> "np.ndarray":
    """A second crash — a hair darker and longer than crash 1 (different seed/decay)."""
    t = _t(1.25, rate)
    rng = np.random.default_rng(7)
    noise = np.diff(rng.random(len(t)) * 2 - 1, prepend=0.0)
    return _norm(noise * np.exp(-t * 2.6), 0.72)


def synth_splash(rate: int = RATE) -> "np.ndarray":
    """A splash cymbal: bright and very fast-decaying."""
    t = _t(0.45, rate)
    rng = np.random.default_rng(8)
    noise = np.diff(rng.random(len(t)) * 2 - 1, prepend=0.0)
    return _norm(noise * np.exp(-t * 8.0), 0.7)


def synth_china(rate: int = RATE) -> "np.ndarray":
    """A china / trashy crash: a rougher, noisier wash with a slower onset."""
    t = _t(1.0, rate)
    rng = np.random.default_rng(9)
    noise = rng.random(len(t)) * 2 - 1
    noise = noise + 0.5 * np.diff(noise, prepend=0.0)      # trashier than a clean crash
    return _norm(noise * np.exp(-t * 3.2), 0.72)


def synth_ridebell(rate: int = RATE) -> "np.ndarray":
    """A ride bell: a strong pingy fundamental with a metallic overtone."""
    t = _t(0.7, rate)
    ping = np.sin(2 * np.pi * 640.0 * t) + 0.5 * np.sin(2 * np.pi * 1180.0 * t)
    return _norm(ping * np.exp(-t * 6.0), 0.7)


def synth_cowbell(rate: int = RATE) -> "np.ndarray":
    """A cowbell: two detuned square-ish tones, short and clanky."""
    t = _t(0.35, rate)
    a = np.sign(np.sin(2 * np.pi * 540.0 * t))
    b = np.sign(np.sin(2 * np.pi * 800.0 * t))
    return _norm((0.5 * a + 0.5 * b) * np.exp(-t * 12.0), 0.6)


def synth_tambourine(rate: int = RATE) -> "np.ndarray":
    """A tambourine: a burst of bright jingles (high, fast-decaying noise)."""
    t = _t(0.3, rate)
    rng = np.random.default_rng(12)
    noise = np.diff(rng.random(len(t)) * 2 - 1, prepend=0.0)
    jingle = noise * (np.exp(-t * 20.0) + 0.4 * np.exp(-t * 6.0))
    return _norm(jingle, 0.7)


def synth_shaker(rate: int = RATE) -> "np.ndarray":
    """A shaker: a soft, filtered noise 'chk' with a gentle swell."""
    t = _t(0.12, rate)
    rng = np.random.default_rng(13)
    noise = np.diff(rng.random(len(t)) * 2 - 1, prepend=0.0)
    env = np.exp(-((t - 0.03) ** 2) / (2 * 0.02 ** 2))     # soft bell-shaped burst
    return _norm(noise * env, 0.55)


def synth_crash(rate: int = RATE) -> "np.ndarray":
    t = _t(1.1, rate)
    rng = np.random.default_rng(5)
    noise = np.diff(rng.random(len(t)) * 2 - 1, prepend=0.0)  # bright wash
    return _norm(noise * np.exp(-t * 3.0), 0.75)


def synth_ride(rate: int = RATE) -> "np.ndarray":
    t = _t(0.6, rate)
    rng = np.random.default_rng(6)
    ping = np.sin(2 * np.pi * 950.0 * t) * np.exp(-t * 9.0)
    shimmer = np.diff(rng.random(len(t)) * 2 - 1, prepend=0.0) * np.exp(-t * 7.0)
    return _norm(0.55 * ping + 0.45 * shimmer, 0.7)


def synth_perc(rate: int = RATE) -> "np.ndarray":
    t = _t(0.09, rate)  # short woodblock-style blip
    return _norm(np.sin(2 * np.pi * 620.0 * t) * np.exp(-t * 40.0), 0.8)


# -- kits ------------------------------------------------------------------------

@dataclass
class DrumKit:
    name: str
    voices: dict = field(default_factory=dict)

    def voice(self, role: str):
        return self.voices.get(role)

    def roles(self) -> list[str]:
        # Canonical roles in display order, then any custom line ids (mix-and-match
        # patterns key voices by line id, e.g. "kick 2").
        known = [r for r in ROLES if r in self.voices]
        return known + sorted(k for k in self.voices if k not in ROLES)


def synth_kit(rate: int = RATE) -> DrumKit:
    """The built-in synth kit — a voice for every part of the full standard kit, so the
    whole palette (five toms, second crash, splash, china, ride bell, cowbell, tambourine,
    shaker, pedal hat, rimshot) is always playable and the fill engine never asks for a
    part that isn't there."""
    voices = {
        "kick": synth_kick(rate), "snare": synth_snare(rate),
        "rimshot": synth_rimshot(rate), "clap": synth_clap(rate),
        "hihat": synth_hihat(rate), "pedalhat": synth_pedalhat(rate),
        "openhat": synth_openhat(rate),
        "crash": synth_crash(rate), "crash2": synth_crash2(rate),
        "splash": synth_splash(rate), "china": synth_china(rate),
        "ride": synth_ride(rate), "ridebell": synth_ridebell(rate),
        "cowbell": synth_cowbell(rate), "tambourine": synth_tambourine(rate),
        "shaker": synth_shaker(rate),
        "808": synth_808(rate), "perc": synth_perc(rate),
    }
    for role, (base, decay, secs) in _TOM_VOICES.items():
        voices[role] = synth_tom(rate, base, decay, secs)
    return DrumKit("Synth (built-in)", voices)


#: Name tokens that mark a sample as a vocal chop / chant rather than a drum hit.
#: Producer kits commonly hide these in PERC and FX folders; they make jarring
#: default drum voices, so the auto-pick skips them (they stay selectable by hand).
_VOCAL_TOKENS = {"AHH", "AH", "AAH", "UH", "UHH", "DUH", "HEY", "OOH", "OOOH", "WOO",
                 "YEAH", "YAH", "YA", "VOX", "VOCAL", "CHANT", "TALK", "LAUGH", "SKRRT"}

#: Roles whose default voice should be a short drum hit (808/fx may ring long).
_PERCUSSIVE_ROLES = {"kick", "snare", "rimshot", "clap", "hihat", "pedalhat", "openhat",
                     "tom1", "tom2", "tom", "tom4", "tom5", "crash", "crash2", "splash",
                     "china", "ride", "ridebell", "cowbell", "tambourine", "shaker", "perc"}
_MAX_DEFAULT_HIT_SECONDS = 1.25


def _name_tokens(path) -> set[str]:
    return set(Path(path).stem.upper().replace("_", " ").split())


def wav_duration(path) -> float | None:
    """Seconds of audio in a WAV, from the header only (no decode).  None if unreadable."""
    try:
        raw = Path(path).read_bytes()
        if raw[:4] != b"RIFF" or raw[8:12] != b"WAVE":
            return None
        rate = block = data_size = None
        pos, n = 12, len(raw)
        while pos + 8 <= n:
            cid = raw[pos:pos + 4]
            size = struct.unpack("<I", raw[pos + 4:pos + 8])[0]
            if cid == b"fmt " and size >= 16:
                _fmt, _ch, rate, _br, block, _bits = struct.unpack(
                    "<HHIIHH", raw[pos + 8:pos + 24])
            elif cid == b"data":
                data_size = size
            pos += 8 + size + (size & 1)
        if not rate or not block or data_size is None:
            return None
        return data_size / block / rate
    except Exception:  # noqa: BLE001 - a best-effort probe: a truncated header (struct.error),
        return None    # an unreadable file (OSError), anything — must never crash a caller.


def list_role_files(kit_dir) -> dict[str, list]:
    """Every .wav per recognised role in a kit directory, sorted by name.

    Several subfolders can resolve to the same role — a pack may ship "Percussions",
    "Organic Percussions", "Shakers" and "Tambourine", all percussion — so their files are
    MERGED into that role's pool instead of the first folder winning.  Every sample then
    stays reachable in Kit Sounds, even when more folders exist than there are roles.
    """
    p = Path(kit_dir)
    out: dict[str, list] = {}
    if not p.is_dir():
        return out
    for sub in sorted(p.iterdir()):
        if not sub.is_dir():
            continue
        role = folder_to_role(sub.name)
        if role is None:
            continue
        wavs = sorted(sub.glob("*.wav"))
        if wavs:
            out.setdefault(role, []).extend(wavs)
    return out


def default_sample_for(role: str, files: list):
    """The best default file for a role: for drum-hit roles, prefer the first file
    that is neither vocal-named nor longer than a hit; otherwise just the first."""
    if not files:
        return None
    if role in _PERCUSSIVE_ROLES:
        for f in files:
            if _name_tokens(f) & _VOCAL_TOKENS:
                continue
            dur = wav_duration(f)
            if dur is not None and dur > _MAX_DEFAULT_HIT_SECONDS:
                continue
            return f
    return files[0]


def split_kit_choice(value: str | None) -> tuple[str | None, str | None]:
    """Split a Kit Sounds choice into (source kit or None, filename).

    A plain filename means this kit's own folders (the historical format); a
    ``"Other Kit/file.wav"`` value borrows the file from a sibling kit's same part —
    that's how hybrid kits are stored.  Folder names can't contain a slash on
    Windows, so the separator is unambiguous.
    """
    if not value:
        return None, None
    if "/" in value:
        kit, _, name = value.partition("/")
        return (kit or None), (name or None)
    return None, value


def load_kit_from_folder(path, rate: int = RATE, choices: dict | None = None) -> DrumKit:
    """Load one sample per recognised ROLE subfolder (or role-named files).

    *choices* optionally maps role -> filename (basename) to use instead of the
    automatic pick, so users can select each part's sample (see the Kit Sounds
    dialog).  A ``"Other Kit/file.wav"`` value borrows that part from a SIBLING kit
    folder (same parent directory) — a hybrid kit — and can even add a part this kit
    has no folder for.  Unknown or missing entries fall back to the automatic pick.
    """
    p = Path(path)
    choices = choices or {}
    voices: dict = {}

    def sibling_files(kit_name: str, role: str) -> list:
        return list_role_files(p.parent / kit_name).get(role, [])

    for role, wavs in list_role_files(p).items():
        ordered = list(wavs)
        src_kit, chosen_name = split_kit_choice(choices.get(role))
        pool = sibling_files(src_kit, role) if src_kit else ordered
        chosen = next((w for w in pool if w.name == chosen_name), None)
        if chosen is None:
            chosen = default_sample_for(role, ordered)
        if chosen is not None:  # try the pick first, then this kit's own as fallbacks
            ordered = [chosen] + [w for w in ordered if w != chosen]
        for wav in ordered:
            try:
                voices[role] = load_sample(wav, rate)
                break
            except Exception:  # noqa: BLE001 - skip unreadable files
                continue
    # Borrowed parts this kit has no folder of its own for (say, an 808 from another
    # kit dropped into a kit that never shipped one).
    for role, value in choices.items():
        if role in voices:
            continue
        src_kit, chosen_name = split_kit_choice(value)
        if not src_kit:
            continue
        chosen = next((w for w in sibling_files(src_kit, role) if w.name == chosen_name), None)
        if chosen is not None:
            try:
                voices[role] = load_sample(chosen, rate)
            except Exception:  # noqa: BLE001
                pass
    if not voices and p.is_dir():  # flat folder of role-named files (kick.wav, snare.wav)
        for wav in sorted(p.glob("*.wav")):
            role = folder_to_role(wav.stem)
            if role and role not in voices:
                try:
                    voices[role] = load_sample(wav, rate)
                except Exception:  # noqa: BLE001
                    continue
    return DrumKit(p.name, voices)


# -- patterns --------------------------------------------------------------------

#: Per-hit dynamic levels.  A hit absent from ``Pattern.levels`` plays normal.
LEVEL_ACCENT = "accent"
LEVEL_GHOST = "ghost"
_LEVEL_GAIN = {None: 1.0, LEVEL_ACCENT: 1.45, LEVEL_GHOST: 0.4}


@dataclass
class Pattern:
    name: str
    steps: int                 # total grid steps in one loop
    steps_per_beat: int        # grid steps per quarter note
    hits: dict                 # role -> list of step indices it fires on
    beats_per_bar: int = 4     # time-signature numerator
    beat_unit: int = 4         # time-signature denominator (2/4/8/16)
    bars: int = 1
    levels: dict = field(default_factory=dict)   # role -> {step: "accent"|"ghost"}
    lengths: dict = field(default_factory=dict)  # role -> per-line loop length (polymeter)
    swing: float = 0.0        # 0..1 shuffle feel, saved with the groove (edited in the editor)
    humanize: float = 0.0     # 0..1 subtle timing/level drift, saved with the groove
    probs: dict = field(default_factory=dict)    # role -> {step: chance %}; absent = always
    ornaments: dict = field(default_factory=dict)  # role -> {step: "flam"|"drag"|"roll"}

    def step_seconds(self, bpm: float) -> float:
        return 60.0 / max(1.0, bpm) / max(1, self.steps_per_beat)

    def loop_seconds(self, bpm: float) -> float:
        return self.steps * self.step_seconds(bpm)

    def meter_label(self) -> str:
        return f"{self.beats_per_bar}/{self.beat_unit}"

    def level_of(self, role: str, step: int) -> str | None:
        return self.levels.get(role, {}).get(step)

    def set_level(self, role: str, step: int, level: str | None) -> None:
        if level is None:
            if role in self.levels:
                self.levels[role].pop(step, None)
                if not self.levels[role]:
                    del self.levels[role]
        else:
            self.levels.setdefault(role, {})[step] = level

    def ornament_of(self, role: str, step: int) -> str | None:
        """A hit's ornament ("flam" | "drag" | "roll"), or None for a plain stroke."""
        return self.ornaments.get(role, {}).get(step)

    def set_ornament(self, role: str, step: int, ornament: str | None) -> None:
        if ornament is None:
            if role in self.ornaments:
                self.ornaments[role].pop(step, None)
                if not self.ornaments[role]:
                    del self.ornaments[role]
        else:
            self.ornaments.setdefault(role, {})[step] = ornament

    def chance_of(self, role: str, step: int) -> int | None:
        """A hit's play chance in percent; None means it always plays."""
        return self.probs.get(role, {}).get(step)

    def set_chance(self, role: str, step: int, percent: int | None) -> None:
        """Set a hit's play chance (10..90); None (or 100) makes it always play."""
        if percent is None or not (0 < percent < 100):
            if role in self.probs:
                self.probs[role].pop(step, None)
                if not self.probs[role]:
                    del self.probs[role]
        else:
            self.probs.setdefault(role, {})[step] = int(percent)

    def line_length(self, role: str) -> int:
        """A line's own loop length in steps (defaults to the full pattern length)."""
        return self.lengths.get(role, self.steps)

    def set_line_length(self, role: str, length: int) -> None:
        """Set a line's loop length; equal to the pattern length means 'default'.

        Hits and levels beyond the new length are dropped.
        """
        length = max(1, min(POLY_MAX_LINE, length))
        if length == self.steps:
            self.lengths.pop(role, None)
        else:
            self.lengths[role] = length
        if role in self.hits:
            self.hits[role] = [s for s in self.hits[role] if s < length]
        if role in self.levels:
            self.levels[role] = {s: lv for s, lv in self.levels[role].items() if s < length}
            if not self.levels[role]:
                del self.levels[role]
        if role in self.probs:
            self.probs[role] = {s: c for s, c in self.probs[role].items() if s < length}
            if not self.probs[role]:
                del self.probs[role]
        if role in self.ornaments:
            self.ornaments[role] = {s: o for s, o in self.ornaments[role].items()
                                    if s < length}
            if not self.ornaments[role]:
                del self.ornaments[role]

    def is_polymetric(self) -> bool:
        return any(L != self.steps for L in self.lengths.values())

    def copy(self) -> "Pattern":
        return Pattern(self.name, self.steps, self.steps_per_beat,
                       {r: list(s) for r, s in self.hits.items()},
                       self.beats_per_bar, self.beat_unit, self.bars,
                       {r: dict(m) for r, m in self.levels.items()},
                       dict(self.lengths), self.swing, self.humanize,
                       {r: dict(m) for r, m in self.probs.items()},
                       {r: dict(m) for r, m in self.ornaments.items()})


#: Grid resolutions as (label, steps-per-quarter-note).
GRID_CHOICES = [("Quarter", 1), ("Eighth", 2), ("Triplet", 3), ("Sixteenth", 4)]
BEAT_UNITS = [2, 4, 8, 16]
MAX_STEPS = 64            # keep the step grid navigable
POLY_MAX_LINE = 64       # longest a single polymetric line may be
POLY_MAX_RENDER = 512    # cap the phased (LCM) loop so it stays a sane length


def flatten_polymeter(p: Pattern, render_len: int | None = None) -> Pattern:
    """Expand a polymetric pattern into a plain one by tiling each line over the loop.

    Lines with their own lengths repeat independently; the flattened loop runs for the
    least common multiple of every line length (and the base), so all parts realign —
    capped at POLY_MAX_RENDER whole bars.  A pattern without custom lengths is returned
    unchanged (unless an explicit *render_len* asks for a specific tiling).

    Pass *render_len* to tile to exactly that many steps instead of the LCM — the Song
    Builder uses this to cut polymetric lines off at a section's end so an odd-length
    line never pushes the next section off its count.
    """
    if not p.is_polymetric() and render_len is None:
        return p
    per_bar = max(1, p.steps // max(1, p.bars))
    if render_len is None:
        render_len = p.steps
        for role in p.hits:
            render_len = math.lcm(render_len, p.line_length(role))
        render_len = min(render_len, POLY_MAX_RENDER)
        render_len = max(per_bar, (render_len // per_bar) * per_bar)  # keep whole bars
    else:
        render_len = max(1, render_len)
    hits: dict = {}
    levels: dict = {}
    probs: dict = {}
    ornaments: dict = {}
    for role, steps in p.hits.items():
        length = p.line_length(role)
        base = [s for s in steps if 0 <= s < length]
        line_levels = p.levels.get(role, {})
        line_probs = p.probs.get(role, {})
        line_orns = p.ornaments.get(role, {})
        tiled, tiled_levels, tiled_probs, tiled_orns = [], {}, {}, {}
        for cycle in range(0, render_len, length):
            for s in base:
                pos = cycle + s
                if pos < render_len:
                    tiled.append(pos)
                    if s in line_levels:
                        tiled_levels[pos] = line_levels[s]
                    if s in line_probs:
                        tiled_probs[pos] = line_probs[s]
                    if s in line_orns:
                        tiled_orns[pos] = line_orns[s]
        if tiled:
            hits[role] = sorted(tiled)
            if tiled_levels:
                levels[role] = tiled_levels
            if tiled_probs:
                probs[role] = tiled_probs
            if tiled_orns:
                ornaments[role] = tiled_orns
    return Pattern(p.name, render_len, p.steps_per_beat, hits, p.beats_per_bar,
                   p.beat_unit, max(1, render_len // per_bar), levels,
                   swing=p.swing, humanize=p.humanize, probs=probs,
                   ornaments=ornaments)


def steps_per_bar(beats_per_bar: int, beat_unit: int, grid: int) -> int:
    """Grid steps in one bar of beats/unit at *grid* steps per quarter note."""
    return max(1, round(beats_per_bar * (4.0 / max(1, beat_unit)) * grid))


def blank_pattern(beats_per_bar: int, beat_unit: int, grid: int, bars: int = 1) -> Pattern:
    """An empty pattern for a given time signature, grid, and bar count."""
    total = steps_per_bar(beats_per_bar, beat_unit, grid) * max(1, bars)
    return Pattern(f"{beats_per_bar}/{beat_unit}", total, grid, {},
                   beats_per_bar, beat_unit, bars)


def _p(name: str, hits: dict, beats: int = 4, unit: int = 4, grid: int = 4, bars: int = 1) -> Pattern:
    return Pattern(name, steps_per_bar(beats, unit, grid) * bars, grid, hits, beats, unit, bars)


#: Built-in grooves. 4/4 ones are 16 sixteenth-note steps; odd meters set their own grid.
GENRE_PATTERNS = [
    _p("Rock", {"kick": [0, 8], "snare": [4, 12], "hihat": [0, 2, 4, 6, 8, 10, 12, 14]}),
    _p("Pop", {"kick": [0, 8, 11], "snare": [4, 12], "hihat": [0, 2, 4, 6, 8, 10, 12, 14]}),
    _p("Four on the Floor", {"kick": [0, 4, 8, 12], "clap": [4, 12], "hihat": [2, 6, 10, 14]}),
    _p("Funk", {"kick": [0, 3, 6, 10], "snare": [4, 12], "hihat": list(range(16))}),
    _p("Hip-Hop", {"kick": [0, 6, 10], "snare": [4, 12], "hihat": [0, 2, 4, 6, 8, 10, 12, 14]}),
    _p("Trap", {"kick": [0, 7, 10], "808": [0, 7, 10], "clap": [4, 12],
                "hihat": [0, 2, 3, 4, 6, 8, 10, 11, 12, 14]}),
    _p("Metal", {"kick": [0, 2, 4, 6, 8, 10, 12, 14], "snare": [4, 12], "crash": [0]}),
    _p("Half-Time", {"kick": [0, 10], "snare": [8], "hihat": [0, 2, 4, 6, 8, 10, 12, 14]}),
    # --- odd / prog meters ---
    _p("5/4", {"kick": [0, 10, 16], "snare": [4, 12], "hihat": list(range(0, 20, 2))},
       beats=5, unit=4),
    _p("7/8 (2+2+3)", {"kick": [0, 4], "snare": [2], "hihat": [0, 1, 2, 3, 4, 5, 6]},
       beats=7, unit=8, grid=2),
    _p("6/8", {"kick": [0, 3], "snare": [3], "hihat": [0, 1, 2, 3, 4, 5]},
       beats=6, unit=8, grid=2),
    _p("5/8 (3+2)", {"kick": [0, 3], "snare": [3], "hihat": [0, 1, 2, 3, 4]},
       beats=5, unit=8, grid=2),
    _p("Djent 7/16 (poly)", {"kick": [0, 1, 2, 4, 5], "808": [0, 4], "snare": [3]},
       beats=7, unit=16, grid=4),

    # --- rock & punk ---
    _p("Hard Rock", {"kick": [0, 6, 8, 14], "snare": [4, 12], "hihat": [0, 2, 4, 6, 8, 10, 12, 14]}),
    _p("Punk", {"kick": [0, 8, 10], "snare": [4, 12], "hihat": [0, 2, 4, 6, 8, 10, 12, 14], "crash": [0]}),
    _p("Grunge", {"kick": [0, 8, 11], "snare": [4, 12], "hihat": [0, 4, 8, 12], "crash": [0]}),
    _p("Motorik", {"kick": [0, 4, 8, 12], "snare": [4, 12], "hihat": list(range(16))}),
    _p("Surf", {"kick": [0, 8], "snare": [4, 12], "tom": [2, 6, 10, 14], "hihat": [0, 4, 8, 12]}),
    _p("Ballad", {"kick": [0, 8], "snare": [8], "hihat": [0, 2, 4, 6, 8, 10, 12, 14]}),

    # --- metal (extreme) ---
    _p("Thrash Gallop", {"kick": [0, 2, 3, 4, 6, 7, 8, 10, 11, 12, 14, 15], "snare": [4, 12], "crash": [0]}),
    _p("Blast Beat", {"kick": [0, 2, 4, 6, 8, 10, 12, 14], "snare": [1, 3, 5, 7, 9, 11, 13, 15], "crash": [0]}),
    _p("D-Beat", {"kick": [0, 3, 8, 11], "snare": [4, 12], "hihat": [0, 2, 4, 6, 8, 10, 12, 14], "crash": [0]}),
    _p("Breakdown", {"kick": [0, 3, 6, 8, 11, 14], "snare": [8], "crash": [0, 8]}),
    _p("Doom", {"kick": [0, 8], "snare": [8], "hihat": [0, 4, 8, 12], "crash": [0]}),

    # --- funk, soul, disco ---
    _p("Motown", {"kick": [0, 8], "snare": [4, 12], "clap": [0, 4, 8, 12], "hihat": [0, 2, 4, 6, 8, 10, 12, 14]}),
    _p("Second Line", {"kick": [0, 3, 8, 11], "snare": [4, 6, 12, 14], "hihat": [0, 2, 4, 6, 8, 10, 12, 14]}),
    _p("Boogaloo", {"kick": [0, 3, 6, 10, 11], "snare": [4, 12], "hihat": list(range(16))}),
    _p("Nu-Disco", {"kick": [0, 4, 8, 12], "clap": [4, 12], "openhat": [2, 6, 10, 14], "hihat": [0, 8]}),

    # --- hip-hop, trap, r&b ---
    _p("Boom Bap", {"kick": [0, 3, 8], "snare": [4, 12], "hihat": [0, 2, 4, 6, 8, 10, 12, 14]}),
    _p("Drill", {"kick": [0, 7, 10], "808": [0, 7, 10], "snare": [6, 14], "hihat": [0, 2, 4, 6, 8, 10, 12, 14]}),
    _p("Lo-Fi", {"kick": [0, 10], "snare": [4, 12], "hihat": [0, 4, 8, 12]}),
    _p("R&B", {"kick": [0, 6, 10], "snare": [4, 12], "hihat": list(range(16))}),
    _p("Reggaeton", {"kick": [0, 8], "snare": [3, 7, 11, 14], "hihat": [0, 4, 8, 12]}),

    # --- electronic ---
    _p("House", {"kick": [0, 4, 8, 12], "clap": [4, 12], "openhat": [2, 6, 10, 14], "hihat": [0, 2, 4, 6, 8, 10, 12, 14]}),
    _p("Techno", {"kick": [0, 4, 8, 12], "clap": [4, 12], "hihat": [2, 6, 10, 14], "perc": [3, 11]}),
    _p("Trance", {"kick": [0, 4, 8, 12], "clap": [4, 12], "openhat": [2, 6, 10, 14]}),
    _p("Drum and Bass", {"kick": [0, 10], "snare": [4, 12], "hihat": [0, 2, 4, 6, 8, 10, 12, 14]}),
    _p("Dubstep", {"kick": [0, 6], "snare": [8], "hihat": [0, 4, 8, 12], "openhat": [14]}),
    _p("Breakbeat", {"kick": [0, 6, 10], "snare": [4, 12], "hihat": [0, 2, 4, 6, 8, 10, 12, 14]}),
    _p("UK Garage", {"kick": [0, 6, 10], "snare": [4, 12], "hihat": [2, 6, 10, 14], "openhat": [8]}),
    _p("Trip-Hop", {"kick": [0, 8], "snare": [4, 12], "hihat": [0, 4, 8, 12]}),

    # --- latin & world ---
    _p("Bossa Nova", {"kick": [0, 6, 8, 14], "perc": [0, 3, 6, 10, 13], "hihat": [0, 2, 4, 6, 8, 10, 12, 14]}),
    _p("Samba", {"kick": [0, 3, 4, 7, 8, 11, 12, 15], "snare": [2, 6, 10, 14], "hihat": [0, 2, 4, 6, 8, 10, 12, 14]}),
    _p("Afrobeat", {"kick": [0, 6, 10], "snare": [4, 10, 12], "perc": [2, 5, 8, 13], "hihat": list(range(16))}),
    _p("Reggae One Drop", {"kick": [8], "snare": [8], "hihat": [0, 2, 4, 6, 8, 10, 12, 14]}),
    _p("Ska", {"kick": [0, 8], "snare": [4, 12], "hihat": [2, 6, 10, 14]}),
    _p("Soca", {"kick": [0, 4, 8, 12], "snare": [4, 12], "hihat": [2, 6, 10, 14], "perc": [3, 7, 11, 15]}),

    # --- jazz & traditional (triplet-swing where noted) ---
    _p("Jazz Swing", {"ride": [0, 2, 3, 5, 6, 8, 9, 11], "hihat": [3, 9], "kick": [0, 6]},
       beats=4, unit=4, grid=3),
    _p("Blues Shuffle", {"kick": [0, 6], "snare": [3, 9], "ride": [0, 2, 3, 5, 6, 8, 9, 11]},
       beats=4, unit=4, grid=3),
    _p("Jazz Waltz", {"ride": [0, 2, 3, 5, 6, 8], "hihat": [3], "kick": [0]},
       beats=3, unit=4, grid=3),
    _p("Waltz", {"kick": [0], "snare": [4, 8], "hihat": [0, 2, 4, 6, 8, 10]}, beats=3, unit=4),
    _p("March", {"kick": [0, 4], "snare": [0, 2, 4, 6], "crash": [0]}, beats=2, unit=4),
    _p("Polka", {"kick": [0, 4], "snare": [2, 6], "hihat": [0, 2, 4, 6]}, beats=2, unit=4),
    _p("Gospel 6/8", {"kick": [0, 3], "snare": [3], "hihat": [0, 1, 2, 3, 4, 5]}, beats=6, unit=8, grid=2),
    _p("Country Train", {"kick": [0, 8], "snare": [4, 12], "hihat": list(range(16))}),

    # --- more odd / prog meters ---
    _p("9/8", {"kick": [0, 4], "snare": [2, 6], "hihat": [0, 1, 2, 3, 4, 5, 6, 7, 8]}, beats=9, unit=8, grid=2),
    _p("7/4", {"kick": [0, 4, 8], "snare": [4, 10], "hihat": list(range(14))}, beats=7, unit=4, grid=2),
    _p("11/8 (3+3+3+2)", {"kick": [0, 3, 6], "snare": [9], "hihat": list(range(11))}, beats=11, unit=8, grid=2),
    _p("5/4 Fast", {"kick": [0, 6, 12], "snare": [4, 16], "hihat": list(range(0, 20, 2))}, beats=5, unit=4),
]


def _bake_default_dynamics(p: Pattern) -> Pattern:
    """Give a groove real dynamics out of the box.

    Universal drummer defaults, meter-aware: the kick (and 808) accents each bar's
    downbeat, snares and claps accent hits that land on a metrical beat (the
    backbeats), and hi-hats ghost their off-beat strokes so the pulse breathes.
    Every step remains editable afterwards.
    """
    beat_len = max(1, round(p.steps_per_beat * 4.0 / max(1, p.beat_unit)))
    per_bar = max(1, p.steps // max(1, p.bars))
    for role, steps in p.hits.items():
        for s in steps:
            if role in ("kick", "808") and s % per_bar == 0:
                p.set_level(role, s, LEVEL_ACCENT)
            elif role in ("snare", "clap") and s % beat_len == 0:
                p.set_level(role, s, LEVEL_ACCENT)
            elif role == "hihat" and beat_len > 1 and s % beat_len != 0:
                p.set_level(role, s, LEVEL_GHOST)
    return p


# -- genre feel: swing / humanize / ornaments / chance / polymeter -----------------
#
# These grooves are a REFERENCE library — a starting point that should be *correct* for its
# style — so this table is idiomatic, not a demo reel.  Straight styles stay straight
# (swing 0), programmed styles stay machine-tight (humanize 0), and ornaments are placed
# SPARSELY rather than on every backbeat: a drag on all of 2 and 4 reads as a rudimental
# march, not as jazz.
#
# SWING SCALE — read this before changing a number.  Swing feeds _swung_fraction, where
#   r = 0.5 + 0.25 * swing   (r = the fraction of the beat the first eighth takes)
# so the curve is:
#   0.00 -> 50/50  dead straight
#   0.16 -> 54/46  a light MPC/909 lean
#   0.40 -> 60/40  a medium laid-back shuffle
#   0.67 -> 66/33  a true triplet swing (jazz / blues shuffle)
#   0.80 -> 70/30  a hard shuffle
# It is NOT a scale where 50 means "neutral" — 0 is neutral.
#
# Compound meters (6/8, 9/8, Gospel 6/8) stay at swing 0: their subdivision is already
# triplet-based, so swinging them again would double-swing the feel.


def _feel(swing=0.0, hum=0.10, orn=None, roll=0.0, hat=0, perc=0, poly=None) -> dict:
    # fill_orn / fill_kinds / tom_run / ghost are merged in from _FILL_FEEL below.
    return {"swing": swing, "humanize": hum, "snare_orn": orn,
            "hat_roll": roll, "hat_chance": hat, "perc_chance": perc, "poly": poly,
            "fill_orn": 0.0, "fill_kinds": (), "tom_run": False, "ghost": 0}


GENRE_FEEL: dict[str, dict] = {
    # --- rock & pop: straight, played by arms rather than a grid ---
    "Rock": _feel(hum=0.14),
    "Pop": _feel(hum=0.06, perc=55),          # quantized; only the sweeteners come and go
    "Four on the Floor": _feel(hum=0.05),
    "Half-Time": _feel(hum=0.12, orn="flam"),  # one huge backbeat, flammed for size
    "Hard Rock": _feel(hum=0.12),
    "Punk": _feel(hum=0.08),
    "Grunge": _feel(hum=0.20, orn="flam"),
    "Motorik": _feel(hum=0.04),               # hypnotic *because* it never varies
    "Surf": _feel(hum=0.15),
    "Ballad": _feel(hum=0.18),
    # --- metal: rigidly straight, click-locked ---
    "Metal": _feel(hum=0.08),
    "Thrash Gallop": _feel(hum=0.06),         # a duple 8th+two-16ths figure; swing kills it
    "Blast Beat": _feel(hum=0.04),
    "D-Beat": _feel(hum=0.15),
    "Breakdown": _feel(hum=0.05, orn="flam"),
    "Doom": _feel(hum=0.20),
    # No poly here: the seed is ALREADY a 7/16 bar, so a 7-step kick would equal the whole
    # pattern and phase against nothing.  Afrobeat (12-step perc under 16) is the polymeter
    # showcase instead, where the cycle genuinely runs against the kit.
    "Djent 7/16 (poly)": _feel(hum=0.04),
    # --- funk, soul, disco ---
    "Funk": _feel(swing=0.16, hum=0.16, hat=75, perc=55),
    "Motown": _feel(swing=0.14, hum=0.18, hat=60),
    "Second Line": _feel(swing=0.55, hum=0.24, orn="drag", hat=65, perc=70),
    "Boogaloo": _feel(hum=0.15, hat=55, perc=75),   # straight-8th cha-cha, not a shuffle
    "Nu-Disco": _feel(hum=0.06, perc=50),
    # --- hip-hop, trap, r&b ---
    "Hip-Hop": _feel(swing=0.18, hum=0.12),
    "Trap": _feel(hum=0.0, roll=0.40),        # on-grid; rolls punctuate, they don't dominate
    "Boom Bap": _feel(swing=0.40, hum=0.18),  # the MPC ~60% lean
    "Drill": _feel(hum=0.04, roll=0.50),
    "Lo-Fi": _feel(swing=0.48, hum=0.28),     # deliberately un-quantized, Dilla sway
    "R&B": _feel(swing=0.20, hum=0.15),
    "Trip-Hop": _feel(swing=0.24, hum=0.20),
    "Reggaeton": _feel(swing=0.14, hum=0.08, perc=55),   # dembow leans, it isn't machine-flat
    # --- electronic: programmed, so humanize stays at zero ---
    "House": _feel(swing=0.18, hum=0.06, perc=70),
    "Techno": _feel(hum=0.0, perc=50),
    "Trance": _feel(hum=0.0, perc=45),
    "Drum and Bass": _feel(hum=0.10, hat=70, perc=60),   # feel lives in ghost notes, not swing
    "Dubstep": _feel(hum=0.0, hat=60, perc=50),
    "Breakbeat": _feel(swing=0.28, hum=0.14, hat=65, perc=60),
    "UK Garage": _feel(swing=0.55, hum=0.08, hat=70, perc=65),   # the shuffle IS the genre
    # --- latin & world ---
    "Bossa Nova": _feel(hum=0.14),
    "Samba": _feel(swing=0.20, hum=0.18, perc=80),   # the bateria is timekeeping, not garnish
    "Afrobeat": _feel(swing=0.20, hum=0.20, hat=70, perc=85, poly={"perc": 12}),
    "Reggae One Drop": _feel(hum=0.18),
    "Ska": _feel(swing=0.25, hum=0.18),
    "Soca": _feel(hum=0.10, perc=60),
    # --- jazz & blues: the genuinely swung styles ---
    "Jazz Swing": _feel(swing=0.66, hum=0.20),
    "Blues Shuffle": _feel(swing=0.66, hum=0.16),
    "Jazz Waltz": _feel(swing=0.62, hum=0.20),
    "Gospel 6/8": _feel(hum=0.18, orn="flam", perc=60),   # compound already: no added swing
    "Country Train": _feel(hum=0.14),
    # --- traditional & odd meters: the odd count is the hook; keep them clean ---
    "Waltz": _feel(hum=0.16),
    "March": _feel(hum=0.08, orn="drag"),     # rudimental ruff is authentic here
    "Polka": _feel(hum=0.14),
    "5/4": _feel(hum=0.12, hat=60),
    "7/8 (2+2+3)": _feel(hum=0.12),
    "6/8": _feel(hum=0.16),
    "5/8 (3+2)": _feel(hum=0.14),
    "9/8": _feel(hum=0.14),
    "7/4": _feel(hum=0.12, hat=65, perc=60),
    "11/8 (3+3+3+2)": _feel(hum=0.12),
    "5/4 Fast": _feel(hum=0.10),
}

# -- fills & ghost notes, per genre -------------------------------------------------
#
# (fill_orn %, ornament kinds, tom_run, ghost %) — its own table so a style's fill character
# can be tuned by ear without disturbing its swing/humanize.
#
#   fill_orn  PER-HIT chance that a hit inside a fill gets an ornament. A fill is ~85%
#             dense, so even a rudimental style rarely wants more than ~35 — past that the
#             run turns to mush.
#   tom_run   the fill DESCENDS across the five toms instead of hammering one. Right for kit
#             idioms (rock, metal, prog, R&B); wrong where fills are snare-only (punk,
#             second line, trap, most electronic).
#   ghost     chance of a quiet off-beat snare stroke between the backbeats — the 16th
#             chatter that defines funk and R&B, and is flatly wrong in styles built on
#             space and impact (doom, breakdown, ballad, blast beats, minimal techno).

_FILL_FEEL: dict[str, tuple] = {
    "Rock": (15, ("flam",), True, 10),
    "Pop": (8, ("flam",), True, 5),
    "Four on the Floor": (8, ("flam",), True, 10),
    "Half-Time": (10, ("flam",), True, 5),
    "Hard Rock": (15, ("flam",), True, 5),
    "Punk": (5, ("flam",), False, 0),
    "Grunge": (22, ("flam",), True, 8),
    "Motorik": (0, (), False, 0),
    "Surf": (25, ("flam", "roll"), True, 0),
    "Ballad": (8, ("flam",), True, 0),
    "Metal": (12, ("flam",), True, 5),
    "Thrash Gallop": (8, ("flam",), True, 0),
    "Blast Beat": (10, ("roll",), False, 0),
    "D-Beat": (0, (), False, 0),
    "Breakdown": (0, (), False, 0),
    "Doom": (8, ("flam",), True, 0),
    "Djent 7/16 (poly)": (10, ("roll", "flam"), True, 4),
    "Funk": (18, ("flam", "drag"), True, 70),
    "Motown": (12, ("flam",), True, 35),
    "Second Line": (35, ("flam", "drag", "roll"), False, 75),
    "Boogaloo": (10, ("flam",), True, 45),
    "Nu-Disco": (14, ("roll",), True, 8),
    "Hip-Hop": (10, ("flam", "roll"), False, 20),
    "Trap": (30, ("roll",), False, 0),
    "Boom Bap": (15, ("flam", "drag"), False, 32),
    "Drill": (20, ("roll",), False, 0),
    "Lo-Fi": (8, ("flam",), False, 22),
    "R&B": (15, ("flam", "drag"), True, 35),
    "Trip-Hop": (10, ("roll",), False, 12),
    "Reggaeton": (20, ("roll", "flam"), False, 0),
    "House": (10, ("roll",), False, 5),
    "Techno": (8, ("roll",), False, 0),
    "Trance": (25, ("roll",), False, 0),
    "Drum and Bass": (22, ("roll", "drag"), False, 45),
    "Dubstep": (15, ("roll",), False, 0),
    "Breakbeat": (18, ("flam", "roll"), False, 35),
    "UK Garage": (15, ("roll",), False, 30),
    "Bossa Nova": (0, (), False, 8),
    "Samba": (25, ("drag", "roll"), False, 55),
    "Afrobeat": (15, ("flam", "drag"), True, 50),
    "Reggae One Drop": (10, ("flam",), True, 10),
    "Ska": (25, ("flam", "drag"), False, 15),
    "Soca": (20, ("flam", "roll"), True, 20),
    "Jazz Swing": (30, ("flam", "drag", "roll"), False, 15),
    "Blues Shuffle": (20, ("flam", "drag"), False, 35),
    "Jazz Waltz": (25, ("drag", "roll"), False, 10),
    "Gospel 6/8": (25, ("flam", "roll", "drag"), True, 20),
    "Country Train": (20, ("flam", "roll"), False, 60),
    "Waltz": (10, ("flam", "drag"), False, 8),
    "March": (35, ("flam", "drag", "roll"), False, 0),
    "Polka": (10, ("flam",), False, 0),
    "5/4": (12, ("flam",), True, 15),
    "7/8 (2+2+3)": (15, ("flam", "drag"), True, 12),
    "6/8": (12, ("flam",), True, 10),
    "5/8 (3+2)": (12, ("flam", "drag"), False, 8),
    "9/8": (15, ("flam", "drag"), True, 12),
    "7/4": (12, ("flam",), True, 15),
    "11/8 (3+3+3+2)": (15, ("flam", "drag"), True, 12),
    "5/4 Fast": (8, ("flam",), True, 12),
}

for _g, (_fo, _fk, _tr, _gs) in _FILL_FEEL.items():
    GENRE_FEEL[_g].update(fill_orn=_fo / 100.0, fill_kinds=_fk, tom_run=_tr, ghost=_gs)


_GHOST_MAX_PER_BAR = 3      # keep the chatter a texture, never a second snare part
_ORNAMENT_SPARSITY = 0.30   # share of eligible backbeats that actually get the ornament


def _genre_of(name: str) -> str:
    """The seed genre a library entry came from ("Rock 07 fill" -> "Rock")."""
    n = name[:-5] if name.endswith(" fill") else name
    head, _, tail = n.rpartition(" ")
    return head if head and tail.isdigit() else n


def _bake_genre_feel(p: Pattern) -> Pattern:
    """Apply the genre's idiomatic feel: swing/humanize, sparse ornaments, play-chance on
    decoration only, and polymeter where the style calls for it.

    Deterministic — seeded from the pattern's name — so a given groove sounds the same on
    every launch, exactly like the seeded variations it sits alongside.  Never touches the
    backbone (downbeat kick, backbeat snare): that is what makes a groove a groove.
    """
    prof = GENRE_FEEL.get(_genre_of(p.name))
    if prof is None:
        return p
    p.swing = prof["swing"]
    p.humanize = prof["humanize"]
    rng = random.Random(f"feel:{p.name}")
    beat_len = max(1, round(p.steps_per_beat * 4.0 / max(1, p.beat_unit)))

    if prof["snare_orn"]:      # sparse, so it reads as a player's choice, not a machine
        for s in p.hits.get("snare", []):
            if s % beat_len == 0 and rng.random() < _ORNAMENT_SPARSITY:
                p.set_ornament("snare", s, prof["snare_orn"])

    if prof["hat_roll"]:       # ratchets punctuate the off-beats (trap / drill)
        for s in p.hits.get("hihat", []):
            if s % beat_len != 0 and rng.random() < prof["hat_roll"]:
                p.set_ornament("hihat", s, "roll")

    if prof["hat_chance"] and beat_len > 1:   # off-beat hats only — the pulse stays solid
        for s in p.hits.get("hihat", []):
            if s % beat_len != 0:
                p.set_chance("hihat", s, min(90, prof["hat_chance"]))

    if prof["perc_chance"]:
        for role in ("perc", "tambourine", "shaker"):
            for s in p.hits.get(role, []):
                p.set_chance(role, s, min(90, prof["perc_chance"]))

    if prof["ghost"] and beat_len > 1:
        # The 16th-note chatter that makes funk and R&B breathe: quiet strokes BETWEEN the
        # backbeats. Capped per bar so it stays a texture rather than becoming a second
        # snare part, and it never lands on a beat — the backbeat has to stay solid.
        snare = set(p.hits.get("snare", []))
        per_bar = max(1, p.steps // max(1, p.bars))
        added_in_bar: dict[int, int] = {}
        for s in range(p.steps):
            if s % beat_len == 0 or s in snare:
                continue                      # on the beat, or already playing
            bar = s // per_bar
            if added_in_bar.get(bar, 0) >= _GHOST_MAX_PER_BAR:
                continue
            if rng.random() * 100 < prof["ghost"]:
                snare.add(s)
                p.set_level("snare", s, LEVEL_GHOST)
                added_in_bar[bar] = added_in_bar.get(bar, 0) + 1
        if snare:
            p.hits["snare"] = sorted(snare)

    if prof["poly"]:
        for role, length in prof["poly"].items():
            if role in p.hits:
                p.set_line_length(role, length)
    return p


GENRE_PATTERNS = [_bake_genre_feel(_bake_default_dynamics(p)) for p in GENRE_PATTERNS]


# -- the pattern library (500 grooves: hand-made genre bases + seeded variations) --

def _metrical_beat_len(p: Pattern) -> int:
    """Grid steps in one metrical beat of the pattern (e.g. an eighth in 7/8)."""
    return max(1, round(p.steps_per_beat * 4.0 / max(1, p.beat_unit)))


def _two_bars(base: Pattern, name: str) -> Pattern:
    """The base groove repeated over two bars (so a fill can live in bar 2)."""
    per = base.steps
    hits = {r: sorted({s + b * per for b in range(2) for s in steps})
            for r, steps in base.hits.items()}
    levels = {r: {s + b * per: lv for b in range(2) for s, lv in m.items()}
              for r, m in base.levels.items()}
    # Carry the groove's feel across — a variation of a shuffle is still a shuffle.
    return Pattern(name, per * 2, base.steps_per_beat, hits,
                   base.beats_per_bar, base.beat_unit, 2, levels,
                   swing=base.swing, humanize=base.humanize)


def _generate_variation(base: Pattern, seed: int, with_fill: bool, name: str) -> Pattern:
    """A deterministic musical variation of *base* (same seed -> same groove forever)."""
    rng = random.Random(seed)
    p = _two_bars(base, name)
    total = p.steps
    beat_len = _metrical_beat_len(p)

    # Hat movement: drop or add a few hat steps so the ride pattern breathes.
    hat = set(p.hits.get("hihat", []))
    if hat:
        for _ in range(rng.randint(1, 3)):
            s = rng.randrange(total)
            if s in hat and rng.random() < 0.5:
                hat.discard(s)
            else:
                hat.add(s)
        p.hits["hihat"] = sorted(hat)
    if rng.random() < 0.45:  # occasional open hat, replacing the closed one there
        s = rng.randrange(total)
        p.hits.setdefault("openhat", [])
        p.hits["openhat"] = sorted(set(p.hits["openhat"]) | {s})
        if "hihat" in p.hits:
            p.hits["hihat"] = [x for x in p.hits["hihat"] if x != s]

    # Kick syncopation: up to two extra kicks, avoiding the backbeat snares.
    snare = set(p.hits.get("snare", []))
    kicks = set(p.hits.get("kick", []))
    for _ in range(rng.randint(0, 2)):
        s = rng.randrange(total)
        if s not in snare:
            kicks.add(s)
    p.hits["kick"] = sorted(kicks)
    if "808" in base.hits:  # trap-style: the sub shadows the kick
        p.hits["808"] = sorted(kicks)

    if rng.random() < 0.4:  # light percussion sprinkle
        p.hits["perc"] = sorted(rng.sample(range(total), k=rng.randint(1, 3)))

    if with_fill:
        # Fill: clear the last beat(s) of bar 2 and run snare/tom through it, with a
        # crash landing on the loop restart. Sized from the meter, so it always fits.
        fill_beats = rng.choice((1, 2)) if p.beats_per_bar >= 4 else 1
        start = total - min(total, beat_len * fill_beats)
        for role in ("snare", "hihat", "openhat", "clap", "tom", "perc"):
            if role in p.hits:
                p.hits[role] = [s for s in p.hits[role] if s < start]
        prof = GENRE_FEEL.get(_genre_of(name), {})
        # A kit player turns a fill DOWN the toms; a snare-only idiom (punk, second line,
        # trap, most electronic) keeps it on the snare. TOM_ROLES is already high-to-low.
        tom_run = prof.get("tom_run") and len(TOM_ROLES) > 1
        span = max(1, total - start)
        first = True
        touched = set()
        for s in range(start, total):
            if rng.random() < 0.85:
                if tom_run:
                    # Descend across the toms as the fill progresses; the snare still leads.
                    step = (s - start) / span
                    role = "snare" if (first or rng.random() < 0.25) else \
                        TOM_ROLES[min(len(TOM_ROLES) - 1, int(step * len(TOM_ROLES)))]
                else:
                    role = rng.choice(("snare", "tom", "tom", "snare"))
                p.hits.setdefault(role, []).append(s)
                touched.add(role)
                if first:  # the fill announces itself, then breathes
                    p.set_level(role, s, LEVEL_ACCENT)
                    first = False
                elif rng.random() < 0.3:
                    p.set_level(role, s, LEVEL_GHOST)
                # Ornament the fill the way the style would — drummers grace their fills.
                kinds = prof.get("fill_kinds") or ()
                if kinds and rng.random() < prof.get("fill_orn", 0.0):
                    p.set_ornament(role, s, rng.choice(kinds))
        for role in touched | {"snare", "tom"}:
            if role in p.hits:
                p.hits[role] = sorted(set(p.hits[role]))
        p.hits["crash"] = sorted(set(p.hits.get("crash", [])) | {0})

    p.hits = {r: s for r, s in p.hits.items() if s}  # drop emptied roles
    # Dynamics only where hits remain (mutations may have moved or removed steps).
    p.levels = {r: {s: lv for s, lv in m.items() if s in set(p.hits.get(r, []))}
                for r, m in p.levels.items()}
    p.levels = {r: m for r, m in p.levels.items() if m}
    # The variation moved, added and removed steps, so re-derive dynamics and the genre's
    # feel over the FINAL hit set — otherwise new hits land flat and the groove loses the
    # swing/chance/ornaments its style calls for.
    _bake_default_dynamics(p)
    _bake_genre_feel(p)
    return p


def build_pattern_library(total: int = 500) -> list[Pattern]:
    """The full groove list: the hand-made bases plus seeded variations up to *total*.

    Seeds are fixed, so the library is identical every launch — pattern 137 today is
    pattern 137 forever.  Dozens of genre bases (rock, metal, funk, hip-hop, electronic,
    latin, jazz, odd meters, ...) each become a category, with dynamics baked in.
    """
    library = [p.copy() for p in GENRE_PATTERNS]
    counters: dict[str, int] = {}
    i = 0
    while len(library) < total:
        base = GENRE_PATTERNS[i % len(GENRE_PATTERNS)]
        n = counters.get(base.name, 2)  # the base itself is number 1
        counters[base.name] = n + 1
        with_fill = i % 2 == 1
        name = f"{base.name} {n:02d}" + (" fill" if with_fill else "")
        library.append(_generate_variation(base, seed=1000 + i, with_fill=with_fill, name=name))
        i += 1
    return library


#: Built once at import; deterministic (see build_pattern_library).
# -- showcase grooves ---------------------------------------------------------------
#
# The 500 above are a REFERENCE library: a rock beat is straight because rock IS straight,
# so most of them deliberately don't show off.  These few exist for the opposite reason —
# each is built to demonstrate one capability you can hear within a bar or two.  Reach for
# them when you want to hear what the sequencer does, or to show someone else.
#
# They are APPENDED to the library rather than added to GENRE_PATTERNS on purpose: the
# generator cycles through the seeds, so adding one there would renumber every variation and
# break the "pattern 137 is pattern 137 forever" guarantee.

SHOWCASE_CATEGORY = "Showcase"


def _showcase() -> list[Pattern]:
    out: list[Pattern] = []

    # 1. Polymeter — a 7-step kick cycling under a 4/4 bar, phasing and realigning.
    poly = _p("Showcase Polymeter (7 against 4)",
              {"kick": [0, 3, 5], "snare": [4, 12],
               "hihat": [0, 2, 4, 6, 8, 10, 12, 14], "crash": [0]})
    poly.set_line_length("kick", 7)      # 7 against 16 -> realigns after seven bars
    out.append(poly)

    # 2. Chance — the decoration re-rolls every pass, so the loop never repeats exactly.
    chance = _p("Showcase Chance (varies every pass)",
                {"kick": [0, 8], "snare": [4, 12], "hihat": list(range(16)),
                 "perc": [2, 6, 10, 14], "openhat": [7, 15]})
    for s in range(16):
        if s % 4 != 0:                   # backbone stays solid; only decoration rolls
            chance.set_chance("hihat", s, 65)
    for s in (2, 6, 10, 14):
        chance.set_chance("perc", s, 50)
    for s in (7, 15):
        chance.set_chance("openhat", s, 40)
    out.append(chance)

    # 3. Ornaments — all three graces in one bar: flam, drag (ruff) and roll (ratchet).
    orn = _p("Showcase Ornaments (flam, drag, roll)",
             {"kick": [0, 8], "snare": [4, 12],
              "hihat": [0, 2, 4, 6, 8, 10, 12, 14], "tom1": [14]})
    orn.set_ornament("snare", 4, "flam")
    orn.set_ornament("snare", 12, "drag")
    orn.set_ornament("hihat", 6, "roll")
    orn.set_ornament("hihat", 14, "roll")
    orn.set_ornament("tom1", 14, "flam")
    out.append(orn)

    # 4. Full kit — a tom run across the whole standard kit, so every part is audible.
    full = _p("Showcase Full Kit (a tom run)",
              {"kick": [0, 8], "snare": [4], "tom1": [10], "tom2": [11], "tom": [12],
               "tom4": [13], "tom5": [14], "crash": [0], "ride": [2, 6], "ridebell": [15],
               "cowbell": [3], "tambourine": [4, 12], "shaker": [1, 5, 9, 13],
               "openhat": [7]})
    out.append(full)

    # 5. Dynamics — the same hat line as accent / normal / ghost, so the range is obvious.
    dyn = _p("Showcase Dynamics (accents and ghosts)",
             {"kick": [0, 10], "snare": [4, 12], "hihat": list(range(16))})
    for s in range(16):
        if s % 4 == 0:
            dyn.set_level("hihat", s, LEVEL_ACCENT)
        elif s % 2 == 1:
            dyn.set_level("hihat", s, LEVEL_GHOST)
    dyn.set_level("snare", 4, LEVEL_ACCENT)
    dyn.set_level("snare", 12, LEVEL_ACCENT)
    for s in (2, 6, 14):                 # ghosted snare chatter between the backbeats
        dyn.hits.setdefault("snare", [])
        dyn.hits["snare"] = sorted(set(dyn.hits["snare"]) | {s})
        dyn.set_level("snare", s, LEVEL_GHOST)
    out.append(dyn)

    # 6. Swing — a hard shuffle, next to the straight grooves, to hear what swing does.
    swing = _p("Showcase Swing (hard shuffle)",
               {"kick": [0, 8], "snare": [4, 12], "hihat": [0, 2, 4, 6, 8, 10, 12, 14]})
    swing.swing = 0.66                   # a true triplet shuffle (see the SWING SCALE note)
    swing.humanize = 0.16
    out.append(swing)

    for p in out:
        _bake_default_dynamics(p)
    return out


SHOWCASE_PATTERNS = _showcase()

# The generated 500 stay exactly as they are; the showcase grooves ride along after them.
PATTERN_LIBRARY = build_pattern_library() + SHOWCASE_PATTERNS


def retime_pattern(p: Pattern, beats: int, unit: int, grid: int, bars: int) -> Pattern:
    """Return *p* fitted to a new meter/bar count — non-destructively.

    A pure bar-count change (same grid, not polymetric) **tiles** the existing bars
    across the new count: growing repeats the music, shrinking keeps the first bars.

    Any other change (grid resolution, beats, or unit) **remaps every hit by its
    musical time position** so the groove stays in time and no parts are dropped —
    changing sixteenths to triplets keeps the backbeat on the backbeat, not scattered.
    (Incommensurate grids like triplets vs sixteenths can't round-trip bit-perfectly,
    but the feel is preserved.)  Per-line polymeter is reset, being grid-relative.
    """
    per_bar = steps_per_bar(beats, unit, grid)
    bars = max(1, bars)
    total = per_bar * bars
    old_bars = max(1, p.bars)
    old_per_bar = max(1, p.steps // old_bars)
    name = f"{beats}/{unit}"
    levels: dict = {}
    probs: dict = {}
    ornaments: dict = {}

    if per_bar == old_per_bar and grid == p.steps_per_beat and not p.is_polymetric():
        hits: dict = {}
        for role, steps in p.hits.items():
            out = set()
            src_levels = p.levels.get(role, {})
            src_probs = p.probs.get(role, {})
            src_orns = p.ornaments.get(role, {})
            new_levels: dict = {}
            new_probs: dict = {}
            new_orns: dict = {}
            for b in range(bars):
                src = b % old_bars
                lo, hi = src * old_per_bar, (src + 1) * old_per_bar
                for s in steps:
                    if lo <= s < hi:
                        dst = s - lo + b * per_bar
                        out.add(dst)
                        if s in src_levels:
                            new_levels[dst] = src_levels[s]
                        if s in src_probs:
                            new_probs[dst] = src_probs[s]
                        if s in src_orns:
                            new_orns[dst] = src_orns[s]
            if out:
                hits[role] = sorted(out)
                if new_levels:
                    levels[role] = new_levels
                if new_probs:
                    probs[role] = new_probs
                if new_orns:
                    ornaments[role] = new_orns
        return Pattern(name, total, grid, hits, beats, unit, bars, levels,
                       swing=p.swing, humanize=p.humanize, probs=probs,
                       ornaments=ornaments)

    # Time-preserving remap: place each hit at the same fraction of the loop.
    old_total = max(1, p.steps)
    hits = {}
    for role, steps in p.hits.items():
        src_levels = p.levels.get(role, {})
        src_probs = p.probs.get(role, {})
        src_orns = p.ornaments.get(role, {})
        chosen: dict = {}  # new step -> level (None if the hit here had no dynamic)
        new_probs = {}
        new_orns = {}
        for s in steps:
            ns = max(0, min(total - 1, round(s / old_total * total)))
            if src_levels.get(s) is not None or ns not in chosen:
                chosen[ns] = src_levels.get(s, chosen.get(ns))
            if s in src_probs:
                new_probs[ns] = src_probs[s]
            if s in src_orns:
                new_orns[ns] = src_orns[s]
        if chosen:
            hits[role] = sorted(chosen)
            role_levels = {ns: lv for ns, lv in chosen.items() if lv}
            if role_levels:
                levels[role] = role_levels
            if new_probs:
                probs[role] = new_probs
            if new_orns:
                ornaments[role] = new_orns
    return Pattern(name, total, grid, hits, beats, unit, bars, levels,
                   swing=p.swing, humanize=p.humanize, probs=probs,
                   ornaments=ornaments)


def expand_with_fill(p: Pattern, total_bars: int) -> Pattern:
    """Stretch a groove to *total_bars* with its fill (last bar) landing only at the end.

    For a jam: 'fill every 12 bars' plays the plain groove for 11 bars, then the
    pattern's final bar (where library fills live) as the turnaround.  One-bar
    patterns simply repeat.  Returns *p* unchanged when no stretch is needed.
    """
    if total_bars <= p.bars:
        return p
    per_bar = max(1, p.steps // max(1, p.bars))
    if p.bars >= 2:
        body = list(range(p.bars - 1))
        order = [body[i % len(body)] for i in range(total_bars - 1)] + [p.bars - 1]
    else:
        order = [0] * total_bars
    hits: dict = {}
    levels: dict = {}
    probs: dict = {}
    ornaments: dict = {}
    for role, steps in p.hits.items():
        out = []
        src_levels = p.levels.get(role, {})
        src_probs = p.probs.get(role, {})
        src_orns = p.ornaments.get(role, {})
        new_levels: dict = {}
        new_probs: dict = {}
        new_orns: dict = {}
        for dst, src in enumerate(order):
            if role == "crash" and src == 0 and dst != 0:
                # A first-bar crash marks the post-fill downbeat (the loop restart);
                # tiling it onto every body bar would crash constantly.
                continue
            lo, hi = src * per_bar, (src + 1) * per_bar
            for s in steps:
                if lo <= s < hi:
                    d = s - lo + dst * per_bar
                    out.append(d)
                    if s in src_levels:
                        new_levels[d] = src_levels[s]
                    if s in src_probs:
                        new_probs[d] = src_probs[s]
                    if s in src_orns:
                        new_orns[d] = src_orns[s]
        if out:
            hits[role] = sorted(out)
            if new_levels:
                levels[role] = new_levels
            if new_probs:
                probs[role] = new_probs
            if new_orns:
                ornaments[role] = new_orns
    return Pattern(p.name, per_bar * total_bars, p.steps_per_beat, hits,
                   p.beats_per_bar, p.beat_unit, total_bars, levels,
                   swing=p.swing, humanize=p.humanize, probs=probs,
                   ornaments=ornaments)


# -- improvised fills (rule-bound randomness, Diablo-dungeon style) ----------------

_FILL_CLEAR_ROLES = ("snare", "rimshot", "hihat", "pedalhat", "openhat", "clap",
                     "tom1", "tom2", "tom", "tom4", "tom5", "perc", "tambourine", "shaker")


def _generate_fill_zone(rng: "random.Random", beat_len: int, per_bar: int,
                        fill_amount: float = 0.0):
    """One generated fill: (length in grid steps, hits keyed by offset-in-zone).

    Length varies — usually one or two beats, occasionally a whole bar — and the
    run is a snare/tom mix with varying density and an occasional kick pickup, so
    consecutive fills rarely feel the same.  Everything is measured in grid steps,
    so it lands on the meter whatever the time signature.

    *fill_amount* (0..1, default 0) leans the fill longer and busier: higher values
    bias the length toward a full bar and raise the hit density.  At 0 it makes the
    exact same rng calls as before, so existing seeded callers are unaffected.
    """
    big = per_bar // max(1, beat_len)
    fill_len = min(per_bar, beat_len * rng.choice((1, 1, 1, 2, 2, big)))
    if fill_amount > 0.0:
        # A second, independent roll leaning toward the bigger end; blend toward it
        # as fill_amount rises, so 1.0 lands close to a full bar most of the time.
        longer = min(per_bar, beat_len * rng.choice((2, big, big)))
        fill_len = int(round(fill_len + (longer - fill_len) * fill_amount))
    fill_len = max(1, fill_len)
    hits: dict = {}
    levels: dict = {}
    density = rng.uniform(0.6 + 0.2 * fill_amount, min(1.0, 0.95 + 0.05 * fill_amount))
    first = True
    for s in range(fill_len):
        if rng.random() < density:
            role = rng.choice(("snare", "tom", "tom", "snare", "perc"))
            hits.setdefault(role, []).append(s)
            if first:  # the fill announces itself
                levels.setdefault(role, {})[s] = LEVEL_ACCENT
                first = False
            elif rng.random() < 0.3:  # ghosted in-between strokes breathe
                levels.setdefault(role, {})[s] = LEVEL_GHOST
    if fill_len >= beat_len and rng.random() < 0.4:  # kick pickup into the fill
        hits.setdefault("kick", []).append(0)
    return fill_len, hits, levels


def improvised_loop(p: Pattern, cycle_bars: int, cycles: int = 4,
                    seed: int | None = None, fill_amount: float = 0.0) -> Pattern:
    """A long loop of *cycles* passes of the groove, each ending in a *different*
    generated fill — programmatic improvisation.

    Each cycle is *cycle_bars* long: the plain groove (the pattern minus its own
    final-bar fill, if it has one) fills the cycle, then a freshly generated fill
    is carved into the cycle's last beats, with a crash on each cycle's downbeat.
    With ``seed=None`` every render improvises anew.

    *fill_amount* (0..1, default 0) is passed to every cycle's fill: higher values
    make the fills longer and busier (see :func:`_generate_fill_zone`).
    """
    rng = random.Random(seed)
    per_bar = max(1, p.steps // max(1, p.bars))
    beat_len = _metrical_beat_len(p)
    body_bars = list(range(p.bars - 1)) if p.bars >= 2 else [0]
    cycle_bars = max(1, cycle_bars)
    total_bars = cycle_bars * max(1, cycles)
    total_steps = per_bar * total_bars
    hits: dict = {}
    levels: dict = {}
    probs: dict = {}
    ornaments: dict = {}

    def copy_bar(src: int, dst: int) -> None:
        lo, hi = src * per_bar, (src + 1) * per_bar
        for role, steps in p.hits.items():
            if role == "crash":
                continue  # crashes are re-placed on cycle downbeats below
            src_levels = p.levels.get(role, {})
            src_probs = p.probs.get(role, {})
            src_orns = p.ornaments.get(role, {})
            for s in steps:
                if lo <= s < hi:
                    d = s - lo + dst * per_bar
                    hits.setdefault(role, []).append(d)
                    if s in src_levels:
                        levels.setdefault(role, {})[d] = src_levels[s]
                    if s in src_probs:
                        probs.setdefault(role, {})[d] = src_probs[s]
                    if s in src_orns:
                        ornaments.setdefault(role, {})[d] = src_orns[s]

    for c in range(max(1, cycles)):
        base = c * cycle_bars
        for b in range(cycle_bars):
            copy_bar(body_bars[b % len(body_bars)], base + b)
        fill_len, fill_hits, fill_levels = _generate_fill_zone(rng, beat_len, per_bar,
                                                               fill_amount)
        zone_start = (base + cycle_bars) * per_bar - fill_len
        for role in _FILL_CLEAR_ROLES:
            if role in hits:
                hits[role] = [s for s in hits[role] if not (zone_start <= s)
                              or s >= zone_start + fill_len]
            if role in levels:
                levels[role] = {s: lv for s, lv in levels[role].items()
                                if s < zone_start or s >= zone_start + fill_len}
            if role in probs:
                probs[role] = {s: c for s, c in probs[role].items()
                               if s < zone_start or s >= zone_start + fill_len}
            if role in ornaments:
                ornaments[role] = {s: o for s, o in ornaments[role].items()
                                   if s < zone_start or s >= zone_start + fill_len}
        for role, offsets in fill_hits.items():
            hits.setdefault(role, []).extend(zone_start + o for o in offsets)
        for role, offset_levels in fill_levels.items():
            for off, lv in offset_levels.items():
                levels.setdefault(role, {})[zone_start + off] = lv
        # Crash lands on the downbeat after each fill (wrapping at the loop end).
        hits.setdefault("crash", []).append(((base + cycle_bars) * per_bar) % total_steps)

    hits = {r: sorted(set(s)) for r, s in hits.items() if s}
    levels = {r: m for r, m in levels.items() if m and r in hits}
    probs = {r: m for r, m in probs.items() if m and r in hits}
    ornaments = {r: m for r, m in ornaments.items() if m and r in hits}
    return Pattern(f"{p.name} improv", total_steps, p.steps_per_beat, hits,
                   p.beats_per_bar, p.beat_unit, total_bars, levels,
                   swing=p.swing, humanize=p.humanize, probs=probs,
                   ornaments=ornaments)


def _clear_span(p: Pattern, roles, start: int, end: int) -> None:
    """Drop every hit (and its dynamics/chance/ornament) of *roles* in ``[start, end)``."""
    for role in roles:
        if role in p.hits:
            p.hits[role] = [s for s in p.hits[role] if not (start <= s < end)]
            if not p.hits[role]:
                del p.hits[role]
        for store in (p.levels, p.probs, p.ornaments):
            if role in store:
                store[role] = {s: v for s, v in store[role].items()
                               if not (start <= s < end)}
                if not store[role]:
                    del store[role]


def fill_span(p: Pattern, start: int, end: int, complexity: float = 0.5,
              spill: bool = False, seed: int | None = None) -> Pattern:
    """Carve an improvised drum fill across steps ``[start, end)`` of *p*, in place.

    The melodic parts (snares, toms, hats, perc) in the span are cleared and replaced with
    a **descending tom-and-snare run** drawn from the full kit — Tom 1 down to the floor
    tom as the fill progresses — with the density set by *complexity* (0..1).  The first
    stroke is accented so the fill announces itself.

    Unless *spill* is set, the fill **resolves on the bar**: the final beat of the span is
    left open and a crash (with a kick) lands on the downbeat at ``end`` (wrapping to the
    loop start if the span runs to the pattern's end).  With *spill* on, the run stays busy
    right through the span and no resolving crash is placed — the fill spills past the end.

    A *seed* makes the fill deterministic; ``None`` improvises fresh each call.  Returns *p*.
    """
    steps = p.steps
    start = max(0, min(steps, int(start)))
    end = max(start, min(steps, int(end)))
    if end <= start:
        return p
    rng = random.Random(seed)
    complexity = max(0.0, min(1.0, complexity))
    beat_len = _metrical_beat_len(p)
    _clear_span(p, _FILL_CLEAR_ROLES + ("crash", "crash2", "splash", "china", "ride",
                                        "ridebell"), start, end)
    run_end = end if spill else max(start + 1, end - beat_len)   # reserve a beat to resolve
    density = 0.5 + 0.45 * complexity
    toms = TOM_ROLES                                            # high -> low
    span = max(1, run_end - start)
    first = True
    for i, s in enumerate(range(start, run_end)):
        if rng.random() >= density:
            continue
        # Descend the toms across the span; sprinkle snare so it isn't only toms.
        if rng.random() < 0.4:
            role = "snare"
        else:
            role = toms[min(len(toms) - 1, int(i / span * len(toms)))]
        if s >= p.line_length(role):     # never place past a polymetric line's own length
            continue                     # (it would be silently dropped on save)
        p.hits.setdefault(role, []).append(s)
        if first:
            p.set_level(role, s, LEVEL_ACCENT)
            first = False
        elif rng.random() < 0.25 + 0.25 * complexity:
            p.set_level(role, s, LEVEL_GHOST)
    if not spill:
        crash_at = end if end < steps else 0
        if crash_at < p.line_length("crash"):
            p.hits.setdefault("crash", []).append(crash_at)
            p.set_level("crash", crash_at, LEVEL_ACCENT)
        if crash_at < p.line_length("kick"):
            p.hits.setdefault("kick", []).append(crash_at)
    for role in list(p.hits):
        p.hits[role] = sorted(set(p.hits[role]))
    return p


# -- rendering (the compensator) -------------------------------------------------

def _mix_wrap(buf: "np.ndarray", v: "np.ndarray", offset: int) -> None:
    """Add voice *v* into *buf* at *offset*, wrapping the tail to the start (seamless)."""
    length = len(buf)
    if length == 0 or len(v) == 0:
        return
    v = v[:length]                       # never longer than one loop
    offset %= length
    end = offset + len(v)
    if end <= length:
        buf[offset:end] += v
    else:
        first = length - offset
        buf[offset:] += v[:first]
        buf[: len(v) - first] += v[first:]


_HUMANIZE_MAX_JITTER_S = 0.014  # +/- 14 ms of timing drift at humanize = 1.0
_HUMANIZE_MAX_GAIN = 0.28       # +/- 28% of level drift at humanize = 1.0

#: Ornaments — drummer rudiments around a single hit, sequencer-style.
ORNAMENT_FLAM = "flam"   # one soft grace stroke just before the hit
ORNAMENT_DRAG = "drag"   # two grace strokes (a ruff) leading into the hit
ORNAMENT_ROLL = "roll"   # the hit rebounds across its step (a ratchet/buzz)
ORNAMENTS = [ORNAMENT_FLAM, ORNAMENT_DRAG, ORNAMENT_ROLL]
_GRACE_GAIN = 0.42       # grace strokes whisper next to the main stroke
_FLAM_S = 0.028          # flam grace lead time (fixed ms — drummer physics, not grid)
_DRAG_S = 0.024          # drag grace spacing
_ROLL_GAINS = (0.7, 0.5, 0.35)  # rebound decay across the step (main stroke = 1.0)


def _swung_fraction(frac: float, swing: float) -> float:
    """Map a within-beat position (0..1) to its swung position.

    *swing* 0 is straight; higher delays the second eighth of each beat (and the
    sixteenths ride along), reaching a triplet shuffle near 1.
    """
    if swing <= 0.0:
        return frac
    r = 0.5 + 0.25 * min(1.0, swing)   # first eighth takes fraction r of the beat
    if frac < 0.5:
        return 2 * frac * r
    return r + 2 * (frac - 0.5) * (1 - r)


def resample_pitch(voice, semitones: float):
    """Pitch-shift a voice by *semitones* (equal temperament) by resampling.

    Higher pitch plays back faster, so the sample also gets slightly shorter — which
    is natural for drums (a lower tom rings a touch longer, a higher one tightens up).
    Uses the windowed-sinc core so pitched-down 808s/toms keep their highs instead of
    gaining linear-interp haze.  Zero semitones is a no-op.
    """
    if np is None or voice is None or not semitones or len(voice) == 0:
        return voice
    ratio = 2.0 ** (semitones / 12.0)
    new_len = max(1, int(round(len(voice) / ratio)))
    return _sinc_read(voice, ratio, new_len)


def scale_voice(voice, gain: float):
    """Scale a voice's amplitude by a linear *gain* (per-line mix balance)."""
    if np is None or voice is None or gain == 1.0 or len(voice) == 0:
        return voice
    return (voice * gain).astype(np.float32)


def _click_array(freq: float, rate: int, ms: float = 35.0, volume: float = 0.6):
    """A short percussive click: a fast-decaying sine with a soft attack (no pop)."""
    n = max(1, int(rate * ms / 1000.0))
    t = np.arange(n) / rate
    env = np.exp(-t / ((ms / 1000.0) / 4.0))
    attack = max(1, int(rate * 0.001))
    env[:attack] *= np.linspace(0.0, 1.0, attack, dtype=np.float64)
    return (np.sin(2 * np.pi * freq * t) * env * volume).astype(np.float32)


def tempo_ramp(start: int, target: int, step: int) -> list[int]:
    """The tempo-trainer plateaus from *start* up to *target* (inclusive), by *step* BPM.

    Always at least ``[start]``; never overshoots the target (the last jump is clamped).
    Used for the finite ramp and to describe the climb ("90 to 160, 15 steps").
    """
    start = max(1, int(start))
    step = max(1, int(step))
    target = max(start, int(target))
    seq = [start]
    while seq[-1] < target:
        seq.append(min(target, seq[-1] + step))
    return seq


def render_count_in(beats: int, beat_unit: int, bpm: float, rate: int = RATE):
    """One bar of clicks for a count-in as a (float32 samples, duration_seconds) pair.

    Clicks the bar's beats at the current tempo, accenting beat one, so a player can
    come in on the downbeat.  Returned as raw samples so it plays on a one-shot channel.
    """
    if np is None:
        return None, 0.0
    beats = max(1, beats)
    beat_dur = 60.0 / max(1.0, bpm) * (4.0 / max(1, beat_unit))  # a beat of the meter's unit
    total = beats * beat_dur
    buf = np.zeros(max(1, int(round(total * rate))), dtype=np.float32)
    for b in range(beats):
        click = _click_array(1600.0 if b == 0 else 1100.0, rate)  # accent the downbeat
        off = int(round(b * beat_dur * rate))
        end = min(len(buf), off + len(click))
        buf[off:end] += click[: end - off]
    return buf, total


def _truncate_voice(v, max_len: int, rate: int):
    """A copy of *v* cut to *max_len* samples with a short fade so it doesn't click.

    Used for choke groups: a ringing voice is cut when the next hit in its group fires.
    """
    if max_len >= len(v):
        return v
    fade = min(max_len, max(1, int(0.004 * rate)))
    out = v[:max_len].copy()
    out[-fade:] *= np.linspace(1.0, 0.0, fade, dtype=np.float32)
    return out


def _choke_cutoffs(pattern: Pattern, choke_groups: dict, step_s: float, rate: int) -> dict:
    """Map each choked hit to how many samples it may ring — the gap (in samples) to
    the next hit anywhere in its choke group, wrapping around the loop's end."""
    steps_by_group: dict = defaultdict(set)
    for role, steps_on in pattern.hits.items():
        g = choke_groups.get(role)
        if g:
            steps_by_group[g].update(s for s in steps_on if 0 <= s < pattern.steps)
    cutoffs: dict = {}
    for g, sset in steps_by_group.items():
        ordered = sorted(sset)
        for i, s in enumerate(ordered):
            nxt = ordered[i + 1] if i + 1 < len(ordered) else ordered[0] + pattern.steps
            cutoffs[(g, s)] = max(1, int(round((nxt - s) * step_s * rate)))
    return cutoffs


def _mix_pattern(pattern: Pattern, kit: DrumKit, bpm: float, rate: int,
                 swing: float, humanize: float, seed: int | None,
                 choke_groups: dict | None):
    """Mix one loop of *pattern* into a float32 buffer (no normalize/volume yet)."""
    pattern = flatten_polymeter(pattern)  # per-line lengths -> one tiled loop
    step_s = pattern.step_seconds(bpm)
    beat_dur = 60.0 / max(1.0, bpm)      # a quarter note, the swing reference
    spb = max(1, pattern.steps_per_beat)
    length = max(1, int(round(pattern.steps * step_s * rate)))
    buf = np.zeros(length, dtype=np.float32)
    rng = random.Random(seed) if humanize > 0 else None
    # Per-step probability ("sometimes" hits): its own RNG stream, so seeded humanize
    # renders stay reproducible and chance-free patterns stay byte-identical.
    roll = random.Random(None if seed is None else seed ^ 0x9E3779B9) if pattern.probs else None
    group_of = choke_groups or {}
    cutoffs = _choke_cutoffs(pattern, group_of, step_s, rate) if group_of else {}

    def hit_offset(step: int) -> int:
        if swing <= 0.0 and rng is None:
            return int(round(step * step_s * rate))
        beat_i, within = divmod(step, spb)
        t = (beat_i + _swung_fraction(within / spb, swing)) * beat_dur
        if rng is not None:
            t += rng.uniform(-1.0, 1.0) * humanize * _HUMANIZE_MAX_JITTER_S
        return int(round(max(0.0, t) * rate))

    for role, steps_on in pattern.hits.items():
        voice = kit.voice(role)
        if voice is None or len(voice) == 0:
            continue
        role_levels = pattern.levels.get(role, {})
        role_probs = pattern.probs.get(role, {})
        role_orns = pattern.ornaments.get(role, {})
        group = group_of.get(role)
        scaled = {None: voice}
        for step in steps_on:
            if not 0 <= step < pattern.steps:
                continue
            chance = role_probs.get(step) if roll is not None else None
            if chance is not None and roll.random() * 100.0 >= chance:
                continue                 # this pass, the hit sits out
            gain = _LEVEL_GAIN.get(role_levels.get(step), 1.0)
            if rng is not None:
                v = voice * (gain * (1.0 + rng.uniform(-1.0, 1.0) * humanize * _HUMANIZE_MAX_GAIN))
            else:
                level = role_levels.get(step)
                if level not in scaled:
                    scaled[level] = voice * gain
                v = scaled[level]
            if group:                    # cut the ring at the next hit in this group
                cut = cutoffs.get((group, step))
                if cut is not None:
                    v = _truncate_voice(v, cut, rate)
            off = hit_offset(step)
            orn = role_orns.get(step)
            if orn == ORNAMENT_FLAM:     # grace offsets are negative; _mix_wrap wraps
                _mix_wrap(buf, v * _GRACE_GAIN, off - int(_FLAM_S * rate))
            elif orn == ORNAMENT_DRAG:
                _mix_wrap(buf, v * _GRACE_GAIN, off - int(2 * _DRAG_S * rate))
                _mix_wrap(buf, v * _GRACE_GAIN, off - int(_DRAG_S * rate))
            elif orn == ORNAMENT_ROLL:   # rebounds subdivide the step: tempo-aware
                sub = max(1, int(round(step_s * rate / 4)))
                for k, g in enumerate(_ROLL_GAINS, start=1):
                    _mix_wrap(buf, v * g, off + k * sub)
            _mix_wrap(buf, v, off)
    return buf


_SOFT_KNEE = 0.8      # level above which peaks are squashed instead of the whole mix ducked


def _soft_limit(buf: "np.ndarray") -> "np.ndarray":
    """Tame over-unity peaks without pulling the whole mix down.

    Straight peak-normalize meant ONE hot transient (a crash landing on a kick) dropped
    the loudness of the entire loop.  Instead, the body of the signal (|x| <= knee) passes
    untouched and only the excursion above the knee is squashed through tanh, which maps
    any peak into [-1, 1].  Memoryless, deterministic, transparent below the knee.
    """
    peak = float(np.max(np.abs(buf))) if len(buf) else 0.0
    if peak <= 1.0:
        return buf
    a = np.abs(buf)
    over = a > _SOFT_KNEE
    out = buf.astype(np.float32).copy()
    span = 1.0 - _SOFT_KNEE
    out[over] = np.sign(buf[over]) * (
        _SOFT_KNEE + span * np.tanh((a[over] - _SOFT_KNEE) / span))
    return out


def _buf_to_wav(buf, volume: float, rate: int) -> bytes:
    """Soft-limit, apply *volume*, dither, and wrap a float32 buffer as a 16-bit WAV.

    Accepts mono (1D) or stereo (frames, 2).  The TPDF dither is seeded, so the same
    buffer always produces the same bytes — several tests (and WAV-export reproducibility)
    rely on renders of identical content being identical.
    """
    buf = np.asarray(buf, dtype=np.float32)
    buf = _soft_limit(buf)
    buf = buf * max(0.0, min(1.0, volume))
    scaled = np.clip(buf, -1.0, 1.0) * 32767.0
    if len(scaled) and float(np.max(np.abs(scaled))) > 0.0:
        rng = np.random.default_rng(24601)                    # fixed seed: determinism
        scaled = scaled + (rng.random(scaled.shape, dtype=np.float32)
                           - rng.random(scaled.shape, dtype=np.float32))  # TPDF, +-1 LSB
    # Never dither pure digital silence — volume 0 must stay absolutely silent.
    pcm = np.clip(np.rint(scaled), -32768, 32767).astype("<i2")
    out = io.BytesIO()
    w = wave.open(out, "wb")
    w.setnchannels(1 if pcm.ndim == 1 else pcm.shape[1])
    w.setsampwidth(2)
    w.setframerate(rate)
    w.writeframes(np.ascontiguousarray(pcm).tobytes())   # C order interleaves L R L R
    w.close()
    return out.getvalue()


def render_loop(pattern: Pattern, kit: DrumKit, bpm: float, rate: int = RATE,
                volume: float = 1.0, swing: float | None = None,
                humanize: float | None = None,
                seed: int | None = None, choke_groups: dict | None = None,
                passes: int | None = None) -> bytes:
    """Pre-mix one loop of *pattern* played on *kit* at *bpm* into a 16-bit mono WAV.

    *volume* (0..1) scales the finished mix.  *swing* and *humanize* default to the
    pattern's own saved feel (``pattern.swing`` / ``pattern.humanize``) — a groove
    carries its own shuffle and looseness; pass a float to override for this render.
    *swing* (0..1) delays off-beats for a shuffle feel; *humanize* (0..1) adds subtle
    per-hit timing and level drift so a looped groove doesn't sound stamped out.
    *choke_groups* maps a role to a group id; within a group a new hit cuts the previous
    one's ring (an open hat closed by the hat).

    A pattern with **chance steps** (``pattern.probs``) is mixed *passes* times (default
    4) with fresh rolls each pass and the passes concatenated — a looping WAV repeats
    its buffer verbatim, so the variation has to be baked into the loop itself.
    Chance-free patterns render a single pass, byte-identical to before.
    """
    if np is None:
        raise RuntimeError("numpy is required for the drum looper")
    sw = pattern.swing if swing is None else swing
    hm = pattern.humanize if humanize is None else humanize
    n = passes if passes and passes > 0 else (4 if pattern.probs else 1)
    if n == 1:
        buf = _mix_pattern(pattern, kit, bpm, rate, sw, hm, seed, choke_groups)
    else:
        buf = np.concatenate([
            _mix_pattern(pattern, kit, bpm, rate, sw, hm,
                         None if seed is None else seed + i, choke_groups)
            for i in range(n)])
    return _buf_to_wav(buf, volume, rate)


def _auto_hat_choke(pattern: Pattern) -> dict | None:
    """A default choke group for a groove that plays both hats (closed cuts open)."""
    if "hihat" in pattern.hits and "openhat" in pattern.hits:
        return {"hihat": 1, "openhat": 1}
    return None


def render_song(sections, rate: int = RATE, volume: float = 1.0,
                swing: float | None = None, humanize: float | None = None,
                contain_polymeter: bool = True) -> bytes:
    """Render a song — ordered ``(pattern, repeats, bpm, kit)`` sections — end to end.

    Each section is mixed **at its own tempo, kit, and feel** (each groove's saved
    ``swing``/``humanize``), tiled *repeats* times; the sections are concatenated into one
    continuous 16-bit mono WAV (gapless, no timers), then peak-limited and volume-scaled
    together so levels stay even across sections.  Sections may differ in meter, tempo, kit,
    feel and length; hats auto-choke per section.  Pass *swing*/*humanize* to force one feel
    across the whole song instead of per-section.  A song plays through once.

    *contain_polymeter* (default on) keeps a polymetric section exactly as long as its
    pattern's nominal length times its repeats: odd-length lines cycle continuously
    through the whole section and are cut off at its end, so the next section always
    starts on its own count.  Turn it off to let each repeat run the full realignment
    (LCM) loop instead — the pre-containment behavior, where an extended line pushes
    everything after it.
    """
    buf = render_song_buffer(sections, rate, swing, humanize, contain_polymeter)
    return _buf_to_wav(buf, volume, rate)


def render_song_buffer(sections, rate: int = RATE, swing: float | None = None,
                       humanize: float | None = None, contain_polymeter: bool = True):
    """The raw float32 mix of a song (before peak-limit/volume) — see :func:`render_song`
    for the semantics.  Exposed so callers can slice it (e.g. play from a cursor position)."""
    if np is None:
        raise RuntimeError("numpy is required for the drum looper")
    parts = []
    for pattern, repeats, bpm, kit in sections:
        sw = pattern.swing if swing is None else swing
        hm = pattern.humanize if humanize is None else humanize
        # Repeats may be fractional in halves ("extend the verse by half a loop"):
        # whole passes then a truncated tail pass.
        reps = max(0.5, round(float(repeats) * 2) / 2)
        whole, frac = int(reps), reps - int(reps)

        if contain_polymeter and pattern.is_polymetric():
            # One continuous performance the exact nominal length of the section:
            # lines keep cycling across repeats (the polymeter phrasing carries
            # through the section) and stop dead at the section boundary.
            flat = flatten_polymeter(pattern,
                                     render_len=math.ceil(pattern.steps * reps))
            buf = _mix_pattern(flat, kit, bpm, rate, sw, hm, None,
                               _auto_hat_choke(pattern))
            exact = int(round(pattern.loop_seconds(bpm) * reps * rate))
            parts.append(buf[: max(1, exact)])
            continue

        def mix():
            return _mix_pattern(pattern, kit, bpm, rate, sw, hm, None,
                                _auto_hat_choke(pattern))
        if pattern.probs:                # chance steps: fresh rolls every repeat
            parts.extend(mix() for _ in range(whole))
        elif whole:
            buf = mix()
            parts.extend([buf] * whole)
        if frac:
            tail = mix()
            parts.append(tail[: max(1, int(round(len(tail) * frac)))])
    return np.concatenate(parts) if parts else np.zeros(1, dtype=np.float32)


def section_seconds(pattern: Pattern, repeats, bpm: float,
                    contain_polymeter: bool = True) -> float:
    """One section's playing time.  Contained (default), a polymetric section lasts
    exactly its nominal length times its repeats; uncontained, each repeat runs the
    full realignment (LCM) loop — matching :func:`render_song` either way."""
    reps = max(0.5, round(float(repeats) * 2) / 2)
    p = pattern if contain_polymeter else flatten_polymeter(pattern)
    return p.loop_seconds(bpm) * reps


def song_seconds(sections, contain_polymeter: bool = True) -> float:
    """Total playing time of ``(pattern, repeats, bpm, kit)`` sections (each at its
    tempo; repeats may be fractional in halves)."""
    return sum(section_seconds(p, r, bpm, contain_polymeter)
               for p, r, bpm, _kit in sections)


# -- playback --------------------------------------------------------------------

class DrumLoopPlayer:
    """Loops a rendered WAV through the speakers; re-render and call :meth:`play` to change it."""

    def __init__(self) -> None:
        self._ok = winsound is not None
        self._path: str | None = None
        self.playing = False
        if winsound is not None:
            fd, self._path = tempfile.mkstemp(prefix="firehawk_loop_", suffix=".wav")
            os.close(fd)

    @property
    def available(self) -> bool:
        return self._ok

    def play(self, wav_bytes: bytes, loop: bool = True) -> None:
        """Play *wav_bytes*.  Looped by default (a groove); pass ``loop=False`` to play it
        once (a song, which has an ending — and Windows' SND_LOOP is unreliable on the long
        WAV a whole song produces)."""
        if winsound is None or self._path is None:
            return
        try:
            with open(self._path, "wb") as f:
                f.write(wav_bytes)
            flags = winsound.SND_FILENAME | winsound.SND_ASYNC
            if loop:
                flags |= winsound.SND_LOOP
            winsound.PlaySound(self._path, flags)
            self.playing = True
        except Exception:  # noqa: BLE001
            self._ok = False

    def stop(self) -> None:
        if winsound is not None:
            try:
                winsound.PlaySound(None, 0)
            except Exception:  # noqa: BLE001
                pass
        self.playing = False

    def dispose(self) -> None:
        self.stop()
        if self._path:
            try:
                os.remove(self._path)
            except OSError:
                pass
            self._path = None
