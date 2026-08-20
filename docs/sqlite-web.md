# SQLite-Datenbank im Browser ansehen

Das Gateway läuft auf dem Host und schreibt standardmäßig nach
`./gateway.sqlite3`. Optional kann nur die Datenbankoberfläche in Docker
gestartet werden:

```powershell
docker compose up -d sqlite-web
```

Danach ist `sqlite-web` unter <http://localhost:8080> erreichbar. Der Container
bindet dieselbe lokale `gateway.sqlite3` ein, die auch das Host-Gateway nutzt.
Änderungen über die Oberfläche wirken daher direkt auf die lokale
Anwendungsdatenbank.
