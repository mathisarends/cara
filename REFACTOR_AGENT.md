# Refactor: Agent-Kern von der Modalität trennen

Ziel: `Agent` ist textbasiert und alleine lauffähig. Voice ist eine Schale darum
herum, kein Sonderfall im Kern. Beide Wege teilen sich exakt dieselbe
Denk-Logik (LLM-Stream, Tools, `MessageManager`, Event-Bus).

```python
agent = Agent(llm=llm, skills=skills)
print(await agent.ask("Wie ist das Wetter?"))          # Text, ein Aufruf

await ConsoleAgent(agent).start()                       # Text, REPL
await VoiceAgent(agent, wake_word_settings=...).start()  # Voice
```

---

## 1. Was heute im Weg steht

`cara/assistant.py` ist eine einzige Klasse, die fünf Verantwortlichkeiten
vermischt:

| Zeile | Verantwortlichkeit | Modalität |
| --- | --- | --- |
| `start`, `_run` | Wake-Word-Schleife, Follow-up, Barge-in | nur Voice |
| `_record`, `_transcribe` | Mikrofon → Text | nur Voice |
| `_think`, `_stream_response`, `_resolve_completion` | LLM + Tools | **modalitätsfrei** |
| `_speak`, `_publish_speech_chunks` | Text → Lautsprecher | nur Voice |
| `__init__` | baut alles davon auf | gemischt |

Drei konkrete Kopplungen:

1. **`_stream_response` erzeugt Sprach-Chunks.** Der `NaturalPauseChunker`
   (300/500/800 Zeichen) sitzt mitten in der Tool-Schleife, obwohl er reine
   TTS-Ergonomie ist. Für Text will man Deltas sofort, nicht in 500er-Blöcken.
2. **`interrupt: asyncio.Event` zieht sich durch den Kern.** Das ist ein
   Wake-Word-Barge-in-Konzept, das `_think`, `_stream_response` und `_speak`
   durchdringt.
3. **Der Konstruktor erzwingt Audio.** `PortAudioDevice()`, `MicrophoneStream`,
   `AudioPlayer` und `wake_word_settings` (Pflichtargument!) werden gebaut,
   bevor irgendein Modell irgendwas denkt. Ein Text-Agent kann so nicht
   existieren, ohne ein Audiogerät zu öffnen.

---

## 2. Zielarchitektur

Drei Schichten, klar getrennt:

```
┌─────────────────────────────────────────────────────────────┐
│  Driver           ConsoleAgent          VoiceAgent          │
│  (Sessionform)    stdin-REPL            Wake-Word + Turns   │
├─────────────────────────────────────────────────────────────┤
│  Kanäle           InputChannel          ResponseSink        │
│                   ConsoleInput          ConsoleSink         │
│                   VoiceInput            SpeechSink          │
├─────────────────────────────────────────────────────────────┤
│  Kern             Agent                                     │
│                   llm · Tools · MessageManager · EventBus   │
│                   run(prompt) -> AsyncIterator[AgentEvent]  │
└─────────────────────────────────────────────────────────────┘
```

Die Abhängigkeiten zeigen nur nach unten. `Agent` kennt weder Mikrofon noch
Lautsprecher noch `asyncio.Event`-Interrupts.

### Modulaufteilung

```
cara/
  agent/
    __init__.py        # Agent, AgentEvent-Typen, ResponseSink
    agent.py           # Agent (Kern)
    views.py           # TextDelta, ToolCalled, TurnCompleted
    sinks.py           # ResponseSink (ABC), CollectingSink, ConsoleSink
  voice/
    __init__.py        # VoiceAgent, VoiceSettings
    agent.py           # VoiceAgent (Driver: Wake-Word, Follow-up, Barge-in)
    input.py           # VoiceInput (Recorder + STT)
    sink.py            # SpeechSink (Chunker + StreamingTextToSpeech)
  console/
    __init__.py        # ConsoleAgent
    agent.py           # ConsoleAgent (stdin-REPL)
```

`cara/assistant.py` entfällt. `cara/replies.py` wandert nach `cara/agent/` und
verliert den Chunker (siehe 2.3).

---

### 2.1 Der Kern: `Agent`

Der Kern streamt **Events**, statt in einen Lautsprecher zu schreiben. Damit
entscheidet der Aufrufer, was mit Zwischenständen passiert, und Voice/Text
teilen sich denselben Code ohne Flags.

```python
# cara/agent/views.py
class TextDelta(BaseModel):
    """Roher Text-Ausschnitt aus dem LLM-Stream, ungechunkt."""
    text: str


class ToolCalled(BaseModel):
    name: str
    ok: bool


class TurnCompleted(BaseModel):
    answer: str
    end_session: bool
    replaced: bool
    """True, wenn ein END_SESSION-Tool die gestreamte Antwort ersetzt hat."""


type AgentEvent = TextDelta | ToolCalled | TurnCompleted
```

```python
# cara/agent/agent.py
class Agent:
    def __init__(
        self,
        *,
        llm: ChatModel,
        tools: Tools | None = None,
        skills: Skills | None = None,
        file_system: FileSystem | None = None,
        event_bus: EventBus | None = None,
        system_prompt: str | SystemPrompt | None = None,
        override_system_prompt: str | None = None,
        extend_system_prompt: str | None = None,
    ) -> None: ...

    @property
    def event_bus(self) -> EventBus: ...

    @property
    def tools(self) -> Tools:
        """Damit Voice den AudioPlayer nachträglich bereitstellen kann."""

    async def run(self, prompt: str) -> AsyncIterator[AgentEvent]:
        """Ein Turn: Nutzertext rein, Deltas + Tool-Runden raus.

        Läuft die Tool-Schleife bis zur finalen Antwort, hängt sie an den
        MessageManager an und schließt mit genau einem TurnCompleted.
        """

    async def ask(self, prompt: str) -> str:
        """Bequemlichkeit: run() leerlaufen lassen, Antworttext zurückgeben."""
```

Was aus `VoiceAgent` unverändert hierher wandert: `_build_system_prompt`,
`_resolve_completion`, `_reply`, die Tool-Schleife aus `_stream_response`, die
`MessageManager`-Anbindung, `AnswerGenerated`.

Was **nicht** mitkommt: `interrupt`, `_speak`, `_publish_speech_chunks`,
`_set_state` für Audio-Phasen, `NaturalPauseChunker`.

Kein Audiogerät im Konstruktor. `Agent(llm=llm)` öffnet nichts.

### 2.2 Interrupt aus dem Kern entfernen

Heute reicht `_think` ein `asyncio.Event` bis in `_speak` durch und wirft
`_ResponseInterrupted`. Der Kern braucht das nicht: **Abbruch ist Task-Abbruch.**

`agent.run()` ist ein Async-Generator. Wer ihn abbrechen will, cancelt den
konsumierenden Task oder verlässt die `async for`-Schleife — der Generator wird
geschlossen, der LLM-Stream via `finally` beendet. `VoiceAgent` behält
`WakeWordBargeIn` und den `_ResponseInterrupted`-Pfad **bei sich**:

```python
# cara/voice/agent.py (Ausschnitt)
async with WakeWordBargeIn(listener) as barge_in:
    turn = asyncio.create_task(self._drive_turn(transcript, barge_in.interrupt))
    ...
```

Der Kern bleibt frei von Interrupt-Vokabular. Wichtig: Eine mittendrin
abgebrochene Antwort darf den `MessageManager` nicht mit einer halben
Assistant-Nachricht verunreinigen — `Agent.run` schreibt die Antwort erst beim
`TurnCompleted` fest, also passiert das automatisch richtig.

### 2.3 Chunking gehört zur Sprache, nicht zum Kern

`NaturalPauseChunker` zieht in den `SpeechSink`. Konsequenz: Der Kern streamt
rohe Deltas, und die Konsole kann live Zeichen für Zeichen tippen, statt auf
300-Zeichen-Blöcke zu warten — heute nicht möglich.

```python
# cara/agent/sinks.py
class ResponseSink(ABC):
    """Nimmt den Antwortstrom eines Turns entgegen."""

    @abstractmethod
    async def open(self) -> None: ...

    @abstractmethod
    async def send(self, text: str) -> None: ...

    @abstractmethod
    async def close(self, completed: TurnCompleted) -> None:
        """Rest ausspülen; bei completed.replaced die Ersatzantwort ausgeben."""
```

```python
# cara/voice/sink.py
class SpeechSink(ResponseSink):
    """Deltas -> NaturalPauseChunker -> StreamingTextToSpeech -> Player."""

    def __init__(
        self,
        *,
        tts: TextToSpeech,
        player: AudioPlayback,
        speech_settings: SpeechSettings,
        event_bus: EventBus,
        cancel: asyncio.Event | None = None,
    ) -> None: ...
```

`SpeechSink` erbt die heutige Mechanik: `TextChunkStream` als Queue, die
`StreamingTextToSpeech.speak(...)` in einem Hintergrundtask konsumiert, plus
`SpeechChunkGenerated`-Dispatch. Die Logik aus `StreamingReply.finish` —
gestreamte Antwort vs. vom Tool ersetzte Antwort — wird zu `close()`:

```python
async def close(self, completed: TurnCompleted) -> None:
    if completed.replaced:
        self._chunks.send(completed.answer)   # END_SESSION-Text sprechen
    elif tail := self._chunker.flush():
        self._chunks.send(tail)
    self._chunks.close()
    await self._pipeline                       # auf Playback warten
```

`ConsoleSink` schreibt Deltas direkt nach stdout. `CollectingSink` sammelt nur
(für `ask()` und Tests).

### 2.4 Eingabe: `InputChannel`

```python
# cara/agent/inputs.py
class InputChannel(ABC):
    @abstractmethod
    def turns(self) -> AsyncIterator[str]:
        """Liefert Nutzeräußerungen, bis die Session endet."""
```

`ConsoleInput` liest `stdin` (via `asyncio.to_thread`, damit der Loop frei
bleibt). `VoiceInput` kapselt Recorder + STT + Follow-up-Timeout:

```python
# cara/voice/input.py
class VoiceInput(InputChannel):
    def __init__(
        self,
        *,
        recorder: SpeechRecorder,
        stt: SpeechToText,
        speech_settings: SpeechSettings,
        event_bus: EventBus,
        follow_up_timeout_seconds: float = 7.0,
    ) -> None: ...

    async def record(self, *, follow_up: bool = False, ready: threading.Event | None = None) -> str | None:
        """Aufnehmen bis Stille, transkribieren, Transcribed dispatchen."""
```

Das ist `_record` + `_transcribe` unverändert, nur an einem eigenen Ort.

### 2.5 Die Driver

`ConsoleAgent` ist trivial und macht sofort sichtbar, dass die Trennung trägt:

```python
class ConsoleAgent:
    def __init__(self, agent: Agent, *, sink: ResponseSink | None = None) -> None:
        self._agent = agent
        self._sink = sink or ConsoleSink()

    async def start(self) -> None:
        async for prompt in ConsoleInput().turns():
            if (completed := await self._drive(prompt)).end_session:
                break
```

`VoiceAgent` behält den kompletten heutigen `_run`-Ablauf — Wake-Earcon,
Follow-up, Barge-in mit `pending_audio`, `SessionStarted`/`SessionEnded` — aber
delegiert Denken an `Agent` und Sprechen an `SpeechSink`:

```python
class VoiceAgent:
    def __init__(
        self,
        agent: Agent,
        *,
        wake_word_settings: WakeWordSettings,
        speech_settings: SpeechSettings | None = None,
        recorder: SpeechRecorder | None = None,
        player: AudioPlayer | None = None,
        stt: SpeechToText | None = None,
        tts: TextToSpeech | None = None,
        api_key: str | None = None,
        follow_up_timeout_seconds: float = DEFAULT_FOLLOW_UP_TIMEOUT_SECONDS,
    ) -> None:
        ...
        agent.tools.provide(self._player)   # set_volume / set_audio_output
```

Hier sitzt auch die Audio-Hardware: `PortAudioDevice`, `MicrophoneStream`,
`EarconPlayer`, `SoundListener`. `ConsoleAgent` importiert davon nichts.

Der gemeinsame Turn-Ablauf ist in beiden Drivern dieselben sechs Zeilen:

```python
async def _drive(self, prompt: str) -> TurnCompleted:
    await self._sink.open()
    async for event in self._agent.run(prompt):
        match event:
            case TextDelta(text=text):
                await self._sink.send(text)
            case TurnCompleted() as completed:
                await self._sink.close(completed)
                return completed
```

---

## 3. Zustand und Events

`AssistantState` enthält heute Voice-Phasen (`LISTENING`, `TRANSCRIBING`,
`SPEAKING`) und Kern-Phasen (`THINKING`, `CALLING_TOOL`). Kein neuer Event-Typ
(entsprechend CLAUDE.md) — nur eine Aufteilung, wer welchen Zustand setzt:

| Zustand | Setzer |
| --- | --- |
| `THINKING`, `CALLING_TOOL` | `Agent` |
| `IDLE`, `LISTENING`, `WAITING_FOLLOW_UP` | `VoiceAgent` |
| `TRANSCRIBING` | `VoiceInput` |
| `SPEAKING` | `SpeechSink` |

`StateChanged` bleibt das einzige Lifecycle-Signal. Ein Text-Agent emittiert
schlicht nie `SPEAKING` — bestehende Listener (`HueListener`, `SoundListener`)
funktionieren unverändert.

`SessionStarted`/`SessionEnded` bleiben beim Driver: Voice hat eine Session pro
Wake-Word, Konsole eine pro Prozess.

---

## 4. Migrationsschritte

Jeder Schritt ist für sich lauffähig; `main.py` bleibt bis Schritt 6 grün.

1. **`cara/agent/views.py` + `sinks.py` anlegen.** `ResponseSink`,
   `CollectingSink`, `ConsoleSink`. Noch niemand nutzt sie.
2. **`SpeechSink` bauen** aus `_speak`, `_publish_speech_chunks`,
   `StreamingReply.finish` und `NaturalPauseChunker`. `cara/replies.py` verliert
   den Chunker und wird zu `cara/agent/replies.py` (sammelt nur noch die
   `ChatInvokeCompletion` und gibt Deltas weiter).
3. **`Agent` extrahieren.** Kopiere `_build_system_prompt`, `_stream_response`,
   `_resolve_completion`, `_reply` nach `cara/agent/agent.py` und ersetze den
   `_speak`-Aufruf durch `yield TextDelta(...)`. Interrupt-Parameter ersatzlos
   streichen.
4. **`VoiceInput` extrahieren** (`_record`, `_transcribe`).
5. **`VoiceAgent` auf den Kern umstellen.** `_run` bleibt strukturell gleich;
   `_think` wird zu `_drive_turn` in einem cancelbaren Task.
6. **`main.py` umstellen** auf `VoiceAgent(Agent(llm=...), wake_word_settings=...)`;
   `cara/assistant.py` löschen.
7. **`ConsoleAgent` ergänzen** — jetzt fast geschenkt.
8. **`cara/__init__.py` aufräumen**: `Agent`, `VoiceAgent`, `ConsoleAgent`,
   `SpeechSettings`, die Events. `MessageManager` und `SystemPrompt` sind
   Implementierungsdetails und fliegen aus dem Re-Export (CLAUDE.md).

Kein Kompatibilitäts-Alias für `VoiceAgent`s alte Signatur — der Rename wird
laut CLAUDE.md komplett durchgezogen.

---

## 5. Wie sich das anfühlt

```python
# Textbasiert, kein Audio, kein Wake-Word, kein Mikrofon
agent = Agent(llm=ChatCodex.from_cli(model="gpt-5.6-terra"), skills=skills)
print(await agent.ask("Fasse mir die Skills zusammen."))

# Textbasiert mit Live-Ausgabe
await ConsoleAgent(agent).start()

# Derselbe Agent, per Stimme
await VoiceAgent(
    agent,
    wake_word_settings=WakeWordSettings(wake_word=WakeWord.HEY_MYCROFT, sensitivity=0.5),
    speech_settings=SpeechSettings(language="de"),
).start()
```

Der Agent ist in allen drei Fällen dasselbe Objekt mit demselben
Gesprächsverlauf. Man kann eine Unterhaltung getippt beginnen und per Stimme
fortsetzen, weil der `MessageManager` im Kern sitzt.

---

## 6. Offene Punkte

- **`AssistantState` umbenennen?** `AgentState` wäre konsistenter, berührt aber
  `HueListener`, `SoundListener` und die Event-Views. Separater Commit.
- **Mehrere Sinks gleichzeitig** (sprechen *und* mitschreiben): Ein
  `FanOutSink(ResponseSink)` löst das, sobald es gebraucht wird — nicht auf
  Vorrat bauen.
- **`SpeechSettings.language`** wird von STT und TTS geteilt, gehört also klar
  in die Voice-Schicht. `cara/views.py` sollte nach `cara/voice/views.py`.
- **`ready: threading.Event`** (Wake-Earcon-Synchronisation) bleibt bewusst in
  `VoiceInput.record` — das ist echte Hardware-Kopplung, kein Kern-Konzept.
