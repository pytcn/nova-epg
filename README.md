# nova-epg

Programmführer (XMLTV) für die App **NOVA+**: 6.530 Sender aus der iptv-org-Senderdatenbank (`data/channels.csv`),
für die es eine funktionierende Programmquelle gibt (im Testlauf geprüft) – ohne Russland, China, Japan, Afrika und den Balkan
(Türkei bleibt drin), ohne eingestellte Sender und ohne Doppelte.
Zusätzlich vollständig: sky.com (DE/UK/IT), dazn.com und www.magenta.tv; ergänzend die fertige Datei von epg.lat (DE).

- Senderliste: `channels/shard1…8.xml`, erzeugt mit `python3 scripts/build_channels.py <pfad-zu-iptv-org/epg>`
  (Regeln stehen oben im Skript); je Sender eine Quelle aus
  [iptv-org/epg](https://github.com/iptv-org/epg), die dort als funktionierend (🟢) markiert ist
  (DACH: deutschsprachige Anbieter bevorzugt, sonst Anbieter aus dem Land des Senders).
- Aktualisierung: GitHub Actions, zweimal täglich, 2 Tage im Voraus, 8 Teile parallel; `scripts/merge.py` führt sie zusammen.
- Adressen (Einstellungen → Programmführer):
  - `https://pytcn.github.io/nova-epg/guides/dach.xml.gz` – Deutschland, Österreich, Schweiz (**empfohlen**)
  - `https://pytcn.github.io/nova-epg/guides/<land>.xml.gz` – ein Land (`de`, `at`, `uk`, `fr`, …), als weitere Adresse
  - `https://pytcn.github.io/nova-epg/guide.xml.gz` – alle Sender (groß; für einen Fire TV Stick nicht empfohlen)
  - `stats.tsv` zeigt Sender, Sendungen und Größe jeder Datei.

## Hinweise

- Die Programmdaten werden von Webseiten Dritter abgerufen. Für deren Nutzung gelten die jeweiligen
  Nutzungsbedingungen; das Repository ist für den privaten Gebrauch gedacht.
- GitHub pausiert geplante Workflows in öffentlichen Repos nach 60 Tagen ohne Aktivität – dann unter Actions wieder aktivieren.
- Einzelne Quellen fallen gelegentlich aus; der Guide enthält dann für diese Sender keine Daten, NOVA+ behält die zuletzt geladenen.
- Senderliste ändern: Regeln in `scripts/build_channels.py` anpassen und neu erzeugen, oder Zeilen in `channels/shard*.xml` löschen.
- Externe Guides (z. B. epg.lat) ergänzen nur Sender, die noch fehlen, und nur Sendungen, die noch nicht vorbei sind.
  Ist die Datei veraltet, steht das in `stats.tsv` („abgelaufen“).
