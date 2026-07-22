# CLIs & Credentials in der Bash-Sandbox verfügbar machen

Ziel: Das `bash`-Tool im „Open-Claude-Stil" nutzen, damit der Agent eigene
CLIs (Python + Go) über normale Shell-Commands aufrufen kann — inklusive der
Credentials, die diese CLIs zum Funktionieren brauchen (z. B. eine Spotify-CLI
zum Suchen und Abspielen von Tracks).

Dieses Dokument beschreibt, **wie das technisch grundlegend funktioniert** und
welche Abwägungen es gibt. Es ist bewusst an den aktuellen Aufbau in
`cara/tools/handler/bash.py` und `docker/bash-sandbox.Dockerfile` angelehnt.

---

## 1. Ausgangslage: Die Sandbox ist heute maximal abgeschottet

Der aktuelle `DockerBashSandbox` startet für **jeden** Command einen frischen,
kurzlebigen Container mit diesen Flags:

```
--rm                     # Container wird nach dem Command sofort verworfen
--network=none           # KEIN Netzwerk
--read-only              # Root-Filesystem ist nur lesbar
--cap-drop=ALL           # keine Linux-Capabilities
--security-opt=no-new-privileges=true
--pids-limit=64  --memory=256m  --cpus=1
--tmpfs=/tmp:...         # einziger beschreibbarer Ort
--env=HOME=/tmp          # die einzige Env-Variable
--mount=<workspace>:/workspace
```

Das ist eine sehr gute Grundlage — aber es steht in direktem Konflikt mit dem
Ziel. Eine Spotify-CLI braucht **zwei Dinge**, die die Sandbox heute bewusst
verbietet:

| Anforderung der CLI      | Aktueller Zustand      | Muss geändert werden |
| ------------------------ | ---------------------- | -------------------- |
| Die CLI-Binary existiert | Nur `bash` + `python3` | **Ja** (Abschnitt 2) |
| Credentials (Token)      | Keine Env-Variablen    | **Ja** (Abschnitt 3) |
| Netzwerkzugriff          | `--network=none`       | **Ja** (Abschnitt 4) |

Es sind also **drei getrennte Probleme**. Wichtig: man löst sie getrennt und
so restriktiv wie möglich — nicht pauschal „alles auf" schalten.

---

## 2. Die CLIs in die Sandbox bringen

Es gibt zwei grundsätzliche Wege, ein Binary in den Container zu bekommen.

### 2a. In das Image einbacken (empfohlen)

Die CLIs werden beim `docker build` fest in das Sandbox-Image gelegt. Zur
Laufzeit ist dann nichts mehr zu tun — der Command findet sie einfach im
`PATH`. Das passt perfekt zum aktuellen `--read-only`-Ansatz: der Code liegt
unveränderbar im Image, der Agent kann ihn nur ausführen, nicht verändern.

**Go-CLIs** sind hier ideal: Go kompiliert zu einem einzelnen, statisch
gelinkten Binary ohne Runtime-Abhängigkeiten. Man kopiert genau eine Datei.

**Python-CLIs** brauchen einen Interpreter (den hast du schon: `python3` im
Alpine-Image) plus ihre Dependencies. Drei Varianten, von einfach zu robust:

- **Modul einbacken + `pip install`** im Build. Einfach, aber Alpine +
  C-Extensions (z. B. `cryptography`) können zickig sein.
- **`pipx`** installiert die CLI in ein isoliertes venv mit eigenem Entrypoint.
- **Standalone-Binary** via PyInstaller/`shiv`/`uv` → dann verhält sich die
  Python-CLI wie die Go-CLI (eine Datei, kein Interpreter-Gefummel).

Ein Multi-Stage-Build hält das finale Image klein — bauen in einer fetten
Stage, nur die fertigen Binaries in die schlanke Runtime-Stage kopieren:

```dockerfile
# docker/bash-sandbox.Dockerfile

# --- Stage 1: Go-CLIs bauen ---
FROM golang:1.23-alpine AS go-build
WORKDIR /src
COPY clis/go/ .
# CGO aus => wirklich statisches Binary, läuft überall
RUN CGO_ENABLED=0 go build -o /out/spotify ./cmd/spotify

# --- Stage 2: Python-CLIs vorbereiten ---
FROM python:3.13-alpine AS py-build
RUN pip install --no-cache-dir pipx
# Beispiel: eine Python-CLI aus deinem Repo installieren
COPY clis/python/mytool /src/mytool
RUN pipx install /src/mytool

# --- Stage 3: schlanke Runtime (das eigentliche Sandbox-Image) ---
FROM python:3.13-alpine
RUN apk add --no-cache bash

# Go-Binaries: eine Datei nach /usr/local/bin
COPY --from=go-build /out/spotify /usr/local/bin/spotify

# Python-CLIs: pipx-venvs + Shims übernehmen
COPY --from=py-build /root/.local /opt/pipx
ENV PATH="/opt/pipx/bin:${PATH}"

ENTRYPOINT []
CMD ["bash"]
```

`scripts/prepare_bash_sandbox.sh` baut dieses Image bereits — es muss nur den
Build-Context bekommen, der die CLI-Quellen enthält (`clis/` statt nur
`docker/`). Danach ist `spotify` in jedem Sandbox-Command aufrufbar.

> **Vorteil:** Binaries sind versioniert, reproduzierbar und liegen im
> read-only-Layer. Der Agent kann sie nicht manipulieren.
> **Nachteil:** Nach Änderungen an einer CLI muss das Image neu gebaut werden.

### 2b. Zur Laufzeit mounten (für schnelle Iteration)

Statt einzubacken kann man ein Verzeichnis mit den fertigen Binaries als
zweiten Bind-Mount read-only in den Container hängen:

```
--mount=type=bind,source=<host>/clis/bin,target=/opt/clis,readonly
--env=PATH=/opt/clis:/usr/local/bin:/usr/bin:/bin
```

Praktisch beim Entwickeln (kein Rebuild pro Änderung). Aber: Go-Binaries für
**Linux** müssen vorliegen (dein Host ist Windows → Cross-Compile mit
`GOOS=linux GOARCH=amd64`), und Python-CLIs schleppen wieder das
Interpreter-/Dependency-Problem mit. Für den Dauerbetrieb ist 2a sauberer.

**Empfehlung:** Einbacken (2a) als Standard. Mount (2b) nur als optionaler
Dev-Modus.

---

## 3. Credentials in die Sandbox bringen

Kernregel vorweg: **Credentials niemals in das Image einbacken.** Ein Image
wird geteilt, gepusht, gecacht — Secrets landen sonst dauerhaft in einem Layer.
Credentials kommen **zur Laufzeit** rein, pro Container-Start.

Deine Credentials liegen heute schon zentral in `.env` (bzw. deinen
`pydantic-settings`). Genau von dort werden sie selektiv in den Container
gereicht. Vier Mechanismen, geordnet nach Sauberkeit:

### 3a. Einzelne Env-Variablen (`--env NAME=value`)

Der direkteste Weg. Der Handler übergibt genau die Variablen, die der aktuelle
Command braucht:

```
--env=SPOTIFY_CLIENT_ID=...
--env=SPOTIFY_REFRESH_TOKEN=...
```

Einfach und explizit. Nachteil: Der Wert steht dann im `docker run`-Argv und
ist auf dem Host kurz via `ps`/Prozessliste sichtbar.

### 3b. Env-File (`--env-file`)

Docker liest die Variablen aus einer Datei statt aus dem Argv → nichts steht in
der Prozessliste. Der Handler schreibt pro Aufruf ein kurzlebiges File (im
scratchpad/`tmp`), übergibt `--env-file` und löscht es danach:

```
--env-file=<host>/tmp/cara-creds-<uuid>.env
```

### 3c. Secret als Datei-Mount (am saubersten für „echte" Secrets)

Manche CLIs lesen Tokens lieber aus einer Datei (`~/.config/spotify/token`).
Dann mountet man diese Datei read-only an die erwartete Stelle. Da HOME auf
`/tmp` zeigt und `/tmp` ein tmpfs ist, verschwindet der Inhalt beim
Container-Ende automatisch.

### 3d. Kurzlebige statt langlebige Tokens

Der wichtigste konzeptionelle Punkt, unabhängig vom Mechanismus: **Gib nach
Möglichkeit kurzlebige Access-Tokens rein, nicht die langlebigen Secrets.**
OAuth-Dienste wie Spotify trennen ohnehin:

- Der **Refresh-Token** / das **Client-Secret** ist langlebig und wertvoll →
  bleibt auf dem Host (in cara).
- cara tauscht ihn außerhalb der Sandbox gegen einen **Access-Token** (Gültig-
  keit ~1 h) und reicht **nur diesen** in den Container.

So kann selbst ein durch die CLI kompromittierter Container maximal begrenzten
Schaden anrichten, und das eigentliche Secret verlässt cara nie.

### Das Prinzip: Least Privilege pro Aufruf

Der Bash-Handler sollte **nicht** blind alle `.env`-Werte in jeden Container
kippen. Besser: pro Command wird entschieden, welche Credentials nötig sind —
gesteuert durch das Skill/den Command (siehe Abschnitt 5). Ein Command, der nur
`ls` macht, bekommt keine Spotify-Tokens.

---

## 4. Netzwerk selektiv öffnen

`--network=none` verhindert jeden Netzwerkzugriff — eine Spotify-CLI kann so
nicht mit der API reden. Es gibt keinen Weg, „nur ein bisschen" Netzwerk mit
einem einzigen Flag zu bekommen; man wählt eine Stufe:

1. **Voller Egress** (`--network=bridge`, Docker-Default). Einfach, aber der
   Container kann mit dem ganzen Internet reden. Für eine vertrauenswürdige,
   eingebackene CLI oft akzeptabel — der Angriffsvektor ist der Command, den
   der Agent formuliert, nicht die CLI selbst.
2. **Allowlist über Egress-Proxy.** Der Container darf nur an einen HTTP(S)-
   Proxy, der ausschließlich bestimmte Domains (`api.spotify.com`) durchlässt.
   Deutlich sicherer, aber Infrastruktur-Aufwand (eigenes Docker-Netzwerk +
   Proxy-Container).
3. **DNS/Firewall-Regeln** auf einem dedizierten Docker-Netzwerk. Zwischen 1
   und 2 angesiedelt.

**Wichtige Kopplung:** Sobald Netzwerk offen ist, wird die Least-Privilege-
Regel bei Credentials (Abschnitt 3) sicherheitskritisch. Netzwerk **und**
langlebige Secrets im selben Container = ein einziger schlechter Command kann
Daten exfiltrieren. Deshalb: Netzwerk nur an, wenn nötig, und dann nur mit
kurzlebigen Tokens.

Praktisch heißt das: Die Sandbox braucht **nicht mehr genau eine** Konfiguration,
sondern ein **Profil pro Command-Klasse** — der reine Rechen-/Dateisandkasten
bleibt `--network=none` ohne Secrets; ein „Spotify"-Profil bekommt Egress plus
kurzlebigen Token.

---

## 5. Zusammenführung: Sandbox-Profile, gesteuert durch Skills

Der sauberste Weg, all das im Open-Claude-Stil zu verdrahten, ist ein
**Capability-/Profil-Konzept**. Statt einer festen `DockerBashSandbox`-Config
bekommt der Handler pro Aufruf ein Profil, das drei Dinge festlegt:

1. **Welches Image** (bzw. welche eingebackenen CLIs).
2. **Welche Credentials** in den Container gereicht werden.
3. **Welche Netzwerkstufe** gilt.

Das fügt sich in deinen bestehenden Aufbau ein: Es gibt bereits
`BashPolicyMiddleware` (heute ein No-Op) und `skills/` mit `SKILL.md`. Der Fluss
wird dann:

```
Skill (spotify/SKILL.md)
  └─ beschreibt dem Agenten: "nutze `spotify search …` / `spotify play …`"
  └─ deklariert das benötigte Profil: image+netz+creds "spotify"
        │
        ▼
Agent formuliert bash-Command:  spotify play "Bohemian Rhapsody"
        │
        ▼
BashPolicy/Handler wählt Profil "spotify"
  ├─ Image mit eingebackener spotify-CLI
  ├─ Access-Token (kurzlebig) via --env-file
  └─ --network=bridge  (statt none)
        │
        ▼
DockerBashSandbox.run(command, workspace, profile)
```

Konkret bedeutet das an deinem Code:

- **`DockerBashSandbox._docker_arguments`** wird parametrisiert: Netzwerk-Flag
  und Env-Injection kommen aus einem Profil-Objekt statt hartkodiert
  (`--network=none`, nur `HOME=/tmp`).
- **Credential-Beschaffung** (z. B. Spotify-Refresh→Access-Token-Tausch) lebt
  **außerhalb** der Sandbox in cara (dort, wo heute `pydantic-settings` die
  `.env` liest), und übergibt nur das Ergebnis.
- **Skills** deklarieren, welches Profil sie brauchen — analog zu deinem
  `weather`-Skill, nur zusätzlich mit einer Profil-/Credential-Angabe im
  Frontmatter.

Default bleibt das heutige harte Profil (kein Netz, keine Secrets). Ein Command
bekommt nur dann mehr Rechte, wenn ein Skill das explizit anfordert.

---

## 6. Durchgängiges Beispiel: Spotify-CLI

**Einmalig (Build-Time):**

1. Go-CLI `spotify` (oder Python) implementieren; liest `SPOTIFY_ACCESS_TOKEN`
   aus der Env.
2. In `docker/bash-sandbox.Dockerfile` einbacken (Multi-Stage, Abschnitt 2a).
3. `scripts/prepare_bash_sandbox.sh` mit erweitertem Build-Context bauen.

**Zur Laufzeit (pro Command):**

1. Agent lädt `skills/spotify/SKILL.md`, das ihm die Commands beibringt.
2. Agent ruft `bash` mit `spotify play "…"` auf.
3. Handler erkennt Profil „spotify":
   - cara tauscht (außerhalb der Sandbox) den Refresh-Token gegen einen
     Access-Token.
   - Startet den Container mit `--network=bridge` und
     `--env-file` (nur `SPOTIFY_ACCESS_TOKEN`).
4. Die CLI redet mit `api.spotify.com`, spielt den Track, Container wird
   verworfen (`--rm`), Token-File gelöscht.

Langlebiges Secret bleibt in cara. Im Container war nur ein 1-Stunden-Token und
genau eine CLI.

---

## 7. Zusammenfassung der Abwägungen

| Thema        | Empfehlung                                   | Warum                                              |
| ------------ | -------------------------------------------- | -------------------------------------------------- |
| CLI-Bereitst.| In Image einbacken (Multi-Stage)             | Reproduzierbar, read-only, kein Runtime-Setup      |
| Go vs Python | Go = eine Binary; Python = pipx/Standalone   | Go trivial; Python braucht Interpreter/Deps        |
| Credentials  | Zur Laufzeit, `--env-file`, nie ins Image    | Secrets dürfen nicht in geteilten Layern landen    |
| Token-Art    | Kurzlebige Access-Tokens statt Secrets       | Begrenzt Schaden bei kompromittiertem Container    |
| Least Priv.  | Nur nötige Creds pro Command                  | `ls` braucht keinen Spotify-Token                  |
| Netzwerk     | Standard `none`; pro Profil selektiv öffnen   | Netz + Secrets zusammen = Exfiltrationsrisiko      |
| Steuerung    | Sandbox-Profile, deklariert via Skills        | Passt zu bestehender Policy-Middleware + `skills/` |

**Kernaussage:** Die drei Probleme (CLI da, Credentials da, Netzwerk da) werden
getrennt gelöst. CLIs kommen fest ins Image, Credentials kommen kurzlebig und
selektiv zur Laufzeit rein, Netzwerk wird nur pro Profil geöffnet — und ein
Skill entscheidet, welches Profil ein Command bekommt. So bleibt der harte
Default erhalten und nur die Commands, die es wirklich brauchen, bekommen mehr.
