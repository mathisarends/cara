# Earcon Implementation Plan

Wire the generated earcon set (`sounds/*.mp3`) into the voice assistant so Cara
plays short audio cues at the right lifecycle moments.

**Guiding principle (hard requirement):** every earcon plays through the **same
`AudioPlayer` instance** that the assistant uses for its spoken answers, so
sounds and speech always come out of the **same output device** and are seen by
the **same echo canceller**. This is the central design constraint and drives
most decisions below.

---

## 1. Background: how the audio path actually works today

Read these before touching anything — the plan depends on these concrete facts.

| Fact | Where | Consequence for earcons |
| --- | --- | --- |
| `WavAudioPlayer.play` decodes its input with `wave.open(...)` — it only accepts **WAV** bytes. | `cara/audio/player.py:37` | Earcons must be delivered as WAV, not MP3. |
| TTS is synthesized as `TextToSpeechFormat.WAV` and fed straight to the player. | `cara/speech/streaming.py:166` | The speech path is already WAV end-to-end; earcons should match. |
| The player forwards every rendered chunk to an optional `EchoCanceller.analyze_render(...)`. | `cara/audio/player.py:55` | If earcons play through the same player, AEC automatically knows about them and can cancel them from the mic. |
| `WebRtcEchoCanceller._to_mono_int16` raises unless `sample_width == 2`, but resamples any rate and down-mixes any channel count. | `cara/audio/echo.py:91`, `:96`, `:99` | Earcon WAV **must be 16-bit PCM**. Sample rate / channel count are free. |
| The assistant builds `player` as a local variable and passes it only to `StreamingTextToSpeech`; it is **not** retained on `self`. | `cara/audio/…` used in `cara/assistant.py:64`–`79` | To reuse the player for earcons, the assistant must keep a reference (`self._player`). |
| `EventBus.dispatch` awaits **all** handlers via `asyncio.gather` before returning. | `cara/events/bus.py:48` | A handler that `await`s playback would **block** the dispatcher (and thus the core loop) for the whole sound. Side-effect earcons must *not* await playback. |
| `HueListener` is a pure reactive side-effect listener subscribed to `StateChanged`/`SessionStarted`. | `cara/listener/hue_listener.py` | Good template for the *side-effect* earcons — but the earcon device is the assistant's own audio output, which is private, so ownership differs (see §4). |
| `SonosAudioPlayer.play` uploads the clip over HTTP and **blocks until the speaker starts and finishes** (poll loop, up to 10 s start timeout). | `cara/audio/sonos.py:135`, `:187` | An earcon over Sonos has multi-second latency. Relevant to the wake earcon (see §7 caveats). |
| The event model has `SessionStarted`, `SessionEnded`, `TurnStarted`, `StateChanged`, `Transcribed`, `AnswerGenerated`, `Interrupted`. There is **no** success/failure event. | `cara/events/views.py` | Per `CLAUDE.md` ("do not introduce new event types unless explicitly requested"), success/error earcons have no trigger and are **not** wired now (see §6). |
| `cara/listener/sound_listener.py` exists but is **empty**. | — | This is the intended home for the side-effect earcon listener. |

---

## 2. Orchestration vs. side-effect: the core split

There are two fundamentally different kinds of earcon, and they must be wired
differently:

- **Wake = orchestration.** The wake tone is a turn-taking signal ("go ahead,
  I'm listening"). The microphone must open **only after** the tone has fully
  played, otherwise the earcon bleeds into the recording and the VAD in
  `record_until_silence` can misfire. This ordering guarantee is the whole
  point, so the wake earcon is **awaited inline in the core loop**, *before* the
  first recording. It is **not** a passive event listener.

- **Interrupt / sleep = side-effects.** These react to lifecycle events and must
  **not** gate anything downstream (e.g. after an interrupt we want to re-open
  the mic immediately, not wait for a sound). They are **fire-and-forget**:
  scheduled as background tasks so `EventBus.dispatch` returns instantly.

`success` / `error` / `listening` are generated and ready but have **no clean
trigger today** — see §6.

---

## 3. Asset pipeline: MP3 → 16-bit PCM WAV

The chosen earcons are already committed as MP3 (`sounds/wake.mp3`, etc.). Do
**not** regenerate them from the API — ElevenLabs is stochastic and regeneration
would produce different sounds. Instead **transcode the existing MP3s to WAV
once** and commit the WAV files as the runtime assets.

### Runtime assets
- Runtime loads `sounds/<name>.wav` (16-bit PCM). Keep the `.mp3` files as the
  human-auditionable source (or delete them — optional, out of scope).
- Required WAV encoding: **`pcm_s16le`** (16-bit signed little-endian). Sample
  rate and channels are free; 44.1 kHz stereo (matching the MP3 source) is fine
  because both the player and the AEC adapt to the header.

### Conversion tool
Add a `--to-wav` mode to `scripts/generate_sounds.py` that transcodes the
canonical set's existing `sounds/<name>.mp3` → `sounds/<name>.wav` **without
calling the API**. Use ffmpeg — it is already available on this machine via the
`imageio-ffmpeg` package (bundled binary, `imageio_ffmpeg.get_ffmpeg_exe()`) and
also on `PATH`. Prefer the bundled binary so the step is self-contained:

```
ffmpeg -y -i sounds/wake.mp3 -ac 2 -ar 44100 -c:a pcm_s16le sounds/wake.wav
```

ffmpeg is a **build/dev-time** tool only; the committed WAV assets mean the
runtime gains **zero** new dependencies. Do not add `imageio-ffmpeg` to the
runtime dependency set.

> **Optional future enhancement (not now):** the generator could request
> `SoundEffectFormat.PCM_44100` from ElevenLabs and wrap the raw PCM in a WAV
> header (via the stdlib `wave` module) to emit WAV directly. This only helps
> *future* earcons; it cannot be used to re-encode the already-chosen sounds
> without changing them.

### Sanity check after conversion
Every WAV must satisfy: `wave.open(path).getsampwidth() == 2`. A test enforces
this (see §9).

---

## 4. New component: `EarconPlayer`

A small behavior class (not a dataclass — it owns behavior) that maps a logical
earcon to its WAV bytes and plays it through the shared `AudioPlayer`. This is
the single choke point that guarantees "same device".

**File:** `cara/audio/earcons.py`

```python
import asyncio
import logging
from enum import StrEnum
from pathlib import Path

from cara.audio.ports import AudioPlayer

logger = logging.getLogger(__name__)

_DEFAULT_SOUNDS_DIR = Path(__file__).resolve().parent.parent.parent / "sounds"


class Earcon(StrEnum):
    WAKE = "wake"
    INTERRUPT = "interrupt"
    LISTENING = "listening"
    SUCCESS = "success"
    ERROR = "error"
    SLEEP = "sleep"


class EarconPlayer:
    def __init__(self, player: AudioPlayer, *, sounds_dir: Path | None = None) -> None:
        self._player = player
        self._sounds_dir = sounds_dir or _DEFAULT_SOUNDS_DIR
        self._cache: dict[Earcon, bytes] = {}
        self._background: set[asyncio.Task[None]] = set()

    async def play(self, earcon: Earcon, *, cancel: asyncio.Event | None = None) -> None:
        """Play to completion. Use for orchestrated cues (the wake tone)."""
        await self._player.play(self._load(earcon), cancel=cancel)

    def play_soon(self, earcon: Earcon) -> None:
        """Fire-and-forget. Use for side-effect cues so the caller never blocks."""
        task = asyncio.create_task(self._play_safely(earcon))
        self._background.add(task)
        task.add_done_callback(self._background.discard)

    async def _play_safely(self, earcon: Earcon) -> None:
        try:
            await self.play(earcon)
        except Exception:
            logger.exception("Failed to play earcon %s", earcon)

    def _load(self, earcon: Earcon) -> bytes:
        cached = self._cache.get(earcon)
        if cached is None:
            cached = (self._sounds_dir / f"{earcon}.wav").read_bytes()
            self._cache[earcon] = cached
        return cached
```

Notes:
- `play` (awaited) is for the wake tone; `play_soon` (background task, with a
  strong reference kept in `self._background` so it isn't garbage-collected, and
  its own exception logging) is for side-effects.
- Bytes are cached after first read; the six WAVs are tiny.
- The `_DEFAULT_SOUNDS_DIR` is repo-relative (`<repo>/sounds`). Acceptable while
  the project runs from source. If the package is ever installed as a wheel,
  switch to `importlib.resources` and ship the WAVs as package data — out of
  scope now, note it as a follow-up.

**Package export** (`cara/audio/__init__.py`): add `Earcon` and `EarconPlayer`
to the curated re-exports and `__all__`, using explicit relative imports
(`from .earcons import Earcon, EarconPlayer`), consistent with the existing file.

---

## 5. Side-effect listener: fill `sound_listener.py`

Mirror `HueListener`'s subscription style, but the handlers **schedule** playback
and return immediately (never `await` a full sound), so they don't block
`dispatch`.

**Ownership differs from every other listener.** `ConsoleListener` and
`HueListener` are wired **externally** in `main.py` (they drive external devices
— the console, a Hue bridge). `SoundListener` is the exception: it is
instantiated **inside `VoiceAssistant`** (see §7a), never in `main.py`. Reason:
it must be bound to the assistant's private, AEC-aware `EarconPlayer`/`AudioPlayer`
so sounds share the speech output device (the core requirement of this plan).
Exposing the player publicly just to let `main.py` construct the listener would
leak private state and let a caller wire a *different* device — exactly what we
want to prevent. So `SoundListener` lives in the `cara/listener` package for
symmetry, but the assistant owns its lifecycle.

**File:** `cara/listener/sound_listener.py`

```python
from cara.audio.earcons import Earcon, EarconPlayer
from cara.events import EventBus, Interrupted, SessionEnded


class SoundListener:
    """Plays fire-and-forget earcons in reaction to assistant lifecycle events."""

    def __init__(self, event_bus: EventBus, earcons: EarconPlayer) -> None:
        self._earcons = earcons
        event_bus.subscribe(Interrupted, self._on_interrupted)
        event_bus.subscribe(SessionEnded, self._on_session_ended)

    async def _on_interrupted(self, event: Interrupted) -> None:
        self._earcons.play_soon(Earcon.INTERRUPT)

    async def _on_session_ended(self, event: SessionEnded) -> None:
        self._earcons.play_soon(Earcon.SLEEP)
```

Export it from `cara/listener/__init__.py` alongside `ConsoleListener` and
`HueListener`.

---

## 6. Which earcons get wired now — and which don't

| Earcon | Trigger | Mechanism | Status |
| --- | --- | --- | --- |
| `wake` | Session begins (wake word detected) | **Awaited inline** in `VoiceAssistant._run`, after `SessionStarted`, before the first record | **Wire now** |
| `interrupt` | `Interrupted` event | `SoundListener` → `play_soon` | **Wire now** |
| `sleep` | `SessionEnded` event | `SoundListener` → `play_soon` | **Wire now** |
| `listening` | — | Would map to `StateChanged(LISTENING)`, but that fires on **every** turn and after every barge-in, and the wake tone already signals "ready". Redundant. | **Asset only, not wired** |
| `success` | — | No success event exists. `AnswerGenerated` fires on *every* answer, so it is not a success cue. | **Asset only, not wired** |
| `error` | — | No error/failure event exists. | **Asset only, not wired** |

`CLAUDE.md` forbids inventing new event types unprompted, so `success` / `error`
stay unwired. If the user later wants them, the clean path is: dispatch a
lifecycle signal at the relevant point (e.g. a failure in `_run`, or a tool
outcome) and add a `SoundListener` handler that calls
`play_soon(Earcon.SUCCESS/ERROR)`. Document this; do not implement speculatively.

---

## 7. Assistant wiring

**File:** `cara/assistant.py`

### 7a. Retain the player and build the earcon stack (`__init__`)
The existing block (`cara/assistant.py:64`–`79`) creates `player` locally. Change
it to keep the reference and construct the earcon stack from that **same**
instance:

```python
        self._recorder = recorder or MicrophoneRecorder()
        self._player = player or WavAudioPlayer()          # keep the reference
        self._stt = stt or OpenAISpeechToText(api_key)
        ...
        self._speech_stream = StreamingTextToSpeech(
            tts=tts,
            player=self._player,                            # same instance
            voice=self._speech_settings.tts_voice,
            instructions=self._speech_settings.tts_voice_instructions,
        )
        ...
        self._earcons = EarconPlayer(self._player)
        self._sound_listener = SoundListener(self._event_bus, self._earcons)
```

- Reuse the exact `player` object for both TTS and earcons — this is what
  fulfils the same-device requirement. If a caller injects a `SonosAudioPlayer`,
  both speech and earcons go to Sonos automatically.
- The `SoundListener` is constructed **internally** (not in `main.py`) on
  purpose: it must be bound to the assistant's private, AEC-aware player, and we
  don't want to expose the player publicly (`CLAUDE.md`: keep attributes private,
  expose only intended API). Keeping a reference in `self._sound_listener` also
  prevents it from being collected. (The `EventBus` already holds the bound
  handler references, but the explicit attribute documents ownership.)

### 7b. Play the wake tone as orchestration (`_run`)
In `cara/assistant.py:119`–`122`, after dispatching `SessionStarted` and before
the `while True` loop:

```python
    async def _run(self) -> None:
        follow_up = False
        pending_audio: bytes | None = None
        await self._event_bus.dispatch(SessionStarted())
        await self._earcons.play(Earcon.WAKE)          # play to completion, THEN listen
        try:
            while True:
                ...
```

- Because this is `await`ed, the first `_record` (and thus the mic opening) only
  happens after the tone finishes — the required ordering.
- Ordering with other listeners is intentional: `SessionStarted` handlers (e.g.
  Hue turning the room on) run first, then the wake tone, then recording.
- Do **not** move this into `_record` or key it off `StateChanged(LISTENING)`:
  `LISTENING` recurs every turn and after every barge-in, which would replay the
  wake tone mid-session.

### 7c. Imports
Add to the existing `cara.audio` / `cara.listener` imports:
`from cara.audio import Earcon, EarconPlayer` and
`from cara.listener import SoundListener` (or import `SoundListener` from its
module if `cara.listener` importing the assistant would create a cycle — check;
if so, import `from cara.listener.sound_listener import SoundListener`).

> **Cycle check:** `cara/listener/__init__.py` currently imports `hue_listener`,
> which imports `hueify` (external) — no assistant import. `SoundListener`
> imports only `cara.audio.earcons` and `cara.events`. Importing `SoundListener`
> into `assistant.py` is fine, but confirm no import cycle arises via
> `cara/listener/__init__.py`. If in doubt, import the class directly from
> `cara.listener.sound_listener`.

---

## 8. Caveats and edge cases (call these out in the PR)

1. **16-bit is mandatory.** If a WAV is not `pcm_s16le` and the assistant runs
   with the default `WebRtcEchoCanceller`, `analyze_render` raises
   `"AEC render reference must use 16-bit PCM"` (`echo.py:91`) mid-playback.
   The §9 asset test guards this.
2. **Sonos wake-tone latency.** `SonosAudioPlayer.play` blocks until the speaker
   starts and stops (seconds). Awaiting the wake tone inline therefore adds
   seconds before the mic opens on Sonos. Options to document (pick one; keep it
   simple): (a) accept it, (b) give `VoiceAssistant` an `enable_wake_earcon:
   bool = True` flag and skip the inline `play` when disabled, or (c) make
   `EarconPlayer` optional/injectable and pass `None` for Sonos setups. Default
   local (`WavAudioPlayer`) usage is unaffected and fast.
3. **Keep the wake tone short.** There is no pre-roll mic buffer while the tone
   plays (the wake-word listener pauses its own stream on detection,
   `wakeword/listener.py:89`, and the recorder is a separate stream). A long tone
   = a long dead window where fast talkers get clipped. `wake.mp3` is ~1.3 s;
   consider trimming to ~0.4–0.6 s (re-run the generator with a shorter
   `duration_seconds`, re-pick, then re-convert to WAV). Optional but recommended.
4. **Interrupt earcon during barge-in.** When `Interrupted` fires, the recorder
   is already capturing (`BargeInCapture`). Playing the interrupt tone through
   the **same** AEC-aware player means AEC cancels it from the barge-in
   recording — another reason the same-player rule matters. `play_soon` (not
   awaited) ensures we don't delay re-opening the mic.
5. **Concurrent `play` calls.** `WavAudioPlayer` opens a fresh PyAudio stream per
   call, so a background earcon and TTS can briefly coexist (two OS-mixed output
   streams). This only realistically happens around barge-in teardown and is
   acceptable for a short cue. `EarconPlayer` does **not** serialize playback;
   don't add locking unless a real problem appears.
6. **Old `sounds/wakesound.mp3`** is now superseded by `wake.wav`/`wake.mp3` and
   is unreferenced. Removing it is reasonable but out of scope for this change.

---

## 9. Tests

Follow the existing style in `tests/` (see `tests/test_assistant_barge_in.py`,
`tests/test_assistant_streaming.py`; there is a `tests/audio` dir).

1. **Asset integrity** — parametrized over every `Earcon`:
   - `sounds/<earcon>.wav` exists.
   - `wave.open(path)` succeeds and `getsampwidth() == 2` (16-bit — the AEC
     contract).
2. **`EarconPlayer`** with a fake `AudioPlayer` that records `play` calls:
   - `play(Earcon.WAKE)` calls `player.play` once with the WAV bytes.
   - `_load` caches (two plays → one file read; patch/spy the read).
   - `play_soon` schedules a task, returns immediately, and eventually calls
     `player.play`; an exception in `player.play` is logged, not propagated.
3. **`SoundListener`** with a fake/stub `EarconPlayer` (spy on `play_soon`):
   - Dispatching `Interrupted(phase=...)` → `play_soon(Earcon.INTERRUPT)`.
   - Dispatching `SessionEnded()` → `play_soon(Earcon.SLEEP)`.
   - The handler returns without awaiting playback (dispatch is not blocked).
4. **Assistant ordering** — with fake recorder/player/earcons, assert the wake
   earcon is played **before** the first `record_until_silence` call within a
   session. Mirror the harness already used in the barge-in/streaming tests.

---

## 10. Step-by-step checklist

1. [ ] Add `--to-wav` mode to `scripts/generate_sounds.py` (transcode existing
       `sounds/*.mp3` → `sounds/*.wav`, `pcm_s16le`, via bundled ffmpeg; no API
       calls). Run it. Commit the six `.wav` files.
2. [ ] Create `cara/audio/earcons.py` with `Earcon` + `EarconPlayer` (§4).
3. [ ] Re-export `Earcon`, `EarconPlayer` from `cara/audio/__init__.py`
       (explicit relative import, add to `__all__`).
4. [ ] Fill `cara/listener/sound_listener.py` with `SoundListener` (§5); export
       it from `cara/listener/__init__.py`.
5. [ ] In `cara/assistant.py`: retain `self._player`, pass it to
       `StreamingTextToSpeech`, build `self._earcons` and `self._sound_listener`
       (§7a); add the awaited wake tone in `_run` (§7b); add imports (§7c).
6. [ ] (Recommended) Shorten the wake tone to ~0.4–0.6 s and re-pick/re-convert
       (§8.3).
7. [ ] (Sonos) Decide and implement the wake-tone latency handling (§8.2).
8. [ ] Add tests (§9). Run the full suite + `ruff` (pre-commit is configured).
9. [ ] Manual check: run `main.py`, say the wake word — tone plays fully, then it
       listens; interrupt mid-answer — interrupt tone; end session — sleep tone.

---

## 11. Out of scope (do not do unless asked)

- Inventing `success`/`error`/`listening` triggers or new event types.
- Wiring earcons in `main.py` (they are owned internally by the assistant).
- Per-earcon volume / ducking / mixing controls.
- `importlib.resources` packaging of the WAV assets (only needed if shipped as a
  wheel).
- Removing `sounds/wakesound.mp3`.
