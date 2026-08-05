# Vorschlag zur Struktur von Cara

## Ziel

Die Struktur soll drei Bereiche klar voneinander trennen:

1. **Implementierung**: wiederverwendbarer, getesteter Python-Code
2. **Workspace**: editierbare Inhalte und dauerhafter Zustand der konkreten Cara-Instanz
3. **Experimente**: alternative Zusammensetzungen und unfertige Ideen

Der Workspace soll für Cara wie das Wurzelverzeichnis aussehen. Dadurch liegen die relevanten
Markdown-Dateien aus Sicht von Cara direkt auf Root, während sie auf dem Host sauber vom
Python-Paket und von geheimen Dateien wie `.env` getrennt bleiben.

## Vorgeschlagene Verzeichnisstruktur

```text
cara/
├── cara/                       # Wiederverwendbare Implementierung
│   ├── agent.py
│   ├── memory.py
│   ├── prompt/
│   ├── sessions/
│   ├── tools/
│   ├── audio/
│   └── ...
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
        └── kennt keine konkrete Anwendung und keine persönlichen Inhalte
```

Die Anwendung kennt also die Implementierung, aber die Implementierung kennt weder `main.py` noch
ein bestimmtes Experiment. Workspace-Pfade werden explizit an Prompt, Memory und Tools übergeben.

## Umgang mit `AGENTS.md`

Im Repository existiert bereits eine `AGENTS.md` mit Entwicklungsregeln für Coding-Agenten. Die
gleichnamige Datei im Workspace enthält dagegen Laufzeitanweisungen für Cara. Da beide in getrennten
Wurzeln liegen, können sie denselben Namen behalten, ohne unterschiedliche Zwecke zu vermischen.

## Bewusste Nicht-Ziele

Dieser Vorschlag erfordert zunächst keinen Wechsel auf ein `src/cara/`-Layout und keine Aufteilung in
mehrere Python-Pakete. Entscheidend ist zuerst, die persönlichen Markdown-Inhalte aus dem Paket zu
lösen und Implementierung, Workspace und Experimente klar voneinander abzugrenzen.

Dieses Dokument beschreibt nur eine mögliche Zielstruktur. Es nimmt noch keine strukturellen oder
funktionalen Änderungen am Projekt vor.
