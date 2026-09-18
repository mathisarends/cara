# pyrpckit 0.5.0 – Feedback aus der Cara-Migration

Kontext: Migration von 0.4 auf 0.5 im Cara Gateway (FastAPI + Dishka, ein
JSON-RPC-WebSocket `/v1/gateway`, 13 Methoden, 2 Event-Streams, generierter
Python-Client für CLI und Voice-Client). Stand 2026-09-18.

Kurzfazit: 0.5 ist ein klarer Schritt nach vorn. `RpcService` +
Connect-Hook + Library-Runtime haben rund 200 Zeilen Cara-eigenen
Verbindungscode (`GatewayConnection`, `EventForwarder`) ersetzt, und typisierte
Fehler im Client machen Magic-Numbers überflüssig. Es gibt aber einen echten Bug
(siehe 1) und einige Ergonomie-Kanten beim Einbetten in eine bestehende
FastAPI/Dishka-App.

---

## 1. Bug: `CancelledError` beim Verbindungsende unter Starlettes `TestClient`

**Schwere: hoch.** Betrifft jeden, der pyrpckit + FastAPI mit dem Standard-TestClient testet.

Minimal-Reproduktion ohne Cara-Code:

```python
ch = rpc.RpcChannel("demo")

@ch.method
async def echo(params: P) -> R: ...

service = rpc.RpcService()
service.socket("/ws", ch)
app = FastAPI()
app.include_router(create_router(service))

with TestClient(app) as client:
    for i in range(200):
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"jsonrpc": "2.0", "id": 1, "method": "demo.echo", "params": {"x": i}})
            ws.receive_json()
```

Ergebnis: **111 von 200** Sessions enden beim Verlassen des `with`-Blocks mit
`concurrent.futures.CancelledError`. Mit einem Event-Source auf dem Channel sind
es 76 von 200.

Analyse:
- Starlettes `WebSocketTestSession.__exit__` schickt `websocket.disconnect` und
  cancelt direkt danach den anyio-`CancelScope` der App.
- `serve_endpoint` erkennt den Disconnect im *Reader-Task*, setzt ein Event, und
  der Haupt-Task braucht dann noch mehrere Loop-Runden, um aufzuräumen:
  Hintergrund-Tasks canceln und in `runtime.py:190` per
  `gather(..., return_exceptions=True)` einsammeln, danach die Scopes schließen.
- In diesem Fenster trifft der anyio-Cancel. Instrumentiert: Der Abbruch passiert
  in `serve_endpoint:190`, und in einem Teil der Fälle entkommt der
  `CancelledError` dem Cancel-Scope des Hosts.
- Der alte, handgeschriebene Loop (Disconnect direkt im App-Task behandelt,
  sofort return) war davon nicht betroffen.

Vorschläge:
- Disconnect im Haupt-Task behandeln bzw. nach `RpcDisconnect` ohne weitere
  ungeschützte Awaits zurückkehren.
- Cleanup nach Cancellation nicht mehr awaiten (oder shielden).
- Einen Regressionstest mit `fastapi.testclient.TestClient` in einer Schleife
  in die Library-Suite aufnehmen.

Workaround in Cara: RPC-Verhaltenstests laufen über `RpcTestClient` im Portal
der App (`client.portal.call(...)`), nur die Auth-Denial-Tests über den echten
Socket.

## 2. Einbettung in FastAPI + Dishka

### 2a. `create_router()` braucht den Resolver zur Definitionszeit
`create_router(service, resolver=...)` erwartet den Resolver schon beim Bau des
Routers. Mit Dishka (und Frameworks wie fastapi-canon) existiert der Container
aber erst, wenn die App zusammengesetzt ist. Deshalb nutzt Cara `create_router`
nicht, sondern eine eigene Route:

```python
@gateway_router.websocket(gateway_endpoint.path)
async def gateway_socket(websocket: WebSocket) -> None:
    await gateway_endpoint.serve(
        FastApiSocket(websocket),
        resolver=DishkaResolver(websocket.app.state.dishka_container),
        error_mapper=gateway_error_mapper,
    )
```

Wunsch: `resolver` auch als Factory `Callable[[WebSocket], RpcResolver]`
akzeptieren, oder eine Dishka-FastAPI-Integration, die den Container aus
`app.state` holt.

### 2b. `DishkaResolver` öffnet immer selbst einen SESSION-Scope
Dishkas FastAPI-Middleware öffnet für jeden WebSocket schon einen SESSION-Container
(`websocket.state.dishka_container`). `DishkaResolver.enter_connection` will
zwingend den APP-Container und öffnet einen *zweiten* SESSION-Scope. Man muss
wissen, dass man bewusst am Socket-Container vorbei auf `app.state` greift
(bei Cara steht dafür ein Kommentar im Code). Wunsch: Ein Modus, der einen
bereits geöffneten SESSION-Container übernimmt, und klare Doku dazu.

### 2c. `error_mapper` hängt am Serve-Aufruf statt am Service
Resolver, `error_mapper` und `limits` müssen bei *jedem* `serve()` übergeben
werden: in der Route, im `RpcTestClient` und in `create_router`. In Cara musste
der Testcode die Router-Konfiguration dadurch 1:1 duplizieren (Drift-Risiko).
Wunsch: `RpcService(error_mapper=...)` bzw. am `socket(...)`-Endpoint, analog
zum `connect`-Hook.

## 3. Channels und Namen

- **Namespace pro Channel ist gut**, bricht aber Punkte in Methodennamen.
  `@channel.method("turn.prepare")` ist jetzt ein `ProtocolDefinitionError`.
  Für `voice.turn.start` und `voice.event` braucht man zwei Channels
  (`RpcChannel("voice_turn", namespace="voice.turn")` und `RpcChannel("voice")`).
  Das funktioniert, ist aber nicht offensichtlich. Die Fehlermeldung
  `Invalid RPC method name: 'turn.prepare'` könnte auf `namespace=` hinweisen.
- **Channel-Name vs. Namespace:** Der Channel-Name muss service-weit eindeutig
  und segment-gültig sein, auch wenn er nie auf dem Wire auftaucht
  (`"voice_turn"`). Ein optionaler Name, der aus dem Namespace abgeleitet wird,
  würde reichen.
- **Positiv:** `raises=` auf Channel-Ebene. `ResourceNotFoundError` einmal pro
  Channel statt an jeder Methode.
- **Positiv:** Die Built-in-Fehler (`RpcInvalidParamsError`, `RpcInternalError`)
  sind implizit. Es entfallen ~15 redundante Deklarationen.
- **Kante:** `payload=` bei `@channel.event` ist redundant zur
  `AsyncIterator[T]`-Annotation. Gut, dass es optional ist. Die Doku sollte das
  als Default zeigen.

## 4. Fehler

- **Positiv:** Stabile String-Codes, aus dem Klassennamen abgeleitet
  (`NoActiveTurnError` → `no_active_turn`, Message „No active turn“). Ein Großteil
  der Fehlerklassen ist jetzt eine Zeile, und der generierte Client hat echte
  Exception-Klassen. Die CLI fängt `NoActiveTurnError` statt `error.code != -32010`.
- **Breaking-Falle:** `RpcRemoteError.code` war früher die Zahl und ist jetzt der
  String-Code (die Zahl heißt `rpc_code`). Code wie `if error.code != -32010`
  kompiliert weiter, ist aber still immer wahr. Das gehört als eigener Punkt ins
  Changelog.
- **Kante bei Suffixen:** Die Ableitung entfernt nur `Error`. Cara benennt
  RPC-Fehler mit `...RpcError`, um sie von Domain-Fehlern zu unterscheiden, und
  bekäme `voice_turn_already_active_rpc`. Man muss `code =` explicit setzen.
  Eventuell `RpcError` als Suffix ebenfalls strippen.
- **Unhandlich:** Einen `RpcInvalidParamsError` aus einem Domain-`ValueError`
  zu mappen braucht `RpcInvalidParamsError(issues=[], message=...)`. `issues`
  ist Pflicht, obwohl es keine Pydantic-Issues gibt. Ein Default `issues=[]`
  wäre angenehmer.
- **Positional vs. Keyword:** Der erste Positionsparameter von `RpcError` ist
  jetzt `details`. `ResourceNotFoundError("Not found: x")` (alter Stil) ergibt
  einen `TypeError: ... does not accept details`. Die Meldung könnte
  „did you mean `message=`?“ vorschlagen.
- **Fehler-Envelope:** `data: {"code": ..., "details": null}` wird jetzt immer
  mitgeschickt, auch beim Parse-Error. Das ist ok, aber eine sichtbare
  Wire-Änderung für Clients, die exakt vergleichen.

## 5. Verbindungs-Lifecycle

- **Positiv:** Connect-Hook mit `RpcConnection` + `Inject[T]` +
  `ConnectionRejected(RpcRejection.UNAUTHORIZED)` ist genau das richtige Modell
  für Auth. Rejection als HTTP 401 (Denial-Response) statt Close 1008 ist
  semantisch besser.
  - Aber es ist eine Verhaltensänderung: Clients sehen jetzt einen
    Handshake-Fehler statt eines Close-Frames. Das sollte im Changelog stehen.
- **Positiv:** Event-Sources werden von der Runtime betrieben. In 0.4 hatte Cara
  die Events *zweimal*: einmal als `@module.event` nur fürs Schema und einmal als
  eigener `EventForwarder`, der tatsächlich gesendet hat.
- **Fehlt: serverseitige Request-Hooks.** Der Changelog nennt Request-Hooks nur
  für generierte Clients. Cara hatte pro RPC ein Log mit Methode, ID, Outcome
  und Dauer. Mit der Library-Runtime gibt es dafür keinen Einhängepunkt, und das
  Log ist bei der Migration entfallen. Wunsch: `on_request`/`on_response`-Hooks
  oder eine Middleware am Service/Endpoint.
- **Fehlt: Close-Info.** Es gibt keinen Weg, Close-Code bzw. -Grund der beendeten
  Verbindung zu erfahren, etwa für ein „disconnected (code=1000)“-Log. Den
  Disconnect sieht man nur indirekt über das Finalisieren des Dishka-SESSION-Scopes.
- **Verhaltensänderung:** Requests werden jetzt nebenläufig verarbeitet
  (`RpcLimits.max_concurrency=32`), vorher sequentiell pro Verbindung. Das ist
  vermutlich gewollt, aber Reihenfolgegarantien (z. B. `subscribe` vor `start`
  vom selben Client) sind nicht mehr implizit. Das sollte dokumentiert sein.

## 6. Generierter Client

- **Positiv:** Typisierte Fehler, Modelle und Namespaces am Paket-Root.
  `with_transports()` ist klarer als die drei alten `from_transport*`.
- **Auth-Header:** `connect()` kennt `socket_factory`, aber kein `headers=`.
  Für einen Bearer-Token muss man eine Closure um `websockets.connect` bauen und
  deren Signatur kennen (`subprotocols: list[str] | None`). Das bleibt bei Cara
  eine handgeschriebene `connect_gateway()`-Datei, die per String-Replace in
  `__init__.py` injiziert wird. Wunsch: `connect(headers=...)` bzw. ein
  Extension-Punkt im Codegen für eigene Dateien und Exporte.
- **Lazy by default:** `connect()` öffnet Sockets erst beim ersten Aufruf.
  Auth- oder Netzwerkfehler tauchen dann an unerwarteter Stelle auf (beim ersten
  `subscribe`), nicht beim Verbinden. Cara nutzt deshalb `eager=True`.
  Für Single-Server-Clients wäre eager der erwartbarere Default.
- **`connect().open()`:** Wer den Client über einen Scope hinaus hält (CLI,
  Voice-Session), braucht `await GatewayRpcClient.connect(...).open()`.
  Das ist ok, aber ein `await GatewayRpcClient.connect(...)` direkt wäre
  natürlicher.
- **Server-Name aus dem Pfad:** Der Endpoint-Name wird aus dem letzten
  Pfadsegment abgeleitet (`/v1/gateway` → `gateway`, vorher `local`). Das ist
  sinnvoll, ändert aber `ServerName`-Enum-Werte im Client.
- **Formatierung:** Der generierte Code ist nicht ruff-formatiert (u. a. fehlt
  die Leerzeile nach dem Header). Cara formatiert per `ruff` nach und braucht
  deshalb einen eigenen Codegen-Wrapper statt `pyrpckit generate --config`.
  Ein Post-Process-Hook im TOML (`format = ["ruff", "format", "-"]`) würde den
  Wrapper überflüssig machen.

## 7. Contract

- **Positiv:** Contract aus dem Service mit echten Endpoint-Pfaden. Cara hatte
  in 0.4 die URL separat hardcodiert.
- **Kante:** `service.contract(base_url=...)` verlangt eine `ws://`-URL. Die
  meisten Apps kennen aber ihre HTTP-Basis-URL (die REST-Clients nutzen dieselbe).
  Eine http→ws-Ableitung im generierten `connect()` fehlt, und Cara macht sie in
  `connect_gateway` selbst.
- **Kante:** `render_contract()` schreibt mit `ensure_ascii=True`. Cara hatte
  `ensure_ascii=False` und rendert deshalb selbst per `render_openrpc`. Dort muss
  man daran denken, `binary_streams=contract.binary_streams` durchzureichen,
  sonst fehlen Streams still. `RpcContract.to_openrpc()` wäre robuster.

## 8. Binary Streams: Voice-Media-Transport (noch nicht umgesetzt)

Idee: den eigenen Voice-Media-Socket
(`/v1/voice-sessions/{voice_session_id}/media`) auf `@channel.stream` +
`service.stream(...)` umstellen, statt eigenem Framing und eigener Auth.

Warum das mit 0.5 nicht geht:
- Der Media-Socket ist **bidirektional**: Der Client schickt Mikrofon-PCM
  (`INPUT_PCM`/`INPUT_END`), der Server schickt Assistant-Audio auf *derselben*
  Verbindung. 0.5 unterstützt nur **Server→Client** (Client→Server und
  bidirektionale Streams wurden explizit entfernt; eingehende Frames führen zu
  `PROTOCOL_ERROR`).
- Der Socket hat **exklusive Ownership** („Voice session already has a media
  owner“) und publiziert Frames push-basiert aus dem `VoiceTurnService`.
  Bei `@channel.stream` ist die Quelle ein Async-Generator, der pro Verbindung
  läuft. Das passt für Output-Audio, aber Ownership-Regeln bräuchten den
  Connect-Hook plus einen eigenen Owner-Registry-Provider.
- Möglich wäre nur ein **Split**: Output-Audio als pyrpckit-Stream, Input-Audio
  weiter über einen eigenen Socket. Das ergibt zwei Sockets pro Voice-Session
  und damit mehr Komplexität als heute.

Was es bräuchte, damit Voice komplett auf pyrpckit laufen kann:
1. Client→Server-Binary-Streams (oder bidirektional), z. B.
   `@channel.stream(direction="client-to-server")` mit
   `AsyncIterator[bytes]` als Parameter.
2. Gemeinsames Framing-Konzept (Sequenz/Turn-Index im Frame), oder Doku, wie
   man das in den Payload legt.
3. Pfad-Variablen (`{voice_session_id}`) als typisierter `Inject`-/Parameterwert
   im Stream-Handler (heute nur über `RpcConnection.path_params` als String).
4. Ein Weg, eine Verbindung pro Ressource exklusiv zu halten (Connect-Hook,
   der mit einer passenden Rejection ablehnt, ist dafür wahrscheinlich
   ausreichend und sollte dokumentiert werden).

Sobald (1) existiert, lohnt sich ein neuer Anlauf, denn Auth-Hook, Pfad-Routing
und der generierte Stream-Client würden den handgeschriebenen `MediaTransport`
im Voice-Client ersetzen.
