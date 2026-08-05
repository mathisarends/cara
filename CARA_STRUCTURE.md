# Repository-Struktur von Cara

## Ziel

Die Struktur soll drei Bereiche klar voneinander trennen:

1. **Implementierung**: wiederverwendbarer, getesteter Python-Code
2. **Workspace**: editierbare Inhalte und dauerhafter Zustand der konkreten Cara-Instanz
3. **Experimente**: alternative Zusammensetzungen und unfertige Ideen

Der Workspace soll für Cara wie das Wurzelverzeichnis aussehen. Dadurch liegen die relevanten
Markdown-Dateien aus Sicht von Cara direkt auf Root, während sie auf dem Host sauber vom
Python-Paket und von geheimen Dateien wie `.env` getrennt bleiben.

## Verzeichnisstruktur

```text
cara/
├── cara/                       # Wiederverwendbare Implementierung
│   ├── agent.py
│   ├── memory/
│   │   ├── service.py
│   │   ├── indexing.py
│   │   └── rendering.py
│   ├── prompt/
│   ├── sessions/
│   ├── tools/
│   ├── audio/
│   └── ...
│
├── packages/
│   └── retrieval/                # Eigenständiges, generisches Retrieval-Paket
│       ├── retrieval/
│       ├── examples/
│       ├── tests/
│       └── pyproject.toml
│
├── workspace/                  # Inhalt und Zustand der konkreten Cara-Instanz
│   ├── AGENTS.md
│   ├── IDENTITY.md
│   ├── SOUL.md
│   ├── USER.md
│   ├── MEMORY.md
│   ├── daily/
│   │   └── YYYY-MM-DD.md
│   └── artifacts/              # Von Cara erzeugte Arbeitsdateien
│
├── skills/                     # Lokale, editierbare Skills
├── sounds/                     # Fertige, weiterhin verwendete Audiodateien
├── experiments/                # Spikes und alternative Anwendungen
│   ├── chat_in_terminal.py
│   └── ...
│
├── scripts/                    # Wartungs- und Setup-Skripte
├── tests/                      # Tests der Implementierung
├── main.py                     # Composition Root der normalen Anwendung
├── pyproject.toml
└── README.md
```

## Sicht von Cara auf den Workspace

`C:\code\cara\workspace` wird als Workspace-Root verwendet. Für Cara ergibt sich damit:

```text
/
├── AGENTS.md
├── IDENTITY.md
├── SOUL.md
├── USER.md
├── MEMORY.md
├── daily/
└── artifacts/
```

Zusätzliche Bereiche können gezielt eingebunden werden, wenn Cara sie bearbeiten soll:

```text
/src/cara/                   # Schreibbarer Anwendungscode
/experiments/                # Schreibbare Experimente
/skills/                     # Schreibbare Skills
```

Das gesamte Repository sollte nicht pauschal als Workspace dienen. So bleiben `.env`, `.git`,
Build-Artefakte und andere interne Dateien außerhalb des normalen Zugriffsbereichs.

## Verantwortlichkeiten

### `cara/`: Implementierung

Dieser Ordner enthält ausschließlich allgemeine Mechanik:

- Agent und Gesprächsverlauf
- Prompt-Komposition
- Tool-Registrierung und Tool-Ausführung
- Memory-Indexierung und Suche
- Terminal-, Voice- und Audio-Komponenten

Der Code kennt keine fest eingebauten persönlichen Inhalte. Pfade zu Workspace, Memory und Skills
werden von außen übergeben.

### `workspace/`: konkrete Cara-Instanz

Dieser Ordner enthält alles, was Cara inhaltlich ausmacht oder im Betrieb verändert:

- Identität und Verhalten
- Informationen über den Benutzer
- langfristige und tägliche Erinnerungen
- erzeugte Dokumente und andere Arbeitsartefakte

Diese Dateien sind normal editierbar und werden nicht als Daten des Python-Pakets ausgeliefert.

### `packages/retrieval/`: generische Retrieval-Bibliothek

Dieses uv-Workspace-Paket enthält ausschließlich allgemein verwendbare Retrieval-Bausteine:

- Dokumenttypen und Provider-Ports
- Chunking
- lexikalische und vektorbasierte Indizes
- SQLite- und OpenAI-Adapter
- Ranking, Fusion und Reranking

Das Paket kennt weder Cara noch `MEMORY.md`, Tagesnotizen, Prompt-Tags oder Workspace-Pfade. Die
Cara-spezifische Auswahl, Indexierung und Darstellung von Erinnerungen bleibt unter `cara/memory/`.

### `experiments/`: Labor

Experimente dürfen konkrete Konfigurationen und unfertige Ideen enthalten. Vorerst gibt es hier nur
den Terminal-Flow, beispielsweise mit zusätzlichen Tools oder einem neuen Memory-Ansatz. Erst wenn
Logik stabil und mehrfach nützlich ist, wird sie nach `cara/` verschoben.

### `main.py`: konkrete Verwendung

`main.py` bleibt klein und verbindet lediglich die Bausteine:

- Workspace und Skills auswählen
- Modell und Tools konfigurieren
- Agent erzeugen
- gewünschte Session starten

Allgemeine Geschäftslogik gehört nicht in `main.py`.

## Vorgeschlagene Abhängigkeitsrichtung

```text
main.py / experiments
        │
        ├── verwendet workspace-Inhalte
        │
        └── verwendet cara-Paket

cara-Paket
        ├── kennt keine konkrete Anwendung und keine persönlichen Inhalte
        └── verwendet das generische retrieval-Paket

retrieval-Paket
        └── kennt weder Cara noch den Cara-Workspace
```

Die Anwendung kennt also die Implementierung, aber die Implementierung kennt weder `main.py` noch
ein bestimmtes Experiment. Workspace-Pfade werden explizit an Prompt, Memory und Tools übergeben.

## Umgang mit `AGENTS.md`

Im Repository existiert bereits eine `AGENTS.md` mit Entwicklungsregeln für Coding-Agenten. Die
gleichnamige Datei im Workspace enthält dagegen Laufzeitanweisungen für Cara. Da beide in getrennten
Wurzeln liegen, können sie denselben Namen behalten, ohne unterschiedliche Zwecke zu vermischen.

## Bewusste Nicht-Ziele

Die Struktur verwendet weiterhin kein `src/cara/`-Layout. Das zusätzliche Python-Paket `retrieval`
bleibt bewusst eigenständig, weil es unabhängig von Cara nutzbar ist. Die Sprach-Ein-/Ausgabe und die
fertigen Dateien unter `sounds/` bleiben Teil des Projekts; nur die nicht mehr benötigte
Soundgenerierung wurde entfernt.

Die persönliche Laufzeitkonfiguration ist vom installierbaren Python-Code getrennt. `main.py` und das
Terminal-Experiment stellen die Verbindung über explizite Workspace- und Mount-Konfiguration her.
