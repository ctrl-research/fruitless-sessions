"""A small deterministic synthesizer: notes -> float32 audio.

No SoundFont, no downloads, bit-reproducible from the note list. Timbres are
additive with a simple envelope, one preset per role. The MIDI file is also
written so a DAW can re-voice a take; this synth exists so a bundle's audio
can be rebuilt from the take alone.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from fruitless.conductor.mapper import Note

SR = 44100


@dataclass(frozen=True)
class Preset:
    harmonics: tuple[float, ...]     # relative amplitudes of partials 1..n
    attack: float                    # seconds
    decay: float                     # seconds to fall to sustain
    sustain: float                   # 0..1
    release: float                   # seconds
    vibrato_hz: float = 0.0
    vibrato_depth: float = 0.0       # semitones
    breath: float = 0.0              # noise mix 0..1


PRESETS = {
    # reedy: strong odd partials, slow vibrato, a little breath noise
    "sax": Preset((1.0, 0.55, 0.7, 0.3, 0.35, 0.15, 0.12, 0.05), 0.035, 0.12, 0.75, 0.12, 5.2, 0.12, 0.06),
    # plucked: bright start, fast decay, little sustain
    "bass": Preset((1.0, 0.5, 0.25, 0.12, 0.06), 0.005, 0.35, 0.25, 0.08),
    # struck: many partials, medium decay
    "piano": Preset((1.0, 0.6, 0.35, 0.25, 0.15, 0.1, 0.06, 0.04), 0.004, 0.6, 0.2, 0.15),
}


def midi_to_hz(m: float) -> float:
    return 440.0 * 2.0 ** ((m - 69) / 12.0)


def render_note(n: Note, preset: Preset, rng: np.random.Generator) -> tuple[int, np.ndarray]:
    """(start sample, mono samples) for one note including its release tail."""
    dur = n.dur + preset.release
    t = np.arange(int(dur * SR)) / SR
    # envelope
    env = np.ones_like(t) * preset.sustain
    a = t < preset.attack
    env[a] = t[a] / preset.attack
    d = (t >= preset.attack) & (t < preset.attack + preset.decay)
    env[d] = 1.0 + (preset.sustain - 1.0) * (t[d] - preset.attack) / preset.decay
    r = t >= n.dur
    env[r] = preset.sustain * np.exp(-(t[r] - n.dur) / max(1e-3, preset.release / 3))
    # pitch with vibrato
    f0 = midi_to_hz(n.midi)
    if preset.vibrato_hz:
        vib = preset.vibrato_depth * np.sin(2 * np.pi * preset.vibrato_hz * t) * np.minimum(1.0, t / 0.25)
        f = f0 * 2.0 ** (vib / 12.0)
        phase = 2 * np.pi * np.cumsum(f) / SR
    else:
        phase = 2 * np.pi * f0 * t
    sig = np.zeros_like(t)
    for k, amp in enumerate(preset.harmonics, start=1):
        if f0 * k > SR / 2:
            break
        sig += amp * np.sin(k * phase)
    sig /= max(1e-6, sum(preset.harmonics))
    if preset.breath:
        sig = (1 - preset.breath) * sig + preset.breath * rng.standard_normal(t.size) * 0.3
    vel = (n.vel / 127.0) ** 1.5
    return round(n.t * SR), (sig * env * vel).astype(np.float32)


def render(notes: list[Note], role: str, duration_s: float, seed: int = 0) -> np.ndarray:
    preset = PRESETS.get(role, PRESETS["piano"])
    rng = np.random.default_rng(seed)
    out = np.zeros(int((duration_s + 1.0) * SR), dtype=np.float32)
    for n in notes:
        s, samples = render_note(n, preset, rng)
        e = min(out.size, s + samples.size)
        if e > s:
            out[s:e] += samples[: e - s]
    return out


def mix(tracks: dict[str, np.ndarray], gains: dict[str, float] | None = None) -> np.ndarray:
    gains = gains or {}
    n = max(t.size for t in tracks.values())
    out = np.zeros(n, dtype=np.float32)
    for role, t in tracks.items():
        out[: t.size] += t * gains.get(role, 1.0)
    peak = float(np.abs(out).max()) if out.size else 0.0
    if peak > 0.0:
        out *= 0.89 / max(peak, 0.89)   # normalise only if clipping
    return out


def write_wav(path: Path, audio: np.ndarray, sr: int = SR) -> None:
    import wave
    pcm = np.clip(audio, -1, 1)
    pcm = (pcm * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())


def encode(wav: Path, out_stem: Path) -> Path | None:
    """Encode the WAV for the page with ffmpeg: Opus in .webm when available, else AAC in .m4a.
    Returns the file written, or None when ffmpeg or both encoders are missing."""
    attempts = (("libopus", out_stem.with_suffix(".webm"), ["-b:a", "96k"]),
                ("aac", out_stem.with_suffix(".m4a"), ["-b:a", "128k"]))
    for codec, path, extra in attempts:
        try:
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), "-c:a", codec, *extra,
                            str(path)], check=True)
            return path
        except FileNotFoundError:
            return None
        except subprocess.CalledProcessError:
            continue
    return None
