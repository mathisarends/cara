# Voice-Client: Reconnect zum Gateway

## Ausgangslage

Wenn das Gateway neu startet (z. B. `1012 service restart`), passiert im Voice-Client heute Folgendes:

- `GatewayVoiceBridge` startet drei unabhängige Pumps (`voice-events`, `voice-conversation-events`, `voice-media`). Jeder Pump läuft über `_pump()`, das Fehler mit `logger.exception` loggt, den aktiven Turn aufgibt und dann **endet**. Danach empfängt der Client nichts mehr, bis der Prozess neu gestartet wird.
- Die beiden RPC-Streams hängen am selben `GatewayRpcClient` (eine WebSocket). Fällt sie weg, gibt es zwei Stacktraces für denselben Fehler.
- `MediaTransport.frames()` hat eine eigene, verdeckte Retry-Schleife (`sleep(0.25)` + `_connect()`). Solange das Gateway noch nicht wieder oben ist, wirft `_connect()` (`InvalidMessage`), und der Media-Pump stirbt trotzdem. Die Schleife verschleiert also nur den Fehler, statt ihn zu beheben.
- Während das Gateway weg ist, laufen Wake Word und Aktivierungen weiter. `_on_turn_requested` ruft `start_turn` über die tote RPC-Verbindung auf und scheitert. Hue schaltet beim Wake Word auf `LISTENING` und kommt nie zurück auf `IDLE`.
- Voice-Sessions und Turns speichert das Gateway in SQL, die laufenden STT/TTS-Tasks aber nur im Speicher. Nach einem Neustart kann in der DB also noch ein aktiver Turn stehen, für den nichts mehr läuft. Der nächste `start_turn` scheitert dann mit `VoiceTurnAlreadyActiveError`, und `_restore_active_turn` würde diesen verwaisten Turn sogar lokal wiederherstellen.
- Ist das Gateway schon beim Start nicht erreichbar, bricht `VoiceSessionFactory.create()` direkt ab.

## Ziel

1. Ein Verbindungsabbruch wird **einmal** erkannt und **einmal** sauber geloggt, egal wie viele Streams gleichzeitig sterben.
2. Es gibt zwei Lifecycle-Events, `GatewayDisconnected` und `GatewayReconnected`. Die Hue-Integration zeigt beide kurz an.
3. Der Client verbindet sich periodisch neu (exponentielles Backoff mit Jitter, unbegrenzt viele Versuche) und macht danach nahtlos mit derselben Voice-Session weiter.
4. Solange keine Verbindung besteht, werden Aktivierungen geordnet abgelehnt. Es gibt dann keine Folge-Stacktraces und keine hängenden Lichtzustände.

## Design

### Zuständigkeiten

| Komponente | Aufgabe |
| --- | --- |
| `MediaTransport` | Dummer Transport ohne eigene Retry-Schleife. Ein Socket-Fehler wird als Exception nach oben gereicht. |
| `GatewayVoiceSession` | Kennt die Verbindungsparameter und bekommt `reconnect()`: alte RPC- und Media-Verbindungen verwerfen, neu aufbauen, Snapshot neu laden. |
| `GatewayVoiceBridge` | Überwacht die Verbindung: startet die drei Pumps als Einheit, erkennt den ersten Fehler, emittiert die Events und steuert die Reconnect-Schleife. |
| `voice.events` / `VoiceIntegration` | Neue Events `GatewayDisconnected` / `GatewayReconnected` und die Hooks `on_gateway_disconnected` / `on_gateway_reconnected`. |
| `HueIntegration` | Kurzer Lichtpuls bei Verbindungsverlust und bei Wiederverbindung. Ein Wake Word im Offline-Zustand löst den Offline-Puls statt `LISTENING` aus. |

Der Reconnect sitzt bewusst in der Bridge und nicht versteckt im Transport. Nur die Bridge weiß, dass ein Abbruch den aktiven Turn beendet, dass Aktivierungen blockiert werden müssen und dass nach dem Reconnect die Pumps neu starten.

### 1. `MediaTransport` vereinfachen

`clients/voice/src/voice/gateway/media.py`

- Die Retry-Logik in `frames()` fällt weg. `frames()` liest vom aktuellen Socket und wirft bei `ConnectionClosed` bzw. anderen Socket-Fehlern weiter.
- `close()` bleibt idempotent. Ein bereits toter Socket darf beim Schließen nicht werfen (`ConnectionClosed` unterdrücken).

### 2. `GatewayVoiceSession.reconnect()`

`clients/voice/src/voice/gateway/session.py`

- `connect()` speichert `url`, `token`, `room`, `channel`, `inactivity_timeout_seconds` und die Audioformate auf der Instanz (privat). Die Logik zum Finden oder Öffnen der Voice-Session wandert in einen privaten Modul-Helper `_open_voice_session(rest, ...)`, den `connect()` und `reconnect()` gemeinsam nutzen.
- `async def reconnect(self) -> None`:
  1. Alte `rpc` und `media` schließen und dabei Fehler unterdrücken (sie sind ohnehin tot). Der `httpx`-Client bleibt bestehen.
  2. `rest.get_voice_session(self.id)`. Ist die Session nicht mehr `OPEN` oder unbekannt (404), wird über `_open_voice_session` für denselben Raum eine neue geöffnet. `new_session` gilt dabei **nie**: Ein Reconnect beginnt keine neue Konversation.
  3. `connect_gateway()` + `subscription.subscribe(session_id=...)`.
  4. Snapshot neu laden und `_snapshot` sowie `_last_sequence` ersetzen. Die Sequenzen liegen in der DB und bleiben monoton, deshalb ist das sicher.
  5. `MediaTransport.connect(...)` mit dem (eventuell neuen) `media_path`.
  6. Jeder Fehler auf diesem Weg wird geworfen, und die bereits aufgebauten Teilverbindungen werden wieder geschlossen (gleiches Muster wie in `connect()`).
- Ändern sich Sample-Raten zwischen alter und neuer Session, ist das ein harter Fehler (`RuntimeError`), weil der Channel die Formate beim Aufbau fest verdrahtet. Mit unveränderter `voice.yml` sollte das nicht vorkommen.
- `close()`: `rest.close_voice_session` darf bei nicht erreichbarem Gateway den Shutdown nicht mit einer Exception abbrechen. Deshalb wird der Fehler geloggt (Warning, ohne Traceback) und unterdrückt, die restlichen Ressourcen werden trotzdem freigegeben.

### 3. Verbindungsüberwachung in `GatewayVoiceBridge`

`clients/voice/src/voice/gateway/bridge.py`

Statt drei unabhängiger Tasks gibt es einen Supervisor-Task `voice-gateway-connection`:

```python
async def _supervise_connection(self) -> None:
    while not self._closed:
        error = await self._run_streams()          # returns on first failure
        if self._closed:
            return
        await self._connection_lost(error)
        await self._reconnect_until_connected()
        await self._connection_restored()
```

- **`_run_streams()`** startet die drei Pumps und wartet mit `asyncio.wait(..., return_when=FIRST_COMPLETED)`. Sobald ein Pump endet (Fehler oder regulär), werden die anderen gecancelt und eingesammelt. Das ersetzt das heutige `_pump()`.
  - Endet der Voice-Event-Stream regulär mit `VoiceSessionClosed`, ist das **kein** Reconnect-Fall. Die Session wurde dann absichtlich geschlossen. Der Supervisor endet, und die heutige Semantik bleibt erhalten (siehe offene Punkte).
- **`_connection_lost(error)`**:
  - `self._connected = False`.
  - Logging, genau einmal pro Ausfall:
    - Erwartete Verbindungsfehler (`RpcTransportError`, `websockets.ConnectionClosed`, `websockets.InvalidHandshake`/`InvalidMessage`, `OSError`, `httpx2.TransportError`) werden als `logger.warning("Lost the gateway connection: %s", _describe(error))` **ohne** Stacktrace geloggt. `_describe` läuft die `__cause__`-Kette bis zur eigentlichen Ursache ab (z. B. `received 1012 (service restart)`).
    - Alles andere (Protokollverletzung, Bug) läuft über `logger.exception(...)` und löst trotzdem einen Reconnect aus.
  - `_abandon_active_turn("gateway connection lost")`, damit Audio, Input-Upload und die lokalen Turn-Zustände freigegeben werden.
  - `await self._event_bus.emit(GatewayDisconnected(reason=...))`.
- **`_reconnect_until_connected()`**:
  - Die Backoff-Schleife ruft `self._session.reconnect()` auf. Die Wartezeit beginnt bei `initial_delay`, wird verdoppelt bis `max_delay` und bekommt ±20 % Jitter.
  - Jeder fehlgeschlagene Versuch wird auf `INFO` geloggt: `"Gateway reconnect attempt %d failed (%s); retrying in %.1fs"`. Kein Traceback bei erwarteten Fehlern, bei unerwarteten `logger.exception`.
  - Die Schleife muss sauber cancelbar sein, weil `close()` den Supervisor-Task cancelt.
- **`_connection_restored()`**:
  - Den verwaisten Turn aufräumen: Meldet der neue Snapshot ein `active_turn`, wird er per `session.interrupt(turn_id, None)` beendet und **nicht** über `_restore_active_turn` wiederhergestellt. Nach einem Gateway-Neustart laufen dafür keine Tasks mehr, und lokal wurde der Turn bereits aufgegeben.
  - `self._connected = True`.
  - `logger.info("Reconnected to the gateway after %.1fs (%d attempts)", ...)`.
  - `await self._event_bus.emit(GatewayReconnected(downtime_seconds=..., attempts=...))`.
- **`start()`** behält `_restore_active_turn()` für den initialen Start (Client-Neustart bei laufendem Gateway) und startet danach den Supervisor statt der drei Pumps.
- **Guards, solange `_connected is False`**:
  - `_on_turn_requested`: `logger.info("Ignoring the %s activation: the gateway is unreachable", ...)` und `return`. Es wird kein Event emittiert, weil der Zustand schon über `GatewayDisconnected` bekannt ist.
  - `_on_playback_completed`: Das Melden wird übersprungen (der Turn ist ohnehin aufgegeben).
  - `interrupt()`: Ohne Verbindung wird kein RPC gesendet, lokal wird nur aufgeräumt.
  - `_on_session_ended`: Das bestehende `suppress(Exception)` reicht aus.
- Race-Schutz: `_connected` wird unter `_turn_lock` gesetzt, damit keine Aktivierung zwischen Abbruch und Aufgabe des Turns noch einen neuen Turn startet.

### 4. Konfiguration

`clients/voice/src/voice/config/settings.py`

```yaml
gateway:
  url: http://127.0.0.1:8000
  reconnect:
    initial_delay_seconds: 1.0
    max_delay_seconds: 30.0
```

- Neues `GatewayReconnectConfig(_ConfigModel)` mit `initial_delay_seconds: float = Field(default=1.0, gt=0)` und `max_delay_seconds: float = Field(default=30.0, gt=0)`, dazu ein Validator `max >= initial`.
- `GatewayConfig.reconnect: GatewayReconnectConfig = Field(default_factory=...)`. `_validate_document_root` kennt das Feld dadurch automatisch.
- `VoiceSessionFactory` und `VoiceChannel` reichen die Werte an `GatewayVoiceBridge` weiter (Keyword-Argumente `reconnect_initial_delay` / `reconnect_max_delay`, ohne öffentliches Settings-Objekt, siehe CLAUDE.md).
- Die Backoff-Berechnung wird ein privater Modul-Helper in `bridge.py` (oder ein eigenes kleines Modul `voice/gateway/backoff.py`, falls der Startup-Retry aus Schritt 7 ihn ebenfalls braucht).

### 5. Events und Integration-Hooks

`clients/voice/src/voice/events/models.py`

```python
class GatewayDisconnected(Event):
    """Emitted once when the gateway connection is lost."""

    reason: str


class GatewayReconnected(Event):
    downtime_seconds: float
    attempts: int
```

- Die beiden Events kommen in `voice/events/__init__.py` in `__all__`, weil Integrationen außerhalb des Pakets sie konsumieren.
- **Keine** Events für einzelne Reconnect-Versuche. Das sind interne Zustandsübergänge (CLAUDE.md), sie gehören ins Log.
- `VoiceIntegration` bekommt `async def on_gateway_disconnected(self, reason: str) -> None: ...` und `async def on_gateway_reconnected(self) -> None: ...`. `VoiceIntegrationBridge.setup()` verdrahtet beide.
- `LoggingListener` / `EventTrace` prüfen, ob die neuen Events dort auftauchen sollen. Das Logging passiert in der Bridge, also vermutlich nur der Trace.

### 6. Hue-Anzeige

`clients/voice/src/voice/lights/...`

- `LightingState.DISCONNECTED` mit einem deutlich sichtbaren Effekt in `effects.py`, z. B. `brightness_delta=-35`, `temperature_delta=+20` (dunkler und wärmer, klar anders als die übrigen Zustände), und kurzer Transition (`0.3`).
- `HueIntegration`:
  - `_gateway_connected: bool = True` (privat).
  - `on_gateway_disconnected`: `_gateway_connected = False` und `_submit_pulse(LightingState.DISCONNECTED, repeats=2)`. Ein Puls ist `DISCONNECTED` → kurze Pause (~0.6 s) → `IDLE`, zweimal hintereinander. Er läuft als Job in der bestehenden Queue, damit er nicht mit anderen Zustandswechseln kollidiert.
  - `on_gateway_reconnected`: `_gateway_connected = True`, ein einzelner kurzer `LISTENING`-Puls (heller/kühler), danach `IDLE`. So ist sichtbar, dass Cara wieder da ist.
  - `on_wake_word_detected`: Ist `_gateway_connected` `False`, kommt der Offline-Puls statt `LISTENING`. Wer „Hey Mycroft“ sagt, während das Gateway weg ist, sieht also sofort, warum nichts passiert.
  - `on_agent_error` setzt weiterhin `IDLE`. Der Disconnect-Puls kommt danach und überschreibt das.
- `HueRoomLighting` bleibt unverändert. Der Puls ist nur eine Folge von `set_state`-Aufrufen mit `asyncio.sleep` dazwischen, innerhalb eines Jobs.
- Optional und nicht Teil dieses Plans: `SoundIntegration` spielt beim Wake Word im Offline-Zustand einen Fehlerton.

### 7. Startup ohne Gateway (empfohlen, klein)

`clients/voice/src/voice/factory.py`

- `_connect_gateway()` versucht `GatewayVoiceSession.connect(...)` mit demselben Backoff und denselben Log-Meldungen, bis es klappt. Heute stürzt der Client ab, wenn er vor dem Gateway startet (z. B. nach einem Reboot des Hosts).
- Dabei wird **kein** `GatewayDisconnected`-Event emittiert: Es gibt noch keinen Channel und keinen Event-Bus, und Hue ist noch nicht vorbereitet. Log-Ausgabe reicht.

### 8. Gateway: verwaiste Turns beim Start aufräumen (empfohlen, separat)

Die clientseitige Bereinigung in `_connection_restored()` behebt das Symptom für diesen Client. Sauberer ist es, wenn das Gateway beim Start alle `active_turn`s offener Voice-Sessions mit `reason="gateway_restart"` abbricht. Nach einem Neustart können dafür nachweislich keine Tasks mehr laufen. Das gehört als eigener kleiner Schritt in `gateway/src/gateway/features/voice/application/voice_turn_service.py` (Startup-Hook im `VoiceProvider`). Der Client-Code aus Schritt 3 bleibt trotzdem als Absicherung drin.

## Tests

`clients/voice/tests/gateway/test_bridge.py` (Fake-Session wie bisher):

- Ein Stream wirft `RpcTransportError`: `GatewayDisconnected` wird genau **einmal** emittiert, auch wenn beide RPC-Streams gleichzeitig sterben. Der aktive Turn endet mit `VoiceTurnFailed` + `VoiceTurnEnded`.
- `reconnect()` schlägt zweimal fehl und klappt beim dritten Mal: `GatewayReconnected(attempts=3)`. Die Wartezeiten wachsen, begrenzt durch `max_delay`. Dafür wird ein injizierbares `sleep` genutzt oder Delays im Millisekundenbereich.
- Aktivierung während des Offline-Zustands: `start_turn` wird nicht aufgerufen, keine Exception.
- Nach dem Reconnect mit `active_turn` im Snapshot: `interrupt(turn_id, None)` wird aufgerufen, kein lokaler Restore.
- `close()` während der Backoff-Schleife beendet den Supervisor sofort.
- `VoiceSessionClosed` löst keinen Reconnect aus.
- Erwartete Transportfehler werden ohne Traceback geloggt (`caplog`, `record.exc_info is None`), unerwartete mit Traceback.

`clients/voice/tests/test_hue_integration.py`:

- Disconnect → Puls-Sequenz `DISCONNECTED, IDLE, DISCONNECTED, IDLE`.
- Wake Word im Offline-Zustand → Offline-Puls statt `LISTENING`.
- Reconnect → kurzer Puls, danach `IDLE`, und das Wake Word setzt wieder `LISTENING`.

`clients/voice/tests/gateway/` (neu, falls noch nicht vorhanden):

- `MediaTransport.frames()` wirft bei geschlossenem Socket, statt intern neu zu verbinden.

`clients/voice/tests/config/test_settings.py`:

- Defaults für `gateway.reconnect`, `max < initial` wird abgelehnt.

Manueller Test: Voice-Client laufen lassen, das Gateway neu starten (auch mitten in einer Antwort) und dabei auf Log, Hue und die erste Aktivierung nach dem Reconnect achten.

## Reihenfolge

1. `MediaTransport` vereinfachen (Schritt 1).
2. `GatewayVoiceSession.reconnect()` + robustes `close()` (Schritt 2).
3. Events + Integration-Hooks (Schritt 5).
4. Supervisor in der Bridge + Config (Schritte 3 + 4) mit Tests.
5. Hue-Pulse (Schritt 6) mit Tests.
6. Startup-Retry (Schritt 7).
7. Separat: Aufräumen verwaister Turns im Gateway (Schritt 8).

## Offene Punkte

- **`VoiceSessionClosed` vom Gateway**: Wird die Voice-Session z. B. über die REST-API geschlossen, endet heute nur der Event-Pump, und der Client bleibt halb lebendig. Soll der Channel dann ganz stoppen oder über `_open_voice_session` eine neue Session öffnen? Vorschlag: vorerst unverändert lassen und separat entscheiden.
- **Laufende Wiedergabe beim Abbruch**: Bereits gepufferte Assistant-Audio-Chunks spielen lokal eventuell noch zu Ende. `VoiceTurnFailed` sollte die Wiedergabe über den bestehenden `AudioBridge` stoppen. Das muss im manuellen Test geprüft werden.
- **Puls-Parameter** (Deltas, Dauer, Wiederholungen) werden am echten Raum getuned. Eine Konfiguration in `voice.yml` lohnt sich erst, wenn sich die Werte als unpassend herausstellen.
