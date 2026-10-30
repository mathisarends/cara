# Voice im Room-Prozess

## Ziel

Jeder physische Raum läuft als eigener Python-Prozess. Dieser Room-Prozess besitzt
eine stabile `room_id`, meldet sich beim Gateway an und hält seine Verbindung
selbstständig aufrecht.

Voice wird in denselben Prozess eingebettet. Die bestehende `voice`-Package bleibt
inhaltlich weitgehend unverändert, wird aber von `clients/voice` nach `libs/voice`
verschoben und durch den Room-Prozess als interne Library gestartet.

Das erste Ziel ist bewusst klein:

- ein Room entspricht genau einem laufenden Prozess;
- der Room registriert sich beim Gateway;
- der Room hält die Gateway-Verbindung durch Heartbeats aktiv;
- der Room verbindet sich nach einem Abbruch erneut;
- jeder Room startet seine bestehende Voice-Runtime im selben Prozess.

## Nicht-Ziele

Diese Spec erweitert noch nicht den fachlichen Kontext von Voice-Turns. Insbesondere
sind zunächst nicht Teil der Umsetzung:

- die Weitergabe der `room_id` an den Agenten oder dessen Prompt;
- ein `RoomContext` oder allgemeines `AgentTurnContext`-Modell;
- Änderungen an Conversation-Sessions für Raumkontext;
- eine allgemeine Media-, Geräte- oder Capability-Architektur;
- Kameras oder andere zukünftige Eingabekanäle;
- eine neue Embodiment-Abstraktion für Licht, Earcons oder Displays;
- eine grundlegende Umgestaltung von STT, TTS, Barge-in oder Audio-Fokus;
- eine Migration des bestehenden Voice-Session-Vertrags von `room` auf `room_id`.

Diese Themen können später in eigenen, kleineren Specs ergänzt werden. Die jetzige
Integration soll dafür keine vorweggenommene Abstraktion einführen.

## Zielarchitektur

```text
Room-Prozess
├── Room(room_id)
├── Gateway-Verbindung
│   ├── Registrierung
│   ├── Heartbeats
│   └── Reconnect
└── Voice-Runtime
    └── libs/voice
```

Der Room-Prozess ist der Composition Root und Lifecycle-Owner. Er startet und
beendet sowohl die Gateway-Verbindung als auch die Voice-Runtime. Ein separater
Voice-Prozess entfällt nach der Migration.

## 1. Ein Room ist ein Prozess

Jeder konfigurierte physische Raum wird durch genau einen langlebigen Room-Prozess
repräsentiert. Seine `room_id` ist stabil und wird nicht bei jedem Prozessstart neu
erzeugt.

Der Prozess besitzt zwei wesentliche Laufzeitbestandteile:

1. die Verbindung des Rooms zum Gateway;
2. die lokale Voice-Runtime.

Die `Room`-Domain selbst bleibt klein. Laufende Tasks, Netzwerkverbindungen und
Audio-Handles werden nicht in das Domainobjekt gelegt. Application-Komponenten
orchestrieren deren Lifecycle.

## 2. Registrierung beim Gateway

Beim Start meldet der Prozess den Room über den bereits vorhandenen
Registrierungsvertrag beim Gateway an. Die Registrierung verwendet die konfigurierte
`room_id` und die bereits vorhandenen Room-Daten.

Für diesen Schritt wird kein neues Capability-Modell eingeführt. Dass der Prozess
Voice startet, muss nicht zusätzlich als dynamische Room-Capability modelliert
werden.

Die Registrierung muss erfolgreich abgeschlossen sein, bevor der Room als ready
gilt. Schlägt sie fehl, versucht der Prozess die Verbindung kontrolliert erneut,
anstatt mit einem teilweise verbundenen Zustand weiterzulaufen.

## 3. Langlebige Gateway-Verbindung

Nach der Registrierung öffnet der Room seine bestehende langlebige Verbindung zum
Gateway. Diese Verbindung ist die zentrale Schnittstelle für Erreichbarkeit und
Room-Zustand.

### Heartbeats

- Der Room sendet in einem konfigurierten Intervall Heartbeats.
- Ein Heartbeat bestätigt, dass derselbe Room-Prozess weiterhin erreichbar ist.
- Das Intervall stammt aus der Room-Konfiguration.
- Es wird kein zweiter Heartbeat-Mechanismus für Voice eingeführt.

### Reconnect

Wenn die Gateway-Verbindung abbricht:

1. wird der Verbindungsverlust erkannt und geloggt;
2. der Room gilt nicht mehr als ready;
3. der Prozess versucht mit begrenztem Backoff eine neue Verbindung aufzubauen;
4. falls das Gateway es verlangt, registriert sich der Room erneut;
5. nach erfolgreicher Wiederherstellung gilt der Room wieder als ready.

Der Reconnect läuft im bestehenden Room-Prozess. Ein Verbindungsfehler darf nicht
dazu führen, dass ein zweiter Prozess oder eine zweite konkurrierende Connection für
denselben Room gestartet wird.

Die konkrete Backoff-Strategie soll einfach bleiben und vorhandene Mechanismen
verwenden. Dafür wird keine allgemeine Connection-Management-Framework-Abstraktion
eingeführt.

## 4. Voice wird eine interne Library

Die bestehende Package wird vollständig von `clients/voice` nach `libs/voice`
verschoben. Ihr Python-Package-Name `voice` kann bestehen bleiben.

Bei der Verschiebung werden aktualisiert:

- Workspace-Metadaten;
- Projektabhängigkeiten;
- Imports und Einstiegspunkte;
- Tests und Testpfade;
- Dokumentation und Beispielkonfigurationen.

Unter `clients/voice` bleibt keine Übergangskopie und kein Kompatibilitätsalias
zurück.

Die Voice-Logik wird in diesem Schritt nicht fachlich neu entworfen. Wake Word,
Audio, Barge-in, bestehender Audio-Fokus und vorhandene Integrationen dürfen zunächst
so weiterarbeiten wie bisher. Entscheidend ist nur, dass der Room-Prozess die
Library komponiert und ihren Lifecycle besitzt.

Eine kleine Application-Komponente, beispielsweise `RoomVoiceService`, darf die
Voice-Runtime hinter einem einfachen Start-/Stop-Vertrag kapseln. Sie soll keine
neue Capability-, Media- oder Embodiment-Hierarchie einführen.

## 5. Gemeinsamer Prozess-Lifecycle

### Start

1. Der Room-Prozess lädt und validiert seine Konfiguration.
2. Er erstellt den `Room` mit der konfigurierten `room_id`.
3. Er initialisiert die Voice-Runtime aus `libs/voice`.
4. Er registriert den Room beim Gateway.
5. Er öffnet die langlebige Gateway-Verbindung und startet die Heartbeats.
6. Sobald Gateway-Verbindung und Voice-Runtime bereit sind, wird der Prozess ready.

Voice darf bereits initialisiert werden, bevor die Gateway-Verbindung steht, aber
neue Voice-Aktivierungen werden erst angenommen, wenn der Gesamtprozess ready ist.

### Laufzeit

- Gateway-Verbindung und Heartbeat-Task werden überwacht.
- Ein Abbruch startet den Reconnect innerhalb desselben Prozesses.
- Die Voice-Runtime bleibt Bestandteil desselben Lifecycles.
- Readiness bildet ab, ob der Room seine Kernfunktion gerade erfüllen kann.

### Beenden

1. Keine neuen Voice-Aktivierungen mehr annehmen.
2. Die Voice-Runtime kontrolliert beenden.
3. Heartbeat- und Reconnect-Tasks beenden.
4. Die Gateway-Verbindung schließen.

Das Aufräumen muss nach vollständigem wie auch nach partiellem Start idempotent sein.

## 6. Konfiguration

Der Room-Prozess erhält die bestehende Room- und Voice-Konfiguration. Eine große
Konfigurationsmigration ist nicht Teil dieser Spec.

Erforderlich sind mindestens:

- eine stabile `room_id`;
- Gateway-URL und Token;
- das Heartbeat-Intervall;
- die bisherigen Voice-Einstellungen.

Die Konfiguration darf während der ersten Integration intern noch aus bestehenden
Settings zusammengesetzt werden. Entscheidend ist, dass nur der Room-Prozess als
ausführbare Anwendung gestartet wird. Eine spätere Zusammenführung der Dateien kann
getrennt geplant werden.

## 7. Lokale HTTP-Routen

Die lokalen Routen `GET /room` und `GET /devices` werden für Registrierung,
Heartbeats und Reconnect nicht benötigt. Der Room meldet seine Daten aktiv über die
Gateway-Verbindung.

Deshalb gilt:

- `GET /room` und `GET /devices` sowie ausschließlich dafür vorhandene Schemas und
  Tests können entfernt werden;
- lokale Health- und Readiness-Endpunkte bleiben als Betriebsoberfläche bestehen;
- eine lokale Room- oder Geräte-API wird erst ergänzt, wenn ein konkreter Consumer
  sie benötigt.

## 8. Umsetzungsschnitte

### Slice 1: Gateway-Lifecycle vervollständigen

- Den bestehenden Ablauf für Registrierung und Verbindungsaufbau eindeutig
  orchestrieren.
- Heartbeats an den Lifecycle der aktiven Verbindung binden.
- Verbindungsverlust erkennen und Readiness zurücknehmen.
- Reconnect mit einfachem Backoff ergänzen.
- Nach Reconnect bei Bedarf erneut registrieren.
- Shutdown und partiellen Startup idempotent aufräumen.

### Slice 2: Voice-Package nach `libs` verschieben

- `clients/voice` vollständig nach `libs/voice` verschieben.
- Workspace, Abhängigkeiten, Imports, Tests und Dokumentation aktualisieren.
- Sicherstellen, dass die bestehenden Voice-Tests am neuen Ort weiterhin laufen.
- Keine Kompatibilitätsschicht am alten Pfad behalten.

### Slice 3: Voice in den Room-Prozess einbetten

- Den Room von `libs/voice` abhängig machen.
- Eine kleine `RoomVoiceService` für Start, Readiness und Shutdown ergänzen.
- Die bestehende Voice-Konfiguration an die Library übergeben.
- Voice-Aktivierungen an die Readiness des Room-Prozesses koppeln.
- Den separaten Voice-Entrypoint entfernen, sobald der Room-Prozess dasselbe
  Verhalten bereitstellt.

### Slice 4: Lokale Oberfläche bereinigen

- Nicht benötigte lokale `GET /room`- und `GET /devices`-Routen entfernen.
- Health und Readiness behalten.
- Startanweisungen und Beispiele auf einen Prozess pro Room aktualisieren.

## 9. Akzeptanzkriterien

Die Integration ist abgeschlossen, wenn:

1. Jeder konfigurierte Room als eigener Python-Prozess läuft.
2. Der Prozess eine stabile `room_id` verwendet und sich damit beim Gateway
   registriert.
3. Der Room seine Gateway-Verbindung durch Heartbeats aktiv hält.
4. Nach einem Verbindungsabbruch die Readiness zurückgenommen und die Verbindung
   kontrolliert wiederhergestellt wird.
5. Ein Reconnect keine konkurrierenden Verbindungen oder Hintergrundtasks erzeugt.
6. Die Voice-Runtime im selben Prozess wie der Room läuft.
7. Die bestehende Voice-Funktionalität nach der Einbettung weiterhin funktioniert.
8. Die `voice`-Package unter `libs/voice` liegt und unter `clients/voice` keine
   Übergangskopie verbleibt.
9. Ohne Gateway-Verbindung oder funktionsfähige Voice-Runtime der Room-Prozess nicht
   ready ist.
10. Startup und Shutdown auch nach einem partiellen Fehler sauber und idempotent
    sind.
11. Kein separater Voice-Prozess mehr erforderlich ist.
12. Für diese Integration weder Agent-Kontext noch Media-, Kamera- oder
    Embodiment-Abstraktionen vorausgesetzt werden.

## Architekturentscheidungen

- **Ein Room ist ein Prozess.** Jeder physische Raum hat einen eigenen langlebigen
  Python-Prozess.
- **Die Gateway-Verbindung ist der Kernvertrag.** Registrierung, Heartbeats und
  Reconnect machen den Room für das Gateway erreichbar.
- **Voice läuft im Room-Prozess.** Der Room besitzt den Lifecycle der vorhandenen
  Voice-Runtime.
- **Voice liegt unter `libs/voice`.** Die Package ist eine interne Library und kein
  eigenständiger Client.
- **Readiness umfasst Gateway und Voice.** Der Prozess ist nur ready, wenn seine
  Kernbestandteile verwendbar sind.
- **Room-Kontext für den Agenten wird vertagt.** Die `room_id` wird in dieser Spec
  weder durch Voice-Turns gereicht noch in den Agent-Prompt eingefügt.
- **Media, Kamera und Embodiment werden vertagt.** Dafür entstehen erst bei einem
  konkreten Bedarf eigene Abstraktionen.
