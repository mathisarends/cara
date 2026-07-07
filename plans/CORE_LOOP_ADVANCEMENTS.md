# Core Loop Advancements

Ausbau des Voice-Loops von einem Single-Shot-Turn zu einer echten Konversations-Pipeline.

Zwei Features bauen aufeinander auf:

1. **MULTI_TURN_MESSAGES** — Cara behält Kontext über mehrere Turns und führt
   Folge-Turns ohne erneutes Wakeword.
2. **BARGE_IN** — der Nutzer kann Cara per Wakeword unterbrechen, während sie
   *denkt* oder *spricht*, um die Anfrage zu korrigieren oder zu verfeinern.

---

## Ausgangslage (Stand heute)

Der heutige Loop ist streng sequenziell und zustandslos:

- `VoiceAssistant.run_turn()` (`cara/assistant.py`) macht genau einen Durchlauf:
  `record → transcribe → think → speak` und kehrt danach zu `IDLE` zurück.
- `_reply()` baut die LLM-Nachrichten bei *jedem* Turn neu aus
  `SystemMessage + UserMessage` zusammen — es gibt **keine History**.
- `WavAudioPlayer.play()` (`cara/audio.py`) blockiert bis das Audio fertig
  abgespielt ist; es gibt **keine Möglichkeit zu unterbrechen**.
- `MicrophoneRecorder.record_until_silence()` läuft als blockierender Executor-Task,
  Aufnahme und Wakeword-Erkennung laufen **nie gleichzeitig**.
- `WakeWordListener` (`cara/wakeword/listener.py`) stoppt seinen Mic-Stream
  während eines Turns (`stop_stream`) und startet ihn erst nach `on_detection()`
  wieder. Während eines Turns hört also **niemand** auf das Wakeword.
- Lifecycle-States: `IDLE, LISTENING, TRANSCRIBING, THINKING, SPEAKING`.

Diese drei Eigenschaften — keine History, nicht unterbrechbares Playback, kein
Wakeword-Listening während eines Turns — sind die zentralen Hürden.

---

## Feature 1: MULTI_TURN_MESSAGES

### Ziel

Nach dem Wakeword führt Cara eine zusammenhängende Konversation: Folge-Fragen
beziehen sich auf vorherige Antworten, und nach Caras Antwort kann der Nutzer
direkt weitersprechen, **ohne** das Wakeword zu wiederholen. Die Session endet
durch Stille (Timeout), eine Abschiedsfloskel oder explizites Beenden.

### Verhalten

- **Session-Konzept**: Ein Wakeword startet eine *Session* statt eines einzelnen
  Turns. Eine Session bündelt mehrere Turns mit geteilter History.
- **Follow-up ohne Wakeword**: Nach dem `speak`-Schritt wechselt Cara nicht zu
  `IDLE`, sondern öffnet ein kurzes Aufnahmefenster (z. B. 6–8 s) und lauscht
  direkt auf die nächste Äußerung.
- **Stille-Timeout**: Kommt im Follow-up-Fenster keine Sprache, endet die Session
  und Cara kehrt zum Wakeword-Listening zurück.
- **Kontext im LLM**: Jeder Turn hängt `UserMessage`/`AssistantMessage` an eine
  laufende History an, die als `SystemMessage + [...history...] + UserMessage`
  an das LLM geht.
- **History-Begrenzung**: Sliding Window (z. B. letzte N Turns oder Token-Budget),
  damit Kontext und Latenz nicht unbegrenzt wachsen.

### Architektur-Änderungen

#### 1. MessageManager/History-Modell

Neue Datei `cara/messages/manager.py`:

```python
class MessageManager:
    system_prompt: str
    messages: list[Message]          # llmify Message-Typen
    max_turns: int = 12

    def add_user(self, text: str) -> None: ...
    def add_assistant(self, text: str) -> None: ...
    def to_llm_messages(self) -> list[Message]:  # System + getrimmte History
        ...
    def trim(self) -> None:          # Sliding Window anwenden
        ...
```

- `VoiceAssistant._reply()` nutzt `message_manager.to_llm_messages()` statt jedes Mal
  System + einzelne UserMessage neu zu bauen.
- `VoiceTurn` bleibt das Ergebnis eines einzelnen Turns; eine neue `VoiceSession`
  kann optional die Liste der Turns + finale History tragen.

#### 2. Session-Loop im VoiceAssistant

Neue Methode `run_session()`, die `run_turn()` als Schleife nutzt:

```python
async def run_session(self) -> VoiceSession:
    message_manager = MessageManager(system_prompt=self.system_prompt, messages=[])
    turns: list[VoiceTurn] = []
    try:
        while True:
            turn = await self.run_turn(message_manager, follow_up=bool(turns))
            if turn is None:          # Stille -> Session beenden
                break
            turns.append(turn)
            if self._should_end_session(turn):
                break
    finally:
        await self._set_state(AssistantState.IDLE)
    return VoiceSession(turns=turns)
```

- `run_turn()` bekommt den `MessageManager` übergeben und arbeitet darauf.
- Der `follow_up`-Modus nutzt ein kürzeres Aufnahmefenster mit Stille-Timeout
  (returnt `None` bei reiner Stille → Session endet).
- `main.py` ruft `assistant.run_session` statt `assistant.run_turn` im
  Wakeword-`on_detection` auf.

#### 3. Aufnahme mit Follow-up-Timeout

`UtteranceRecorder` braucht einen Modus, der bei sofortiger Stille abbricht statt
endlos zu warten:

```python
async def record_until_silence(
    self, *, initial_silence_timeout: float | None = None
) -> bytes | None:   # None = es wurde nie Sprache erkannt
```

- `initial_silence_timeout` (z. B. 6 s) im Follow-up: hört der Recorder so lange
  nichts, gibt er `None` zurück → Session endet sauber.

#### 4. Session-Ende erkennen

`_should_end_session(turn)` — pragmatisch starten:

- Abschiedsfloskeln im Transcript (`"danke, das war's"`, `"tschüss"`, `"stop"`).
- Optional später: LLM/Tool-Signal, dass die Konversation abgeschlossen ist.

#### 5. Neue Lifecycle-Events

In `cara/lifecycle.py`:

- `SessionStarted` / `SessionEnded` (umschließt mehrere Turns).
- Optional `AssistantState.WAITING_FOLLOW_UP` für UI/LED-Feedback im
  Follow-up-Fenster.

### Tests

- `MessageManager`: History wächst korrekt, Trimming respektiert das Window,
  `to_llm_messages()` liefert System + getrimmte History.
- `run_session()` mit Fake-Recorder/STT/LLM: mehrere Turns, korrekte Übergabe von
  Kontext, Stille beendet Session.
- Folge-Turn referenziert Kontext (Fake-LLM bekommt History gereicht).

---

## Feature 2: BARGE_IN (per Wakeword)

### Ziel

Während Cara *denkt* (`THINKING`) oder *spricht* (`SPEAKING`), kann der Nutzer das
Wakeword sagen, um sie sofort zu unterbrechen: laufendes Playback bzw. die laufende
LLM-Generierung wird abgebrochen, Cara hört direkt neu zu und der neue Input
verfeinert/korrigiert die Anfrage im selben Konversationskontext.

> Voraussetzung: Feature 1 (MessageManager/History), damit die Korrektur im Kontext
> der bisherigen Konversation landet.

### Verhalten

- **Wakeword bleibt aktiv** während `THINKING` und `SPEAKING`.
- **Unterbrechung beim Sprechen**: Playback stoppt sofort; die abgebrochene
  (Teil-)Antwort wird als solche in der History markiert.
- **Unterbrechung beim Denken**: laufender LLM-Call wird gecancelt; die noch nicht
  ausgesprochene Antwort wird verworfen bzw. als abgebrochen markiert.
- **Nahtloser Übergang**: Nach Barge-in startet sofort ein neuer Aufnahme-Turn in
  derselben Session.
- **Echo-Vermeidung**: Caras eigene Ausgabe darf das Wakeword nicht triggern
  (siehe Risiken).

### Architektur-Änderungen

#### 1. Unterbrechbares Playback

`AudioPlayer.play()` muss kooperativ abbrechbar werden:

```python
class AudioPlayer(ABC):
    @abstractmethod
    async def play(self, audio: bytes, *, cancel: asyncio.Event) -> None: ...
```

- `WavAudioPlayer._play_sync` prüft pro Chunk `cancel.is_set()` und bricht die
  Wiedergabe-Schleife sauber ab (Stream stoppen/schließen).
- Da `play()` im Executor läuft, wird das `cancel`-Event threadsicher gesetzt
  (`asyncio.Event` via `loop.call_soon_threadsafe`, oder ein `threading.Event`
  das der Sync-Code direkt liest).

#### 2. Wakeword-Listening parallel zum Turn

Heute pausiert der `WakeWordListener` während eines Turns. Für Barge-in muss
das Wakeword **während** `THINKING`/`SPEAKING` weiterlaufen.

Optionen:

- **A — Listener läuft durch** und meldet Detektionen über einen Callback/Event
  an den laufenden Turn. Erfordert, dass Mic-Aufnahme (für den Turn) und
  Wakeword-Stream sich denselben Input teilen oder zwei Streams koexistieren.
- **B — Ein zentraler Audio-Input** verteilt PCM-Chunks an mehrere Consumer
  (Wakeword-Modell + Recorder). Sauberer langfristig, aber größerer Umbau.

Empfehlung: **Option A** als ersten Schritt, da Barge-in v. a. in `THINKING`/
`SPEAKING` gebraucht wird — in diesen Phasen läuft *kein* Recorder, der Mic-Stream
kann also exklusiv vom Wakeword-Modell genutzt werden. (In `LISTENING` ist Barge-in
ohnehin unnötig, da Cara bereits zuhört.)

#### 3. Cancellation-Mechanik im Turn

`run_turn()` bekommt ein Interrupt-Signal, das in `_think` und `_speak` greift:

```python
async def run_turn(self, message_manager, *, follow_up=False) -> VoiceTurn | None:
    interrupt = asyncio.Event()
    # Wakeword-Detektion während THINKING/SPEAKING setzt interrupt
    ...
    answer = await self._think(message_manager, interrupt=interrupt)
    if interrupt.is_set():
        return self._interrupted_turn(...)
    await self._speak(answer, interrupt=interrupt)
```

- `_think`: LLM-Call in `asyncio.Task`; bei `interrupt` wird der Task gecancelt
  (`task.cancel()`), Antwort verworfen/als abgebrochen markiert.
- `_speak`: reicht `interrupt` als `cancel`-Event an `player.play()` durch.
- Nach Barge-in kehrt der Loop in `run_session()` sofort in einen neuen
  `LISTENING`-Turn zurück (kein neues Wakeword nötig).

#### 4. History-Konsistenz bei Abbruch

- Abgebrochenes Playback: bereits gesprochener Teil ist unbekannt → die Antwort
  als „(unterbrochen)" in der History markieren oder ganz weglassen und nur die
  neue User-Korrektur anhängen. **Entscheidung nötig** (siehe offene Fragen).

#### 5. Neue Lifecycle-Events / States

- `Interrupted` Event (Phase, in der unterbrochen wurde).
- Optional `AssistantState.INTERRUPTED` als kurzer Übergangszustand.

### Tests

- `WavAudioPlayer`: gesetztes `cancel`-Event stoppt Wiedergabe vor Ende.
- `_think` bricht LLM-Task bei Interrupt sauber ab (kein Hängenbleiben).
- `run_turn` mit simuliertem Wakeword während `SPEAKING` → neuer Turn beginnt,
  History bleibt konsistent.
- Echo-Test: Caras Ausgabe triggert das Wakeword nicht (sofern Test-Setup das zulässt).

---

## Risiken & offene Fragen

- **Echo/Self-Trigger**: Während `SPEAKING` läuft Caras Stimme über den Lautsprecher
  und gleichzeitig das Mikro. Ohne Acoustic Echo Cancellation (AEC) kann Cara sich
  selbst hören und das Wakeword fälschlich triggern. Optionen: AEC, höhere
  Wakeword-Sensitivity-Schwelle während `SPEAKING`, oder Half-Duplex-Heuristik.
  → **Größtes technisches Risiko bei Barge-in.**
- **Doppelte Mic-Nutzung**: Recorder und Wakeword-Listener dürfen sich den
  PyAudio-Input-Stream nicht gegenseitig wegnehmen. Saubere Lösung = zentraler
  Audio-Hub (Option B), kurzfristig phasenabhängige exklusive Nutzung (Option A).
- **History bei Abbruch**: Wie wird eine unterbrochene Antwort in der History
  repräsentiert? (verwerfen vs. als abgebrochen markieren)
- **Session-Ende-Erkennung**: Reicht eine Floskel-Heuristik, oder braucht es ein
  LLM-Signal? Start mit Heuristik, später erweiterbar.
- **Latenz**: History vergrößert den LLM-Prompt. Trimming + ggf. Streaming der
  LLM-Antwort (Token-für-Token in TTS) reduzieren wahrgenommene Latenz.

---

## Umsetzungsreihenfolge (inkrementell)

1. **MessageManager-Modell** (`cara/messages/manager.py`) + Tests — rein, ohne I/O.
2. **`run_turn(message_manager)`** auf History umstellen, Verhalten unverändert.
3. **`run_session()`** + Follow-up-Recording + Session-Events → Feature 1 fertig.
4. **Unterbrechbares Playback** (`AudioPlayer.play(cancel=...)`) + Tests.
5. **Cancelbarer `_think`** (LLM-Task) + Interrupt-Verdrahtung in `run_turn`.
6. **Wakeword-Listening während Turn** (Option A) → Feature 2 fertig.
7. **Echo-Hardening** (Sensitivity/AEC) nach realen Tests.

Schritte 1–3 liefern bereits eigenständigen Mehrwert (echte Mehr-Turn-Gespräche)
und sind Voraussetzung für ein sinnvolles Barge-in in Schritt 4–6.
