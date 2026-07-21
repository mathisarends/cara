---
name: weather
description: Wetterbericht ansagen — immer wenn nach dem Wetter gefragt wird.
---

# Wetterbericht

So lieferst du einen gesprochenen Wetterbericht:

1. Aktueller Standort und aktuelle Uhrzeit stehen bereits in deinem `<context>`. Nutze
   sie, ohne erneut nachzufragen.
2. Rufe das Tool `weather` auf. Nennt die Person keinen anderen Ort, lässt du den
   Parameter `location` weg — dann gilt der aktuelle Standort.
3. Formuliere die Antwort knapp und natürlich zum Vorlesen:
   - Beziehe dich auf die Tageszeit (morgens, mittags, abends, nachts), passend zur
     aktuellen Uhrzeit.
   - Nenne Temperatur und gefühlte Temperatur nur zusammen, wenn sie spürbar
     auseinanderliegen.
   - Gib nur dann eine kurze Empfehlung (Regenschirm, Jacke), wenn sie sich aufdrängt.
4. Halte dich kurz: ein bis zwei Sätze.
