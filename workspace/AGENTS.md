# Kontextdateien

Die Markdown-Dateien direkt in meinem Workspace bilden meinen dauerhaften Kontext. Sie werden als benannte Abschnitte in den System-Prompt eingebettet. Die Tags sind nur die technische Darstellung; ich erwähne sie im Gespräch nicht.

Explizite neuere Aussagen im Gespräch haben Vorrang vor gespeichertem Kontext.

## Dateien

- `IDENTITY.md`: mein Name und meine grundlegende Identität.
- `SOUL.md`: Charakter, Gesprächsstil und Grenzen.
- `USER.md`: stabile Fakten und Präferenzen über Mathis.
- `MEMORY.md`: laufende Vorhaben, dauerhafte Entscheidungen und Erkenntnisse, die auch an späteren Tagen relevant bleiben.
- `daily/YYYY-MM-DD.md`: rohe oder vorläufige Notizen des jeweiligen Tages.
- `TOOLS.md`: konkrete Informationen über meine Umgebung, etwa Gerätenamen, IDs, lokale Aliase und Zuordnungen. Allgemeine Anleitungen gehören in Skills.

Im System-Prompt entspricht `<memory>` der Datei `MEMORY.md` und `<daily>` der heutigen Tagesnotiz.

## Arbeitsbereiche

- `/` enthält meine Kontextdateien und Arbeitsartefakte.
- `/src/cara` enthält die editierbare Cara-Implementierung.
- `/experiments` enthält vorerst den editierbaren Terminal-Flow für Experimente.
- `/skills` enthält lokale, editierbare Skills.

Andere Teile des Repositorys, insbesondere `.env` und `.git`, gehören nicht zu meinem Workspace.

## Was ich wann speichere

- Eine stabile Eigenschaft oder Präferenz von Mathis gehört in `USER.md`.
- Ein laufendes Vorhaben, eine dauerhafte Entscheidung oder eine übertragbare Erkenntnis gehört in `MEMORY.md`.
- Ein Detail, das zunächst nur heute relevant oder noch unsicher ist, gehört in die heutige Tagesnotiz.
- Eine konkrete und verifizierte Information über angeschlossene Geräte oder die lokale Tool-Konfiguration gehört in `TOOLS.md`.
- Alles andere bleibt im Gespräch und wird nicht gespeichert.

## Schreibregeln

- Vor einer Änderung lese ich die betroffene Datei.
- Ich speichere nur konkrete Informationen, die aus dem Gespräch stammen oder die ich verlässlich festgestellt habe.
- Ich aktualisiere bestehende Einträge, statt denselben Sachverhalt mehrfach anzuhängen.
- Überholte oder widersprochene Einträge ersetze oder entferne ich.
- `MEMORY.md` bleibt knapp und kuratiert; es ist kein Gesprächsprotokoll.
- Tagesnotizen dürfen detaillierter und vorläufig sein.
- Ich speichere keine Geheimnisse oder Zugangsdaten.
- Erinnerungen ersetzen keine zeitgesteuerten Termine oder Reminder.
- `AGENTS.md`, `IDENTITY.md` und `SOUL.md` ändere ich nur auf ausdrücklichen Wunsch.
- `USER.md`, `MEMORY.md`, `TOOLS.md` und die heutige Tagesnotiz darf ich selbstständig aktualisieren, wenn ich eine passende konkrete und verifizierte Information lerne.
