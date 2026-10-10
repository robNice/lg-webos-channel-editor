# Technische Grundlagen und verbindliche Projektregeln

**Gültiger Referenzstand: v0.5.24 – erfolgreich am LG OLED55C27LA (webOS 22) mit vollständiger automatischer Neunummerierung getestet am 10.10.2026.**

Diese Datei beschreibt die **aktuell verbindlichen** Architektur- und Sicherheitsregeln. Frühere Zwischenergebnisse aus v0.5.7–v0.5.23 sind in `CHANGELOG.md`, `interne_notizen.md` und `docs/archiv/` dokumentiert; entgegenstehende alte Hinweise gelten als **überholt**. Primäre Wahrheit bleibt immer der aktuelle Quellcode und die tatsächlich auf dem LG beobachteten Ergebnisse.

## 1. Harte Regeln

1. **TV-Daten nicht direkt beschreiben.** Der TV führt die Senderverwaltung selbst. Datenquelle ist `/mnt/lg/cmn_data/iepg/db/channel.sql` (SQLite-Snapshot), aber ein direkter Datenbank- oder LevelDB-Schreibzugriff ist nicht zulässig. Keine Änderungen an `/mnt/lg/cmn_data/ldb_chmap`. TV-Schreiben nur durch explizit freigegebene Luna-APIs.
2. **Kein Sendername als Identität.** Mehrfach auftretende gleiche Namen und gleiche DVB-Kennungen sind real. Nutze die original importierte LG-`dvc_chan_id`, validiere den technischen DVB-Teil und nutze DVB-Identität plus TV-seitige ursprüngliche Nummer nur als eindeutig geprüften Fallback. Bei Zweifeln abbrechen.
3. **Originalzustand und Zielzustand trennen.** Die beim Import festgehaltene ursprüngliche ID/Nummer bilden die Ausgangsidentität. Neu eingegebene Nummern sind ausschließlich Ziele. Bei LG-Renumbering sind neue `channelId`-Werte möglich: **bestätigte Live-IDs** für weitere Schritte (insbesondere Sortierung) als Alias verfolgen. Keine IDs aus Zahlenmustern erraten.
4. **Alle betroffenen Sender vor dem ersten Schreibschritt prüfen.** Baseline-Snapshot, Arbeitskopie und Luna-Live-Abzug müssen widerspruchsfrei sein. Unbekannte Favoriten-IDs, mehrdeutige Plätze oder widersprüchliche Operationen ⇒ Abbruch.
5. **Jeden Schritt am echten Live-Zustand verifizieren.** Ein `returnValue:true` beweist keine Verschiebung (LG kann bei Astra kopieren). Ein `returnValue:false` beweist nicht, dass eine Favoritenänderung ausblieb. Wiederholte **lesende** Prüfungen sind erlaubt, blinde Schreibwiederholungen nicht.
6. **Keine atomare Transaktion vortäuschen.** Vor jedem Übertragungsversuch eine TV-SQLite-Sicherung anlegen; bei Fehler keine automatische TV-Rückabwicklung behaupten. Nach Teilabbruch erst neu importieren, dann einen neuen Plan erstellen.
7. **Neu vergebene Programmnummern ausschließlich 1–99** (globale Editorregel, nicht allgemeine Luna-API-Schranke). Vorhandene Nummern >99 unangetastet anzeigen. Nicht stillschweigend truncaten, klemmen oder auf andere Zahlen umdeuten.
8. **Keine automatische Astra-Ersatz-API.** `copyDvbSatelliteChannelForAstra` wurde untersucht, ist aber nicht als genereller Fallback verifiziert. Der implementierte Pfad verwendet `changeChannelNumber` und erkennt anhand der Live-Zustände, ob LG kopiert oder umnummeriert.
9. **Favoriten A–H nicht vertauschen.** Nummerierungen sind global, Mitgliedschaften listenbezogen. Spezielle Astra-Kopiermigration gilt derzeit nur für **Liste A**; Gruppen B–H des Originals und der Kopie sind zu erhalten. Keine Löschung globaler Originaleinträge.
10. **Gruppenvergleich bei Platztausch ist unmittelbar.** Vorher/nachher die realen Gruppen der **beiden konkreten Sender** vergleichen, nicht den Endzustand der lokalen Arbeitskopie heranziehen. Das ist der am TV erfolgreich getestete Fix aus v0.5.24.
11. **Keine Freigabe von schreibenden Tests am realen TV ohne Zustimmung.** Testfälle sollen mit simulierten LG-Antworten auch Teilabbrüche und Mehrdeutigkeiten abdecken.
12. **Versionierung / Cache-Busting.** Bei echtem App-Update `APP_VERSION` in `version.py` erhöhen; `?v=` für JavaScript/CSS und der Versions-Chip werden beim Ausliefern daraus gesetzt. Statische Einbindungen syntaktisch korrekt halten; `data/` nie paketieren oder überschreiben.
13. **Lokalisierung.** Keine Texte fest im Code: Meldungen als `LocalizedError`/`Message` mit Schlüssel aus `locales/<sprache>/messages.json`, Oberfläche über `{{t:…}}` bzw. `t('…')`. Neue Schlüssel immer in **allen** Sprachordnern ergänzen; Englisch ist Fallback. Tests prüfen Schlüssel und Parameter, nicht Texte.

## 2. Daten und Identität

`tuner_on` enthält u. a. `dvc_chan_id`, `mso_prdt_itm_code`, `chan_no`, `chan_no_int`, `chan_std_name`, `chan_mode_name`, `sat_name`, `dvb_chan_nw_id`, `dvb_chan_transf_strm_id`, `dvb_chan_svc_id`, `satelliteLcn_flag`, `signal_chan_id`, `fav_chan_gr_a`–`fav_chan_gr_h` und `favoriteIdxA`–`favoriteIdxH`.

Der tatsächliche zusammengesetzte **SQLite-Primärschlüssel** lautet (`dvc_chan_id`, `mso_prdt_itm_code`); eine Spalte namens `channel_unique_id` existiert **nicht**. Die Benutzeroberfläche und `tv_write.channel_map` verwenden in der getesteten Datenkonstellation `dvc_chan_id` als wesentlichen Schlüssel. Gleichlautende Sendernamen oder DVB-Kennungen dürfen trotzdem nicht zusammengeführt werden.

Belegter Mehrfacheintrag WELT HD (gleiche DVB-Dienstkennung, verschiedene LG-IDs):

```text
13    7_32_13_13_1053_21108_1
403   7_32_403_403_1053_21108_1
1015  7_32_1015_1015_1053_21108_1
```

Bei einer **normalen Umnummerierung** kann LG die ID ändern. Bei einem **Platztausch** ändern sich typischerweise beide IDs. Bei einer **Astra-Kopie** bleibt die alte ID samt originalem globalem Sendereintrag bestehen; es entsteht eine zweite ID am Ziel. Diese drei Fälle dürfen weder bei Planung noch Verifikation vermischt werden.

## 3. Tatsächlich verwendete Luna-Dienste

| Zweck | Service/Methode | Wesentliche Parameter |
| --- | --- | --- |
| Live-Senderliste | `com.webos.service.iepg/getChannelList` | `dataType`, `sort`, `channelMode`, `channelGroup`, `attribute`; **Satelliten-TV und -Radio** |
| Favorit hinzufügen | `com.webos.service.iepg/setChannelFavoriteGroup` | `channelId` (Array), `favoriteGroup` (Array) |
| Favorit entfernen | `com.webos.service.iepg/releaseChannelFavoriteGroup` | `channelId` (Array), `favoriteGroup` (Array) |
| Favoritenreihenfolge | `com.webos.service.iepg/moveChannelFavoritePriority` | `favoriteGroupId`, `channelId`, `destinationChannelId`, `direction` |
| Sendernummer / Platztausch / beobachtetes Kopierverhalten | `com.webos.service.legacybroadcast.channel/changeChannelNumber` | `channelId`, `channelNumber` |

Der gesamte produktive TV-Schreibpfad ist in `tv_write.py` implementiert. `app.py` erstellt vor dem Schreiben TV-Sicherungen und den in `SYNC_PLANS` gehaltenen zeitlich begrenzten Plan; vor Commit erfolgen ein **zweiter TV-Snapshot**, Live-Abgleich und Vergleich des Plans. Ein API-Fehler mit `errorCode` und `errorText` muss in der Diagnose erhalten bleiben.

Belegter Fall `CHANNEL_ERROR_1003 – Channel Move Denied`: **WELT HD 13→900 bzw. 13→4095** wurde verweigert, **13→99** akzeptiert. Der TV-Eingabedialog zeigt 1–99. Gleichwohl wurde **4mediathek auf 4096** über die Luna-API angenommen. Die Anwendung setzt deshalb **für alle neue Ziele die TV-UI-Regel 1–99** durch. Aus früheren 1003-Fehlern keine absolute Behauptung über Pay-TV-Flags oder einen universellen LCN-Blockiergrund ableiten.

## 4. Nummerierungs- und Kopierlogik

`app.renumber_plan()` und `app.apply_renumber()` verwalten die lokale Änderung. `tv_write.make_plan()` erstellt aus **Arbeitskopie + frischem TV-SQLite-Snapshot + Luna-Live-Liste** einen verifizierbaren Operationsplan, `tv_write.apply_operations()` führt ihn mit Zwischenprüfungen aus.

- **Einzeländerung:** Freies Ziel oder eindeutig erlaubter Platztausch; mehrere Belegungen können die manuelle Funktion blockieren. Der Name ist niemals Zuordnungsschlüssel.
- **Automatische Nummerierung:** Mehrere abhängige `number`/`swap`-Operationen und Rotationen werden aus dem Zwischenzustand geplant; global gleiche alte Nummern (z. B. NDR 101) dürfen den eindeutig über ID identifizierten Quellsender nicht automatisch sperren. Mehrdeutig belegte Ziele sind weiterhin gesperrt.
- **Astra-LCN >99 → 1–99:** LG kann auf neue Zielnummer **kopieren**, statt das Original zu verschieben. Die Live-Quelle und die neue Ziel-ID prüfen. Nach gesicherter Kopie Favorit A auf der Ziel-ID nachweislich setzen, **erst dann** A vom Original entfernen. B–H dürfen nicht geändert werden; das Original bleibt global bestehen. Nie allein aufgrund `returnValue` entscheiden.
- **Vorhandene Zielkopie:** Falls **eindeutig** dieselbe technische DVB-Identität am Zielplatz vorhanden ist, wird diese unter engen Bedingungen für Favorit A wiederverwendet, anstatt doppelt kopiert. Bei bereits in A vorhandener passender Kopie darf nach ausdrücklicher Vorschau eine doppelte A-Mitgliedschaft zusammengeführt werden, **ohne** die Kopie umzunummerieren oder das Original global zu löschen.
- **Laufzeit-Aliase:** Nach echten Nummernänderungen/Platztauschen und Kopiermigrationen müssen bestätigte neue IDs zur abschließenden Favoritensortierung und Endprüfung durchgängig verwendet werden.
- **Platztausch-Favoritenprüfung:** Unmittelbar vor dem Swap die Gruppen jedes Teilnehmers einlesen. Danach anhand der **jeweils neu bestätigten IDs** gegen exakt diesen Vorzustand prüfen. Bei Abweichung mit Gruppen/IDs stoppen. Nicht gegen den lokal gewünschten *Endzustand* vergleichen.

Mehrdeutigkeiten, unerwartete Kopien, widersprüchliche Favoritenzugehörigkeiten und Abweichungen des TV-Live-Zustands führen zu einem Abbruch. Bereits erfolgte Writes werden nicht zurückgerollt.

## 5. Lokale Daten und Entwicklungsprozess

- `app.py`: HTTP-Handler, SQLite-Import/Export, UI-Änderungen, Preflight/Commit (`prepare_tv_write`, `commit_tv_write`)
- `tv_write.py`: `channel_map`, `match_live`, `make_plan`, `apply_operations`, Live-API, Alias-Verfolgung, Kopiermigration
- `number_rules.py`: neue Programmnummern 1–99
- `static/`: Browseroberfläche und Cache-Busting
- `tests/`:  Regressionstests für Platztausch, Nummerngrenzen, Mehrfachbelegungen, Astra-Kopierlogik, A-Duplikate, Alias-Fortführung und v0.5.24-Swap-Gruppen
- `data/`: laufende Arbeitsdaten, `previous.sqlite`, `before-renumber.sqlite`, `before-single-number.sqlite`, `tv-backups/`; **nicht** Teil des Repositories/ZIPs

Vollständige chronologische Fehlergeschichte: `CHANGELOG.md`; ausführliche Agent-Übergabe einschließlich reproduzierbarer Diagnosen: `interne_notizen.md`. Historischer Originaltext dieser Datei unter `docs/archiv/TECHNISCHE_GRUNDLAGEN_v0.5.24_bisherig.md` (nur Archiv).

**Praxistest-Status:** Der Nutzer hat am 10.10.2026 eine **vollständige automatische Neunummerierung** mit v0.5.24 erfolgreich bestätigt. Das ist der letzte nachgewiesene stabile Funktionsstand. Spätere App-Versionen sind in dieser Dokumentationsrevision nicht enthalten.
