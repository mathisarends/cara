# VAD- & Turn-Detection-Alternativen für Cara

> Recherche-/Entscheidungsgrundlage. Ziel: die aktuelle, rein energiebasierte
> Sprachpausen-Erkennung durch etwas Robusteres zu ersetzen und die
> Umbaukosten pro Alternative grob einschätzbar zu machen.

---

## 1. Ausgangslage im Code

Die eigentliche Erkennung „User spricht / User ist fertig" steckt heute
komplett in **`cara/audio/recorder.py`** (`MicrophoneRecorder`), hinter der
sauberen Schnittstelle **`SpeechRecorder`** (`cara/audio/ports.py`).

Was dort passiert (`_record_until_silence_sync`):

- Der `MicrophoneStream` (`cara/audio/microphone.py`) liefert **16 kHz, mono,
  int16** in Chunks von `chunk = 160` Samples (= 10 ms).
- Pro Chunk wird nur die **Lautstärke** bewertet: `_rms_int16(pcm)` (RMS über
  die int16-Samples).
- **Sprachbeginn:** RMS ≥ `silence_threshold` (500). Davor läuft ein 0,5 s
  Pre-Roll-Puffer, damit der Wortanfang nicht abgeschnitten wird.
- **Sprachende:** RMS < `silence_threshold` für zusammenhängend
  `silence_seconds` (1,2 s) → Aufnahme endet. Dazu `min_record_seconds` (0,4)
  und `max_record_seconds` (12,0) als Sicherungen.
- Rückgabe: eine **WAV-Bytefolge**, die anschließend in `assistant.py`
  (`_transcribe`) an die vocalbin-STT (OpenAI) geht.

**Das ist der springende Punkt für die Bewertung:** Die heutige Lösung
vermischt zwei eigentlich getrennte Aufgaben, die auch getrennt austauschbar
sind:

| Schicht | Frage | Heute in Cara |
|---|---|---|
| **VAD** (Voice Activity Detection) | Ist *gerade jetzt* Sprachenergie da? | RMS-Schwelle `500` |
| **Endpointing / Turn Detection** | Ist der User mit seinem *Turn* fertig? | fester Timer `1,2 s` Stille |

Fast alle unten genannten Alternativen ersetzen **genau eine** dieser beiden
Schichten:

- **Bessere VAD** (Silero, WebRTC, TEN) → ersetzt die RMS-Schwelle. Der feste
  1,2-s-Timer bleibt, wird aber deutlich zuverlässiger getriggert.
- **Semantische Turn-Detection** (Smart Turn v3, LiveKit, OpenAI
  `semantic_vad`) → ersetzt den *festen Timer* durch eine gelernte
  „ist-fertig?"-Entscheidung. Braucht darunter *trotzdem* eine VAD, die die
  Pausen findet, an denen das Turn-Modell gefragt wird.

Die beiden Optionen, die du schon recherchiert hast (Smart Turn v3, LiveKit),
sind **Turn-Detektoren**, keine VADs. Die stärkste Wirkung bekommst du
wahrscheinlich aus der Kombination *„gute VAD + optional semantischer
Turn-Detektor obendrauf"* — dazu unten mehr.

### Der Umbaupunkt ist überall derselbe

Egal welche Alternative: Die Naht ist `SpeechRecorder.record_until_silence()`.
Zwei saubere Wege:

1. **Klein (VAD-Tausch):** In `MicrophoneRecorder` nur `_rms_int16(...) >=
   threshold` durch einen VAD-Aufruf ersetzen. Eine neue Mini-Abstraktion:

   ```python
   class VoiceActivityDetector(ABC):
       @abstractmethod
       def is_speech(self, frame: bytes) -> bool: ...
   ```

   Der ganze Rest der Aufnahmelogik (Pre-Roll, min/max, `ready`-Event für den
   Earcon, Cancel) bleibt **unverändert**. Das ist der risikoärmste Umbau.

2. **Groß (Turn-Detection):** Ein zweiter Port für die Endpoint-Entscheidung.
   Die VAD findet die Pause, bei jeder Pause fragt der Recorder das
   Turn-Modell, ob der Turn zu Ende ist:

   ```python
   class TurnDetector(ABC):
       @abstractmethod
       async def is_complete(self, utterance: bytes) -> bool: ...
   ```

   Zusätzlich muss der `MicrophoneRecorder` Rohaudio (nicht nur WAV am Ende)
   segmentweise bereithalten. Mehr Aufwand, weil der feste Timer durch eine
   Zustandslogik ersetzt wird.

---

## 2. Überblick / Vergleich

| Option | Typ | Läuft lokal | Deutsch | Latenz Extra | Modellgröße | Umbau | Reifegrad |
|---|---|---|---|---|---|---|---|
| **Silero VAD** | VAD | ✅ CPU | n/a (sprachunabh.) | ~1 ms/Frame | ~1–2 MB | **klein** | sehr hoch |
| **WebRTC VAD** | VAD | ✅ CPU | n/a | vernachlässigbar | winzig | **klein** | hoch (alt) |
| **TEN VAD** | VAD | ✅ CPU | n/a | ~1 ms/Frame | winzig | **klein** | mittel (neu) |
| **Smart Turn v3** | Turn | ✅ CPU (ONNX) | ✅ (23 Spr.) | ~12–100 ms | ~8 MB | **mittel** | mittel-hoch |
| **LiveKit Turn Detector** | Turn | ✅ CPU | ✅ | ~löst bei Pause | ~mittel | **groß** | hoch |
| **OpenAI `semantic_vad`** | Turn (Cloud) | ❌ Cloud | ✅ | Netz-RTT | – | **groß** | hoch |
| **Picovoice Cobra** | VAD | ✅ CPU | n/a | vernachlässigbar | winzig | **klein** | hoch (proprietär) |

„Umbau" bezieht sich auf Cara konkret, nicht auf generischen Aufwand.

---

## 3. Die Alternativen im Detail

### 3.1 Silero VAD — *die naheliegendste Ergänzung, die du noch nicht auf dem Zettel hast*

Neuronales VAD-Modell, De-facto-Standard für lokale Sprach-Pipelines. MIT-Lizenz,
winziges JIT-/ONNX-Modell, arbeitet auf genau dem Format, das Cara schon liefert
(16 kHz mono, Frames von 512 Samples ≈ 32 ms). Gibt pro Frame eine
Sprach-Wahrscheinlichkeit 0…1.

**Vorteile**
- Direkter 1:1-Ersatz für `_rms_int16`: gleiche Eingabe, aber robust gegen
  Grundrauschen, Lüfter, Musik im Hintergrund, leises Sprechen — genau die
  Fälle, in denen eine RMS-Schwelle von 500 versagt (entweder schneidet sie
  leise Silben ab oder sie triggert auf Störgeräusche).
- Rein lokal, CPU, ~1 ms pro Frame, keine spürbare Zusatzlatenz.
- Sprachunabhängig → Deutsch ist kein Thema.
- Sehr kleiner, extrem gut erprobter Footprint. Kein Architektur-Umbau.

**Nachteile**
- Löst *nicht* das eigentliche Turn-Problem: du behältst den festen
  1,2-s-Timer. „Hat der User nur kurz überlegt oder ist er fertig?" bleibt
  offen. Es ist eine **bessere VAD, keine Turn-Detection**.
- Zusätzliche Runtime-Abhängigkeit (`onnxruntime` bzw. Torch-JIT). Bei Python
  3.13/3.14 auf ONNX-Runtime achten (Wheel-Verfügbarkeit).

**Grob-Umbau (klein)**
1. `onnxruntime` + Silero-Modell als Abhängigkeit; Modelldatei ähnlich wie das
   openwakeword-ONNX ablegen.
2. Neue Klasse `SileroVAD(VoiceActivityDetector)` in `cara/audio/` mit
   `is_speech(frame) -> bool` (Wahrscheinlichkeit > Schwelle).
3. In `MicrophoneRecorder`: `config.chunk` auf die von Silero erwartete
   Framegröße bringen (512 Samples statt 160) und `rms >= silence_threshold`
   durch `vad.is_speech(pcm)` ersetzen. `silence_threshold`/RMS entfällt,
   `silence_seconds` bleibt.
4. VAD über den Konstruktor injizierbar machen (Default = Silero), damit Tests
   weiter mit einem Fake-VAD laufen.

> Aufwand: überschaubar, isoliert, gut testbar. **Beste Wirkung pro Aufwand,
> wenn das Problem eher „schneidet ab / triggert auf Rauschen" ist als
> „reagiert zu langsam/zu schnell auf Turn-Enden".**

---

### 3.2 WebRTC VAD (`py-webrtcvad`)

Der Klassiker aus dem WebRTC-Stack: GMM-basiert, kein neuronales Netz,
C-Extension, mikroskopisch klein. Erwartet 10/20/30-ms-Frames bei 8/16/32/48 kHz.

**Vorteile**
- Praktisch null Latenz, keine ML-Runtime, keine Modelldatei.
- Frame-Größen (10 ms bei 16 kHz) passen exakt zu Caras heutigem `chunk=160`.
- Trivial einzubauen — gleicher kleiner Umbau wie bei Silero.

**Nachteile**
- Deutlich schwächer als Silero/TEN bei Hintergrundgeräuschen und Musik; nur
  vier grobe „Aggressivitäts"-Stufen. Bei Störschall neigt es zu
  Fehlauslösungen.
- Projekt ist quasi eingefroren; Wheels für sehr neue Python-Versionen können
  klemmen (Build-Toolchain nötig).

**Grob-Umbau (klein):** identisch zu Silero (3.1), nur mit `webrtcvad.Vad()`
statt ONNX. Der billigste denkbare Schritt über RMS hinaus — aber wenn man
ohnehin eine Abhängigkeit hinzufügt, ist Silero meist die bessere Wahl.

---

### 3.3 TEN VAD — *der neue Herausforderer (2025)*

Fully-open-source VAD aus dem TEN-Framework, explizit als „stärker als WebRTC,
effizienter als Silero" positioniert. Frame-Level, 16 kHz, Hop-Größen 160/256
Samples (10/16 ms), C-Kern mit Python-Bindings.

**Vorteile**
- Laut Projekt bessere Präzision als Silero bei geringerer Rechenlast und
  kleinerer Library.
- Frame-Auflösung passt gut zu Cara; sprachunabhängig.
- Gleicher kleiner Umbau wie Silero.

**Nachteile**
- Jünger, kleinere Community, weniger „battle-tested" als Silero.
- Python-Bindings v.a. für Linux x64 optimiert — für **Windows** (deine
  Hauptplattform laut `pyproject`-Environments) genau prüfen, ob es ein
  brauchbares Wheel/Build gibt. Das kann ein K.o.-Kriterium sein.

**Grob-Umbau (klein):** wie 3.1. Interessant, wenn Silero zu ungenau/zu schwer
ist — aber erst die Windows-Verfügbarkeit klären.

---

### 3.4 Pipecat Smart Turn v3 *(deine Option 1)*

Semantischer Turn-Detektor: nimmt das Audio des laufenden Turns und schätzt, ob
der User **fertig** ist (Prosodie + Inhalt), statt nur Stille zu zählen. v3 baut
auf Whisper-Tiny + linearem Klassifikator (~8 M Parameter), ONNX/int8 ~8 MB,
23 Sprachen inkl. Deutsch. CPU-Inferenz ~12 ms (moderne CPU) bis <100 ms (billige
Cloud-Instanz).

**Vorteile**
- Löst das *richtige* Problem: „hat der User ausgeredet?" statt fester
  Stille-Timer. Weniger „ins-Wort-fallen" bei Denkpausen, schnelleres Reagieren
  bei klaren Satzenden.
- Vollständig lokal, CPU, klein, Deutsch offiziell dabei. Passt formatseitig
  perfekt (16 kHz mono).
- Reine ONNX-Inferenz — du kannst nur das *Modell* übernehmen, ohne das ganze
  Pipecat-Framework zu adoptieren.

**Nachteile**
- Braucht **darunter weiterhin eine VAD**, die die Pausen findet, an denen das
  Modell gefragt wird (Silero o.ä.). Es ist ein Aufsatz, kein Ersatz für VAD.
- Der Recorder muss von „einmal Stille → Ende" auf „bei jeder Pause Modell
  fragen → ggf. weiter aufnehmen" umgebaut werden (Zustandslogik statt
  Zähler). Mittlerer Aufwand.
- Zusätzliche ONNX-Abhängigkeit + Modell-Deployment.

**Grob-Umbau (mittel)**
1. Silero (oder TEN/WebRTC) als VAD-Schicht einziehen (Schritt 3.1).
2. Neuer Port `TurnDetector` mit `is_complete(utterance_pcm) -> bool` und eine
   `SmartTurnV3(TurnDetector)`-ONNX-Implementierung.
3. `MicrophoneRecorder` umbauen: fortlaufend Rohaudio des Turns puffern; wenn
   die VAD eine Pause meldet (z.B. ab ~200 ms Stille), das bisher Gesprochene an
   `is_complete` geben. `True` → beenden; `False` → weiter aufnehmen. Der feste
   `silence_seconds` wird zum *Fallback/Max-Wait*, nicht mehr zur
   Hauptentscheidung.
4. `record_until_silence` async lassen (ist es schon) — das Modell läuft in
   `run_in_executor`, damit die Loop nicht blockiert.

> Empfehlung, falls Turn-Qualität das Ziel ist: **Silero als VAD + Smart Turn v3
> als Aufsatz.** Beides lokal, beides klein, kein Framework-Lock-in.

---

### 3.5 LiveKit Turn Detector *(deine Option 2)*

Transformer-Turn-Modell, das Bedeutung + Prosodie kombiniert, mehrsprachig
(Deutsch dabei), lokale CPU-Variante vorhanden. Dokumentiertes Endpointing-Fenster
~0,3–2,5 s.

**Vorteile**
- Qualitativ in derselben Liga wie Smart Turn; ausgereift, produktiv im Einsatz.
- Mehrsprachig, lokal lauffähig.

**Nachteile**
- Das Modell ist eng in das **LiveKit-Agents-Framework** eingebettet
  (Sessions, Worker, Pipeline). Es „nur als Bibliotheksfunktion" herauszulösen
  ist deutlich unnatürlicher als bei Smart Turn (das explizit als reines
  ONNX-Modell angeboten wird).
- Für Cara würde das entweder einen **großen Infrastruktur-Umbau** bedeuten
  (Agent-Loop auf LiveKit-Muster umstellen) oder ein Herauslösen des Modells
  gegen die Intention des Projekts.

**Grob-Umbau (groß):** Entweder wie 3.4, aber mit mehr Reibung beim Isolieren
des Modells — oder eine grundlegende Umstellung der Agent-Infrastruktur. Für
Caras schlanke, selbst gebaute Loop (`assistant.py`) eher unattraktiv, solange
Smart Turn dieselbe Qualität mit weniger Kopplung bietet.

> Fazit: qualitativ top, aber für Caras Architektur der **schlechteste
> Aufwand/Nutzen** unter den lokalen Turn-Optionen. Nur sinnvoll, falls du
> ohnehin Richtung LiveKit-Stack willst.

---

### 3.6 OpenAI Realtime API `semantic_vad` — *die „gar-nicht-selbst-machen"-Option*

Da Cara STT/TTS ohnehin über OpenAI (via vocalbin) fährt, liegt es nahe: Die
**Realtime API** erledigt VAD *und* Turn-Detection serverseitig.
`turn_detection.type = "semantic_vad"` schätzt aus dem gesprochenen Inhalt, ob
der User fertig ist, und setzt den Timeout dynamisch (bei „ähm…" wartet es
länger). Alternativ `server_vad` (nur Energiebasiert, serverseitig).

**Vorteile**
- Keine eigene VAD/Turn-Logik, kein lokales Modell, kein Recorder-Umbau im
  Detail — die Pause-Erkennung wandert komplett zu OpenAI.
- Qualitativ hochwertige semantische Endpoint-Erkennung, Deutsch inklusive.
- Könnte mittelfristig STT+Turn+TTS in *einem* Stream vereinen (niedrigere
  End-to-End-Latenz).

**Nachteile**
- **Größter Architektur-Bruch:** Cara müsste von „aufnehmen → WAV → STT-Call"
  auf eine **persistente WebSocket-Streaming-Session** umsteigen. Das berührt
  `assistant.py`, den Recorder, die STT-Anbindung und die Barge-in-Logik.
- Nicht lokal: Datenschutz/Offline-Fähigkeit entfällt, laufende Kosten,
  Netz-Latenz und -Abhängigkeit.
- Verträgt sich schlecht mit dem bestehenden `openwakeword`-Wakeword-Flow und
  dem Earcon-/`ready`-Mechanismus, der eng auf das aktuelle
  Aufnahme-Modell zugeschnitten ist.

**Grob-Umbau (groß):** Neuer Streaming-Pfad statt `record_until_silence`; die
`SpeechRecorder`-Abstraktion würde eher zu einer „RealtimeSession". Eher ein
eigenes Projekt als ein VAD-Tausch. Nur sinnvoll, wenn du ohnehin über einen
Umstieg auf Realtime-Voice nachdenkst.

---

### 3.7 Picovoice Cobra (Randnotiz)

Proprietäres, sehr leichtes VAD (Free-Tier mit AccessKey). Qualitativ gut,
winzig, plattformübergreifend inkl. Windows. Einbau = kleiner VAD-Tausch wie
3.1. **Nachteil:** kein Open Source, AccessKey/Kontobindung — passt weniger zum
sonst offenen, lokalen Cara-Stack. Nur erwähnt der Vollständigkeit halber; Silero
ist bei gleichem Aufwand ohne Lizenzbindung.

---

## 4. Empfehlung

Zwei Fragen entscheiden:

**A) Ist das Problem „schneidet Wörter ab / triggert auf Rauschen"?**
→ Dann ist es ein **VAD-Problem**. Bau **Silero VAD** ein (Abschnitt 3.1).
Kleiner, isolierter, gut testbarer Umbau, sofort spürbar, kein Framework.

**B) Ist das Problem „fällt mir ins Wort / wartet zu lang bei Denkpausen"?**
→ Dann ist es ein **Turn-Problem**. Dann **Silero VAD + Smart Turn v3**
(Abschnitt 3.4). Smart Turn ist von deinen beiden recherchierten Optionen die
mit klar besserem Aufwand/Nutzen für Caras selbst gebaute Loop, weil es als
reines ONNX-Modell ohne Framework-Kopplung kommt — im Gegensatz zu LiveKit.

**Von OpenAI `semantic_vad` / Realtime** würde ich nur ausgehen, wenn du
ohnehin die gesamte Voice-Pipeline auf Streaming umstellen willst — sonst ist
der Architektur-Bruch unverhältnismäßig.

### Empfohlener Pfad in Etappen

1. **Etappe 1 (klein, sofort):** `VoiceActivityDetector`-Port einführen,
   `MicrophoneRecorder` von RMS auf **Silero** umstellen. Fester 1,2-s-Timer
   bleibt. Risiko niedrig, Tests bleiben grün (Fake-VAD injizierbar).
2. **Etappe 2 (mittel, optional):** `TurnDetector`-Port + **Smart Turn v3**
   obendrauf. Der Timer wird zum Fallback, die Endpoint-Entscheidung trifft das
   Modell an VAD-Pausen.

Beide Etappen hängen an genau einer Naht — `SpeechRecorder` /
`MicrophoneRecorder` — und lassen `assistant.py`, Wakeword, Earcons und
Barge-in unangetastet.

---

## Quellen

- [Pipecat Smart Turn (GitHub)](https://github.com/pipecat-ai/smart-turn)
- [Smart Turn Overview – Pipecat Docs](https://docs.pipecat.ai/api-reference/server/utilities/turn-detection/smart-turn-overview)
- [Announcing Smart Turn v3 – 12 ms CPU-Inferenz (Daily.co)](https://www.daily.co/blog/announcing-smart-turn-v3-with-cpu-inference-in-just-12ms/)
- [LiveKit Turn Detector Docs](https://docs.livekit.io/agents/logic/turns/turn-detector/)
- [Silero VAD (GitHub)](https://github.com/snakers4/silero-vad)
- [py-webrtcvad (GitHub)](https://github.com/wiseman/py-webrtcvad)
- [TEN VAD (Hugging Face)](https://huggingface.co/TEN-framework/ten-vad)
- [OpenAI Realtime VAD Guide](https://developers.openai.com/api/docs/guides/realtime-vad)
- [Picovoice Cobra VAD](https://picovoice.ai/platform/cobra/)
