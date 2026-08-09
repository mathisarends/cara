# SQLite-Datenbank im Browser ansehen

Für die lokale Entwicklung startet Docker Compose `sqlite-web` zusammen mit den
anderen Diensten:

```powershell
docker compose up -d
```

Danach ist die Datenbankoberfläche unter <http://localhost:8080> erreichbar.
Eine Anmeldung ist nicht nötig: `sqlite-web` öffnet automatisch die Datei
`gateway.sqlite3` aus dem gemeinsamen Docker-Volume.

Über die Oberfläche lassen sich Tabellen und Inhalte ansehen, SQL-Abfragen
ausführen sowie Ergebnisse als CSV oder JSON exportieren. Änderungen wirken
direkt auf die lokale Anwendungsdatenbank.

Falls nur die Datenbankoberfläche nachgestartet werden soll:

```powershell
docker compose up -d sqlite-web
```
