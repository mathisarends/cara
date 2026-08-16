# Cara Voice Pipeline – Architekturentwurf

Status: Diskussionsentwurf v0.1

## Ziel

Cara hört lokal und dauerhaft auf ein Wake Word. Erst nach einer Erkennung wird
Mikrofonaudio an Cartesia STT übertragen. Das endgültige Transkript startet eine
streamende LLM-Antwort, deren Text-Deltas unmittelbar an Cartesia TTS und deren
PCM-Chunks unmittelbar an die Audioausgabe weitergereicht werden.

Die Pipeline soll dabei:

- die ersten Wörter nach dem Wake Word nicht abschneiden,
- das Mikrofon genau einmal öffnen,
- Wake-Word-Erkennung auch während einer Antwort für Barge-in weiterführen,
- alle eigenen Ausgaben einschließlich Earcons in die Echo Cancellation führen,
- Ende-zu-Ende streamen und Cancellation/Fehler sauber propagieren,
- Provider hinter kleinen, typisierten Ports kapseln.

Nicht Ziel der ersten Ausbaustufe sind spekulative LLM-Aufrufe auf vorläufigen
Transkripten, Sprechererkennung und eine voll-duplex Unterhaltung ohne Wake Word.

## Vorgeschlagener Datenfluss

```text
                                   nur Lifecycle-Events
                              +--------------------------> EventBus
                              |
MicrophoneAudioInput -> EchoCancellingInput -> AudioHub (2 s Ringbuffer)
                                                |                 |
                                                |                 +-> Cartesia STT
                                                |                     (nur aktiver Turn)
                                                v
                                      wakewordkit detector
                                                |
                                                v
                                         TurnController
                                                |
                    final transcript            v       text deltas
Cartesia STT -----------------------------> Streaming LLM ----------+
                                                                      |
                                                                      v
                                                              Cartesia TTS
                                                                      |
                                                                 raw PCM
                                                                      v
                                                         StreamingAudioPlayer
                                                                      |
EchoCancellingInput <--- PlaybackTimeline <--- ReferenceTapOutput <--+
                                                                      |
                                                               AudioOutput
```

Der `EventBus` ist nicht der Audio-Datenpfad. Er meldet lediglich Ereignisse wie
Wake-Word erkannt, User-Turn begonnen/beendet, Assistant-Ausgabe begonnen/beendet,
Unterbrechung und Fehler. PCM-Chunks bleiben in einem direkten, typisierten
Streaming-Pfad; das erhält Reihenfolge und Backpressure.

## Audioaufnahme und Ringbuffer

`AudioHub` ist der einzige Consumer von `AudioInput.stream_chunks()` und damit der
einzige Owner des laufenden Capture-Loops. Er versieht jeden PCM-Chunk mit einer
monotonen Sequenznummer und Capture-Zeit und hält die letzten zwei Sekunden in
einem begrenzten Ringbuffer.

Consumer lesen über unabhängige Cursor statt über eine gemeinsam konsumierte
Queue. Damit bekommt jeder Consumer dieselben Chunks. Ein langsamer Consumer darf
die Aufnahme nicht blockieren; fällt sein Cursor hinter den ältesten Ringbuffer-
Chunk zurück, endet dieser Consumer explizit mit einem Overrun-Fehler.

Vorgeschlagenes Eingabeformat:

- PCM signed 16-bit little-endian
- mono
- 16 kHz
- 1.280 Frames pro Chunk (80 ms), passend zum bestehenden Wake-Word-Pfad
- Ringbuffer: 2 Sekunden
- Command-Pre-Roll: 160 ms vor dem Ende des Detektions-Chunks

Der Wake-Word-Consumer läuft permanent. Eine Erkennung trägt die Sequenznummer des
Chunks, in dem sie erfolgte. Beim Start des User-Turns wird zuerst atomar ein
STT-Cursor ab `detection_end - command_pre_roll` reserviert und erst danach weitere
Arbeit (beispielsweise das Wake-Earcon) begonnen. Audio, das während der lokalen
Wake-Word-Inferenz eintrifft, liegt bereits im Ringbuffer und geht nicht verloren.

Der kurze Pre-Roll enthält höchstens das Ende des Wake Words. Falls Cartesia das
vollständige konfigurierte Wake Word dennoch an den Anfang des finalen Transkripts
setzt, darf exakt diese bekannte Phrase entfernt werden. Unscharfes Abschneiden
von Silben oder beliebigen Präfixen findet nicht statt.

Datenschutzgrenze: Im Zustand `ARMED` laufen Capture, AEC und wakewordkit lokal;
Cartesia erhält noch kein Audio. Erst ein erfolgreicher Trigger öffnet einen
STT-Turn und gibt dessen Cursor frei.

## Wake Word und Turn-Erkennung

`WakeWordDetector.process()` aus `wakewordkit` erhält die tatsächliche
`AudioFormat` explizit. Der Detector besitzt kein Mikrofon und wird beim normalen
Turnwechsel nicht neu erzeugt. Ein Reset ist nur bei Neustart/Overrun oder einer
bewusst gewünschten Session-Grenze nötig; der eingebaute Cooldown verhindert
unmittelbare Doppelerkennungen.

Pro Wake Word entsteht genau ein Cartesia-STT-Stream. Der Stream bekommt Pre-Roll
und danach Live-Audio aus demselben Cursor. Für die Events gilt:

- `TurnUpdate`: vorläufige Anzeige/Logging, niemals LLM-Input.
- `TurnEagerEnd`: weiterhin vorläufig; `TurnResume` kann folgen.
- `TurnEnd`: autoritatives Transkript und Startsignal für LLM/TTS.
- kein Speech-Start innerhalb eines konfigurierten Timeouts: Turn abbrechen und
  wieder `ARMED` werden.

Die erste Version startet das LLM ausschließlich auf `TurnEnd`. Eine spätere
spekulative Ausführung auf `TurnEagerEnd` braucht eine eigene Revisions- und
Cancellation-Semantik und gehört nicht in den Basispfad.

Sobald `TurnEnd` verarbeitet wurde, wird der Audio-Cursor geschlossen und der
STT-Async-Generator zuverlässig mit `aclose()` beendet. So bleiben weder Sender-
Tasks noch WebSockets hängen.

## LLM- und TTS-Streaming

Der LLM-Port ist absichtlich klein:

```python
class LanguageModel(Protocol):
    def respond(self, text: str) -> AsyncIterator[str]: ...
```

Der erste Adapter ist ein `EchoLanguageModel`, der beispielsweise
`"Du hast gesagt: …"` in mehreren Chunks liefert. Der echte Gateway-/LLM-Adapter
implementiert später denselben Port.

Bei `TurnEnd` startet der Controller zwei Tasks gleichzeitig:

1. Der LLM-Producer beginnt zu inferieren und schreibt Text-Deltas in eine kleine,
   begrenzte Queue.
2. Der TTS-Consumer wird sofort bis zum ersten Await vorangetrieben. Dadurch kann
   `vocalbin` die Cartesia-Verbindung öffnen bzw. wiederverwenden, während das LLM
   noch am ersten Token arbeitet. Der Text-Iterator wartet auf derselben Queue.

Es wird keine private `vocalbin`-API zum Vorwärmen verwendet. Ein langlebiger
`CartesiaTextToSpeech`-Client wird beim Prozessstart erzeugt und beim Shutdown
geschlossen; pro Antwort entsteht ein neuer TTS-Context auf dessen persistenter
Verbindung. `stream_incremental()` erhält den LLM-Iterator direkt. Leere Deltas
werden verworfen; optional darf ein kleiner Coalescer sehr kurze Token-Fragmente
für höchstens etwa 30 ms sammeln, ohne Satzende abzuwarten.

Cartesia TTS liefert für den Streaming-Pfad Raw-PCM, vorgeschlagen 24 kHz,
signed 16-bit, mono. Dafür braucht es einen `StreamingAudioPlayer`, der
`AudioOutput.start()` einmal aufruft, Chunks direkt mit `play_chunk()` schreibt und
am Ende `finish_response()` aufruft. Der vorhandene WAV-orientierte `AudioPlayer`
bleibt für vollständige WAV-Dateien und Earcons zuständig und ist nicht der
TTS-Streaming-Adapter.

Ein gemeinsamer `PlaybackCoordinator` serialisiert Earcons und Sprache, damit nie
zwei Producer gleichzeitig dasselbe `AudioOutput` beschreiben. Das Wake-Earcon
darf die bereits gestartete STT-Aufnahme nicht verzögern und läuft über denselben
echo-referenzierten Output.

## Echo Cancellation

Die Echo Cancellation umschließt das physische Gerätepaar genau einmal:

```text
physical input  -> EchoCancellingInput -> AudioHub
physical output <- ReferenceTapOutput  <- alle Playback-Arten
```

Wake-Word-Erkennung und STT sehen ausschließlich das bereinigte Signal. TTS,
Earcons und alle weiteren Sounds laufen ausschließlich durch
`ReferenceTapOutput`. Bei Barge-in wird zuerst der Output-Puffer geleert und die
pending Playback-Referenz verworfen; danach wird der alte Turn abgebrochen.

Die vorhandene Timeline-Ausrichtung ist für eine lokale, zeitnah schreibende
Audioausgabe sinnvoll. `SonosOutput` puffert hingegen die komplette Antwort und
startet sie erst nach Upload als Clip. Ein Reference-Tap beim Befüllen dieses
Puffers bildet den realen Wiedergabezeitpunkt nicht ab. Deshalb gilt für v1:

- Niedrige Latenz und verlässliche AEC: `LocalAudioOutput`.
- Sonos: funktionaler Fallback mit Antwort-Buffering, aber kein garantierter
  Streaming- oder AEC-Pfad, bis Sonos einen belastbaren Playback-Start/-Cursor
  zurückmeldet.

## Zustands- und Cancellation-Modell

```text
STARTING -> ARMED -> LISTENING -> THINKING -> SPEAKING -> ARMED
              ^          |           |           |
              +----------+-----------+-----------+
                      timeout, error oder cancel
```

`THINKING` und `SPEAKING` können sich überlappen: Sobald der erste LLM-Textchunk
vorliegt, beginnt TTS; sobald der erste PCM-Chunk ausgegeben wird, gilt der Turn
als `SPEAKING`.

Der `TurnController` besitzt höchstens eine aktive Turn-Task. Jeder Turn erhält
eine monotone `turn_id`. Ein Wake Word während `THINKING` oder `SPEAKING` bedeutet
Barge-in:

1. neuen STT-Cursor sofort reservieren,
2. laufende Audioausgabe leeren,
3. alten Turn inklusive LLM-, TTS- und Playback-Tasks canceln und schließen,
4. `AssistantInterrupted` emittieren,
5. neuen Listening-Turn starten.

Jeder ausgehende Chunk wird gegen die aktive `turn_id` geprüft, sodass ein später
Provider-Callback eines abgebrochenen Turns keine alte Antwort mehr abspielen
kann. Begrenzte Queues sorgen für Backpressure. Provider-Timeouts und Fehler
beenden nur den aktuellen Turn; Capture und Wake-Word-Loop bleiben aktiv.

## Vorgeschlagene Module

```text
voice/
  audio/
    hub.py                 # ein Capture-Loop, Ringbuffer und Cursor
    streaming_player.py    # Raw-PCM -> AudioOutput
    playback_coordinator.py
  wakeword/
    listener.py            # wakewordkit-Adapter, kein Geräte-Owner
  stt/
    port.py
    cartesia.py
  llm/
    port.py
    mock.py
  tts/
    port.py
    cartesia.py
  pipeline/
    controller.py          # Zustände, Turn-Lifetime, Barge-in
    models.py              # reine Datenobjekte wie AudioFrame/TurnId
```

Package-`__init__.py`-Dateien exportieren nur die bewusst öffentliche API über
explizite relative Imports und `__all__`. Konkrete Provider bleiben in ihren
Untermodulen.

## Abnahmekriterien für v1

- Das Mikrofon wird beim Start einmal geöffnet und läuft über mehrere Turns.
- Vor dem Wake Word verlassen keine Mikrofonbytes den lokalen Prozess.
- Ein Kommando, das unmittelbar nach dem Wake Word beginnt, erscheint vollständig
  im finalen STT-Text (automatisierter Ringbuffer-Race-Test).
- `TurnEagerEnd` startet kein LLM; genau ein `TurnEnd` startet genau einen LLM-Turn.
- LLM-Deltas erreichen TTS vor Abschluss der LLM-Antwort.
- Der erste TTS-PCM-Chunk wird vor Abschluss der TTS-Synthese abgespielt.
- Barge-in verhindert nach seiner Erkennung jeden weiteren PCM-Chunk des alten
  Turns und startet ohne erneutes Öffnen des Mikrofons einen neuen STT-Turn.
- Earcons und TTS erscheinen als Far-End-Referenz der AEC.
- Shutdown und Turn-Cancellation hinterlassen keine Tasks, Cursor oder WebSockets.
- Unit-Tests verwenden deterministische Fake-Frames und Provider; ein optionaler
  Hardware-Smoke-Test misst Wake-to-first-audio-Latenz und AEC praktisch.

## Noch gemeinsam festzulegen

Vorgeschlagene Defaults stehen jeweils zuerst:

1. Ausgabeziel: lokaler Lautsprecher für echtes Streaming/AEC oder Sonos trotz
   vollständigem Response-Buffering?
2. Aktivierungsmodell: ein Wake Word pro User-Turn oder ein kurzes Folgefenster,
   in dem weitere Turns ohne Wake Word erlaubt sind?
3. Wake Word, Sensitivität und Cooldown (aktuell bietet sich `HEY_MYCROFT`, 0,5
   und 1,5 s an).
4. Cartesia-Stimme sowie Endpointing-Werte, insbesondere Speech-Start-Timeout und
   `turn_end_timeout_ms`.
5. Soll ein Wake Word während `LISTENING` ignoriert werden (Vorschlag) oder den
   begonnenen User-Turn ebenfalls neu starten?

## Bestehender Code und Migrationsgrenze

Die neuen `voice.stt`-/`voice.tts`-Ports und die Echo-Cancellation passen bereits
zu diesem Zielbild. Aktuell verweisen `voice_main.py`, einige ältere Tests sowie
mehrere Package-Exports noch auf nicht vorhandene frühere Module wie
`voice.speech`, `voice.wakeword` und `VoiceSession`. Die Implementierung sollte
diese Aufrufer auf die neue Pipeline umstellen und den alten API-Schnitt komplett
entfernen, statt Kompatibilitätsaliases einzuführen.
