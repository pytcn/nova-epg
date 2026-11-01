# nova-epg

Programmführer (XMLTV) für die App **NOVA+**: 8.065 Sender aus allen Ländern der iptv-org-Senderdatenbank,
für die es eine funktionierende Programmquelle gibt (eingestellte Sender ausgenommen).

- Senderliste: `channels/shard1…8.xml` – erzeugt aus der iptv-org-Senderdatenbank (`channels.csv`); je Sender eine Quelle aus
  [iptv-org/epg](https://github.com/iptv-org/epg), die dort als funktionierend (🟢) markiert ist
  (DACH: deutschsprachige Anbieter bevorzugt, sonst Anbieter aus dem Land des Senders).
- Aktualisierung: GitHub Actions, zweimal täglich, 2 Tage im Voraus, 8 Teile parallel; `scripts/merge.py` führt sie zusammen.
- Adressen (Einstellungen → Programmführer):
  - `https://pytcn.github.io/nova-epg/guides/dach.xml.gz` – Deutschland, Österreich, Schweiz (**empfohlen**)
  - `https://pytcn.github.io/nova-epg/guides/<land>.xml.gz` – ein Land (`de`, `at`, `uk`, `fr`, …), als weitere Adresse
  - `https://pytcn.github.io/nova-epg/guide.xml.gz` – alle Sender (groß; für einen Fire TV Stick nicht empfohlen)
  - `stats.tsv` zeigt Sender, Sendungen und Größe jeder Datei.

## Einrichtung (einmalig)

1. Dieses Repository **öffentlich** auf GitHub anlegen und alle Dateien hochladen (auch den Ordner `.github`).
2. **Settings → Pages → Build and deployment → Source: GitHub Actions**.
3. **Actions** → ggf. „I understand my workflows, go ahead and enable them“ → **EPG** → **Run workflow**.
4. Nach dem ersten Lauf (je nach Quellen 20–90 Min.) ist die Adresse oben erreichbar; `updated.txt` zeigt den Zeitpunkt.

## Hinweise

- Die Programmdaten werden von Webseiten Dritter abgerufen. Für deren Nutzung gelten die jeweiligen
  Nutzungsbedingungen; das Repository ist für den privaten Gebrauch gedacht.
- GitHub pausiert geplante Workflows in öffentlichen Repos nach 60 Tagen ohne Aktivität – dann unter Actions wieder aktivieren.
- Einzelne Quellen fallen gelegentlich aus; der Guide enthält dann für diese Sender keine Daten, NOVA+ behält die zuletzt geladenen.
- Senderliste ändern: Zeilen in `channels/shard*.xml` löschen oder aus `iptv-org/epg/sites/…` ergänzen.
