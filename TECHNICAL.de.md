# LG WebOS Channel Editor – Installation und Technik

[English](TECHNICAL.md) · **Deutsch** · Zurück zur [Bedienungsanleitung](README.de.md)

Dieses Dokument beschreibt Installation, Betrieb als Server oder Container, lokale Daten, das technische Modell und die Entwicklung. Die Bedienung des Editors steht in der [Bedienungsanleitung](README.de.md).

## Inhalt

<!-- toc -->
- [Versionsstand](#versionsstand)
- [Voraussetzungen](#voraussetzungen)
- [Installation und Start](#installation-und-start)
- [Sicherheit](#sicherheit)
- [Docker](#docker)
- [Lokale Daten und Sicherungen](#lokale-daten-und-sicherungen)
- [Funktionsstand (v0.8.1)](#funktionsstand-v081)
- [Programmnummern](#programmnummern)
- [Sprachen](#sprachen)
- [Technisches Modell und Sicherheitsinvarianten](#technisches-modell-und-sicherheitsinvarianten)
- [Entwicklungsstruktur](#entwicklungsstruktur)
- [Tests](#tests)
- [Versions- und Dokumentationspflege](#versions--und-dokumentationspflege)
<!-- /toc -->

## Versionsstand

**Aktuelle Version: v0.8.1.** Zuletzt vollständig am echten TV bestätigter Stand: **v0.5.24** (10. Oktober 2026) – vollständige automatische Neunummerierung einer Favoritenliste an einem **LG OLED55C27LA (webOS 22, Astra 19,2° E)**. Das bestätigt den konkreten getesteten Ablauf, nicht sämtliche denkbaren TV-Firmware- oder Senderkonstellationen. Mit v0.6.0 wurden Neunummerierungen (Verschieben und Tauschen, ohne dass der TV umschaltet) und das Umbenennen einer Liste am TV bestätigt; Senderkopien mit Listenübernahme sind dort noch nicht erprobt.

- v0.5.25 ergänzt den lesenden TV-Abgleichsbericht, das Hilfe-Popup, den Versions-Chip und die Lokalisierung; v0.5.26 zeigt und filtert die Empfangsart (Satellit, Kabel, Antenne).
- v0.6.0 führt die Übertragung als Hintergrund-Job mit Fortschrittsdialog, Abbruch und automatischem Re-Import aus und ändert Nummern über `iepg`; v0.6.1 bündelt Export und Import in je einem Dialog und stellt Backups auf der aktuellen Arbeitskopie wieder her; v0.6.2 ergänzt den SSH-Port im TV-Login, den v0.6.3 auch für die Übertragung nutzt; v0.6.4 nimmt die LG Channels (IP) in die Listen auf, überträgt Listen aller Empfangsarten (Satellit, Kabel, Antenne, IP) und sortiert die Liste der übrigen Sender.
- v0.7.0 kopiert, fügt ein, exportiert und importiert einzelne Favoritenlisten; v0.8.0 ergänzt die Sprachauswahl im Kopfbereich (Wechsel ohne Neuladen), 20 Oberflächensprachen, ein Rechts-nach-links-Layout und sprachunabhängige CSV-/JSON-Exporte; v0.8.1 teilt die Dokumentation in Bedienungsanleitung und dieses Dokument.

## Voraussetzungen

- **Python 3.10+** auf einem beliebigen Betriebssystem (Linux, macOS, Windows). Webserver, SQLite und Dateiimport nutzen ausschließlich die Python-Standardbibliothek. Entwickelt und getestet unter Linux.
- **Paramiko** für die Verbindung zum TV (Import per SSH, Sync-Bericht, Übertragung auf den TV): `python3 -m pip install -r requirements.txt`. Wer nur eine bereits gesicherte SQLite-Datei lädt und lokal bearbeitet, braucht Paramiko nicht.
- Für die TV-Verbindung: gerooteter LG-TV mit aktiviertem SSH und SSH-Zugang für `root`, erreichbare IP/Hostname, Root-Passwort, `sqlite3` und `luna-send` auf dem TV.
- SSH-Port: Der Login-Dialog fragt IP-Adresse und SSH-Port ab (Standard 22); der Port wird pro TV im Browser gemerkt.
- SSH-Hostschlüssel: Schlüssel aus `~/.ssh/known_hosts` werden akzeptiert. Bei einem unbekannten TV zeigt der Login-Dialog einmal den SSH-Fingerprint; nach deiner Bestätigung wird er in `data/known_hosts` gespeichert. Ändert sich der Schlüssel später, wird die Verbindung abgelehnt.

## Installation und Start

```bash
# Im Projektverzeichnis
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
python3 -m pip install -r requirements.txt
python3 app.py                   # Windows: python app.py
```

Anschließend **http://127.0.0.1:8765** im Browser öffnen. Optional:

```bash
python3 app.py --port 8766
python3 app.py --host 0.0.0.0     # im Netzwerk erreichbar (ohne Anmeldung – nur im vertrauenswürdigen Heimnetz)
python3 app.py --db /pfad/zur/bereits/gesicherten/channel.sqlite
```

Nach einem Update den laufenden Server neu starten – Python lädt den Code nur beim Start.

## Sicherheit

Standardmäßig bindet sich der Webserver **nur an `127.0.0.1`**, ohne Benutzeranmeldung (`--host` / `LG_EDITOR_HOST` ändern das, das Docker-Image lauscht auf allen Schnittstellen). **Nicht direkt ins Internet oder über einen öffentlichen Reverse Proxy freigeben.** Das TV-Root-Passwort wird für die Verbindung verwendet und nicht dauerhaft gespeichert; nur die zuletzt verwendeten Hostnamen/IPs (maximal 12) und SSH-Ports stehen im `localStorage` des jeweiligen Browsers.

## Docker

Images werden in der GitHub Container Registry für `linux/amd64` und `linux/arm64` veröffentlicht:

| Tag | Inhalt |
| --- | --- |
| `ghcr.io/robnice/lg-webos-channel-editor:latest` | neueste Release-Version |
| `ghcr.io/robnice/lg-webos-channel-editor:0.8.1` | eine feste Release-Version |
| `ghcr.io/robnice/lg-webos-channel-editor:dev` | aktueller Entwicklungsstand, nur zum Testen |

Ein Beispiel zum Kopieren ist [`docs/docker-compose.example.yml`](docs/docker-compose.example.yml): Host-Port (linke Zahl, Standard `8765`) und Host-Verzeichnis für `/app/data` anpassen, dann `docker compose up -d` (oder in das Compose-Plugin von OpenMediaVault einfügen) und `http://<server>:8765` öffnen.

- `/app/data` enthält Arbeitskopie, Sicherungen, `settings.json` und die bestätigten TV-Hostschlüssel (`known_hosts`) – einbinden, damit bei Updates nichts verloren geht.
- Beim ersten TV-Login im Container fragt der Login-Dialog nach dem SSH-Fingerprint des TV (im Container gibt es keine `~/.ssh/known_hosts`).
- Der Editor hat **keine eigene Anmeldung**: Port nur im vertrauenswürdigen Heimnetz freigeben, nie ins Internet.

Releases entstehen automatisch: Ein Tag `vX.Y.Z` auf `main` (muss zu `version.py` passen) baut nach erfolgreichen Tests `:X.Y.Z` und `:latest`; jeder Push auf `dev` baut `:dev`.

## Lokale Daten und Sicherungen

| Pfad | Funktion |
| --- | --- |
| `data/working.sqlite` | Aktuelle lokal bearbeitete SQLite-Datenbank |
| `data/previous.sqlite` | Vorherige Arbeitskopie beim **erneuten Import** (kann beim nächsten Import ersetzt werden) |
| `data/before-renumber.sqlite` | Sicherung vor lokalem automatischem Nummerierungsvorgang; bei späteren Vorgängen wieder überschreibbar |
| `data/before-single-number.sqlite` | Sicherung vor lokaler manueller Nummernänderung |
| `data/before-tv-adopt.sqlite` | Sicherung vor Übernahme von Sendern, die der TV selbst angelegt hat |
| `data/before-file-import.sqlite` | Sicherung vor dem Wiederherstellen einer Backup-Datei auf die Arbeitskopie oder dem Import einer Liste |
| `data/before-list-paste.sqlite` | Sicherung vor dem Einfügen einer kopierten Liste |
| `data/tv-backups/<Modell>-<Seriennummer>/tv-*.sqlite` | Zeitgestempelte TV-Sicherungen (Übertragungsvorschau, unmittelbar vor dem Schreiben, Neu-Einlesen vom TV), je Fernseher ein Ordner (Modell und Seriennummer, vom TV gelesen; ersatzweise `host-<IP>_<Port>`), mit `tv.json` (Modell, Seriennummer, letzte IP und Port); es bleiben je Fernseher nur die neuesten laut Einstellungen |
| `data/settings.json` | Einstellungen (Anzahl aufbewahrter TV-Sicherungen) |
| `data/known_hosts` | Im Login-Dialog bestätigte SSH-Hostschlüssel von TVs |

Der Ordner `data/` ist in `.gitignore` ausgeschlossen. **Bei Updates niemals löschen oder durch eine leere Kopie ersetzen.** Empfindliche lokale Backups nicht versehentlich in Git veröffentlichen.

SQLite-Integritätsprüfung (benötigt das `sqlite3`-Kommandozeilenprogramm):

```bash
sqlite3 data/working.sqlite 'PRAGMA integrity_check;'
```

## Funktionsstand (v0.8.1)

| Funktion | Stand |
| --- | --- |
| LG-Datenbank aus Datei oder per SSH importieren | Implementiert; TV-seitiger SQLite-Snapshot über `.backup` |
| Favoritenlisten A–H anzeigen, Sender suchen/filtern (TV/Radio, Verschlüsselung, Empfangsart), hinzufügen/entfernen | Implementiert; TV-Übertragung über Luna |
| Backup zurückspielen (Toolbar): Fernseher wählen, seine Sicherungen erscheinen nach Datum (neueste zuerst) | Implementiert; stellt nur auf der lokalen Arbeitskopie wieder her |
| Liste der übrigen Sender sortieren (im Browser gemerkt) | Implementiert |
| IP-Sender (Streams von LG Channels) als Empfangsart „IP (LG Channels)“ | Listen wie bei allen anderen Sendern, Übertragung mit denselben Aufrufen; Programmnummer gesperrt (der TV kann LG Channels nicht umnummerieren); jeder Abruf vom TV übernimmt neue IP-Sender und entfernt gelöschte, lokale Listenänderungen bleiben. Übertragung von IP- und Kabelsendern am TV noch nicht erprobt |
| Übertragung aller Empfangsarten | Listen und Nummern von Satelliten-, Kabel- und Antennensendern sowie die Listen der IP-Sender; Programmnummern sind je Empfangsart eindeutig. Der TV wird wie von LGs eigener Senderbearbeitung abgefragt (`channelMode` `["Tuner", "IP"]`) |
| Sender innerhalb einer Favoritenliste sortieren | Implementiert; TV-Übertragung mit Zustandsprüfung |
| Vom TV ausgeblendete Sender (`invisible_flag`) | Hinweis „Vom TV ausgeblendet“; Listen, Reihenfolge und Nummern wie bei allen anderen Sendern. Aufnehmen in und Entfernen aus einer Liste ist am TV bestätigt (13.10.2026); Sortieren und Umnummerieren ist noch nicht gemessen, das Rücklesen fängt eine Abweichung ab und die Fehlermeldung nennt den Sender als ausgeblendet |
| Einzelne Sendernummer ändern; belegte Nummer vergeben | Implementiert; 1–99 für **neu vergebene** Nummern; belegte Nummern als **Platztausch**, sofern eindeutig |
| Favoriten automatisch fortlaufend nummerieren | Implementiert; mehrere Schritte und Platztauschketten; mit v0.5.24 am realen TV getestet |
| Senderkopien (LG legt einen zweiten Eintrag an, wenn ein Satellitensender über 99 eine Nummer von 1–99 bekommt) | Die Kopie übernimmt alle Favoritenlisten des Senders; das Original bleibt ohne Favoriten in der globalen Liste; strenge Identitäts- und Zustandsprüfungen; ein echtes Verschieben wird ebenso akzeptiert |
| Vorhandene Senderkopien / doppelte A-Favoriten | Bedingte Wiederverwendung bzw. ausdrücklich bestätigte Zusammenführung |
| Sync-Bericht (nur lesend) | Vergleicht eine temporäre TV-Kopie mit der Arbeitskopie (keine Sicherung) |
| Einstellungen | Anzahl aufbewahrter TV-Sicherungen (Standard 30), gespeichert in `data/settings.json` |
| Auf TV übertragen | TV-Sicherung, Live-Abgleich, Vorschau, Bestätigung; Fortschrittsdialog, Abbruch zwischen den Schritten, automatischer Re-Import; bei Fehler Abbruch **ohne automatische Rückabwicklung** |
| Favoritenlisten umbenennen | Übertragung über `setGroupName` (wie LGs eigene Senderbearbeitung), Prüfung in der TV-Datenbank; mit v0.6.0 am TV bestätigt |
| Export (SQLite, CSV, JSON) und Import mit Auswahl der Wiederherstellung | Implementiert; CSV mit Rohdaten ist ein ZIP (eine CSV pro Tabelle), JSON mit Rohdaten ein vollständiges Backup; SQLite ist immer vollständig |
| Einzelne Liste kopieren/einfügen, exportieren und importieren | Implementiert; Sender werden wie beim Wiederherstellen eines Backups zugeordnet |
| Favoritenlisten oder Senderbestand vom TV neu laden | Implementiert; lokal geänderte Listen werden nur nach Bestätigung ersetzt |
| Oberfläche in 20 Sprachen | Implementiert; Pluralformen je Sprache, Rechts-nach-links-Layout für Arabisch |

## Programmnummern

**Neue Programmnummern sind auf `1–99` begrenzt**, entsprechend dem LG-Eingabedialog am getesteten TV (Astra 19,2° E). Das ist eine **bewusste UI-Regel** (`number_rules.py`), keine Behauptung, dass die Luna-API niemals höhere Nummern akzeptiert; ob andere Satelliten oder Betreiberlisten mehr erlauben, ist unbestätigt. Bereits existierende Nummern über 99 (z. B. 101, 1004, 4096) werden unverändert eingelesen und angezeigt. LG nummeriert jede Empfangsart (Satellit, Kabel, Antenne) getrennt.

## Sprachen

Die Sprache richtet sich nach `Accept-Language` des Browsers; die Auswahl im Kopfbereich wird als Cookie `lang` (ein Jahr) gespeichert und gilt vorrangig für die Seite und alle API-Meldungen. Rückfall: Region → Sprache → Englisch. In die Seite eingebettet ist nur der Katalog der aktuellen Sprache; `GET /api/i18n` liefert beim Umschalten einen anderen. Exportdateien (CSV-Kopfzeile und -Werte, JSON-Texte) sind immer englisch.

Weitere Sprachen: Ordner `locales/<sprachkürzel>/` (Regionalvarianten als `<sprache>-<REGION>`, z. B. `pt-BR`) mit einer übersetzten `messages.json` anlegen (Vorlage: `locales/en/messages.json`); fehlende Einträge fallen auf die Grundsprache und dann auf Englisch zurück. `language.name` ist der Eigenname der Sprache, `language.dir` (`ltr`/`rtl`) legt die Schreibrichtung fest, `language.intl` die Locale für Pluralformen. Texte mit Zahlen nutzen die ICU-Pluralsyntax, z. B. `{count, plural, one {# Sender} other {# Sender}}`.

## Technisches Modell und Sicherheitsinvarianten

Die relevanten LG-Daten liegen unter `/mnt/lg/cmn_data/iepg/db/channel.sql`, u. a. in `tuner_on`, `tuner_off`, `favorite_idx` und `channel_group_tuner`. `tuner_on` besitzt den zusammengesetzten Primärschlüssel **(`dvc_chan_id`, `mso_prdt_itm_code`)**. Es existiert dort **kein Feld `channel_unique_id`**. Auch die DVB-Kombination aus ONID/TSID/SID ist nicht eindeutig für jeden *LG-Listeneintrag*: WELT HD konnte z. B. gleichzeitig auf 13, 403 und 1015 vorliegen.

- **Identifikation vor Änderungen:** Originale `dvc_chan_id` aus dem frischen TV-Import als Anker; niemals anhand von Sendernamen oder lokal neu vergebenen Programmnummern auswählen. DVB-Kennung plus **ursprüngliche TV-Nummer** nur als strikt eindeutigen Fallback verwenden.
- **Identifikation nach Änderungen:** LG kann durch Umnummerieren beide IDs eines Tauschs ändern oder einen zusätzlichen Eintrag (Senderkopie) erzeugen, wenn ein Satellitensender über 99 eine Nummer von 1–99 bekommt; der Editor akzeptiert eine Kopie ebenso wie ein echtes Verschieben. Am echten TV getestet ist bisher nur Astra 19,2° E; andere Satelliten werden gleich behandelt, sind aber unbestätigt. Die **tatsächlich bestätigten** neuen IDs müssen bis zur abschließenden Favoritensortierung als Laufzeitzuordnung erhalten bleiben.
- **Zwei LG-Semantiken:** Normale Nummernänderung/Platztausch (`changeChannelNumber`) versus Kopierverhalten: Jeder bisher beobachtete Wechsel von über 99 auf 1–99 hat einen zweiten Eintrag erzeugt. Der Editor überträgt dann alle Favoritenlisten des Senders auf die Kopie, jeden Schritt live geprüft; das Original bleibt ohne Favoriten. Keine Kopie blind anlegen oder löschen.
- **Favoritengruppen bei Platztausch:** Die Mitgliedschaften **beider beteiligten realen IDs** jeweils direkt vor und nach dem konkreten Tausch vergleichen, **nicht** mit dem endgültigen lokalen Bearbeitungszustand. Das war der entscheidende Fix in v0.5.24.
- **Schreiben ausschließlich über Luna und ausdrücklich bestätigt:** `com.webos.service.iepg` für Listen/Favoriten, `com.webos.service.iepg/changeChannelNumber` für Nummern. Kein direktes Schreiben nach `/mnt/lg/cmn_data/iepg/db/channel.sql` oder `/mnt/lg/cmn_data/ldb_chmap`; `copyDvbSatelliteChannelForAstra` nicht eigenmächtig als Fallback aufrufen.
- **Gleicher Umfang live und in SQLite:** `getChannelList` wird ohne Attributfilter abgefragt. Mit `Invisible: false` lässt LG die Sender weg, die der TV selbst ausblendet und die die SQLite-Datenbank enthält; ein ausgeblendeter Sender in einer Liste wurde dann nicht gefunden („Treffer: 0“). Ohne Filter kommen sie mit `Invisible: true`.
- **Vorher prüfen, hinterher rücklesen:** Die LG-Rückgabe `returnValue` allein beweist nicht den gewünschten TV-Zustand; insbesondere wurden `false` bei Favoritenaufrufen und `true` bei Kopiervorgängen beobachtet. Mehrdeutigkeit ⇒ Abbruch, nicht raten.
- **Nicht atomar:** Bei einem späteren Fehler können vorangehende Schritte bereits am TV ausgeführt worden sein. Ein SQLite-Backup in `data/tv-backups/` ist **kein automatisches Rollback** und darf nicht durch Überschreiben der aktiven TV-Datenbank „zurückgespielt“ werden.

## Entwicklungsstruktur

```text
app.py                       Lokaler HTTP-Server, SQLite-Arbeitskopie, Import, Plan- und Commit-Endpunkte
number_rules.py              Ein einheitlicher Nummernbereich für neue Programmnummern: 1–99
tv_write.py                  TV-Live-Abfrage, Identitätsabgleich, Operationen, Verifikation
tv_inventory.py              Übernimmt vom TV selbst angelegte Sender; lädt eine Favoritenliste vom TV neu
tv_groups.py                 Überträgt umbenannte Favoritenlisten (setGroupName, Prüfung in der TV-Datenbank)
tv_login.py                  Prüft die TV-Anmeldung (SSH, benötigte Werkzeuge) einmal pro Seitenaufruf
tv_ping.py                   Erreichbarkeit des TV für den Online-Status (TCP zum SSH-Port, ohne Login)
tv_address.py                SSH-Port des TV: Standard (22) und Prüfung an einer Stelle
ip_channels.py               IP-Sender (LG Channels, Tabelle ip): Zeilen mit gesperrter Nummer, lokale Tabelle beim TV-Abruf
tv_identity.py               Identität eines TV (Modell + Seriennummer per luna-send, nur lesend)
tv_backups.py                TV-Sicherungen je Fernseher in einem Ordner: Liste, Begrenzung je TV
tv_hostkeys.py               SSH-Hostschlüssel: System-known_hosts plus beim Login bestätigte Fingerprints (data/known_hosts)
tv_job.py                    Hintergrund-Job für TV-Übertragung: Fortschritt, Abbruch zwischen Schritten, Re-Import
tv_compare.py                Nur lesender Vergleich TV-Snapshot ↔ Arbeitskopie („Sync-Bericht“)
backup_retention.py          Einstellungsdatei und automatische Begrenzung der TV-Sicherungen
backup_export.py             Export mit Auswahl: Editor-CSV/JSON, LG-Rohdaten (JSON mit Schema, CSV als ZIP)
backup_restore.py            Datei-Import: Formaterkennung, Backup-Abbild, Wiederherstellen auf die Arbeitskopie
list_transfer.py             Einfügen/Importieren in eine Liste: ersetzen oder anhängen (ListFill)
version.py                   Einzige Quelle der Versionsnummer (APP_VERSION, ?v=-Cache-Busting, Versions-Chip)
i18n.py                      Lokalisierung: Sprachaushandlung, Pluralregeln, Nachrichtenformat, Message/LocalizedError
locales/<sprache>/           messages.json je Sprache (20 Sprachen); neuer Ordner = neue Sprache
static/index.html            HTML-Template mit Platzhaltern ({{t:schlüssel}}, {{version}}, {{lang}})
static/app.js                Browserinteraktionen, Vorschau, Bestätigung
static/style.css             Darstellung
static/logo.png, favicon…    Header-Logo, Favicons und Web-App-Icons (Manifest wird je Sprache erzeugt)
requirements.txt             Python-Abhängigkeit (paramiko)
Dockerfile, .dockerignore    Container-Image; Beispiel in docs/docker-compose.example.yml
.github/workflows/           Image-Builds: Release bei v*-Tags auf main, :dev bei Pushes auf dev
tests/                       Automatisierte Regressionstests
data/                        Lokale SQLite-Daten und Backups (nicht versionieren)
```

Beispielhafte HTTP-Endpunkte: `GET /api/status`, `GET /api/channels`, `GET /api/i18n`, `GET /api/renumber/preview`, `POST /api/import` (Upload und Analyse), `POST /api/import-plan`, `POST /api/import-apply`, `POST /api/list-paste`, `POST /api/list-import`, `GET /download/<sqlite|csv|json>?lists=…&channels=all|lists&names=0|1&numbers=0|1&raw=0|1`, `POST /api/import-tv`, `POST /api/channel-number`, `POST /api/renumber`, `POST /api/tv-write-preview`, `POST /api/tv-write-commit` (startet einen Hintergrund-Job), `GET /api/tv-write-status`, `POST /api/tv-write-cancel` und `POST /api/tv-sync-report`, `GET`/`POST /api/settings`, `GET /api/tv-ping`, `GET /api/tv-backups[?tv=…]`, `POST /api/tv-backups/restore`. Die Web-App arbeitet ausschließlich über den lokalen HTTP-Server; die Verbindung zum LG übernimmt Python/Paramiko.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

Für Änderungen an Nummerierung, Identität und TV-Schreibpfad müssen insbesondere die Tests zu Platztausch, Senderkopien, vorhandenen Kopien, Mehrfachbelegungen, Laufzeit-IDs und v0.5.24-Gruppenvergleich bestehen. Simulationen sind kein Ersatz für kontrollierte Gerätetests. **Ohne Nutzerbestätigung niemals eine reale LG-Schreiboperation ausführen.**

## Versions- und Dokumentationspflege

- **v0.5.24** bleibt der letzte erfolgreich am realen Gerät getestete Funktionsstand, bis ein neuerer am TV bestätigt ist.
- Bei App-Releases `APP_VERSION` in `version.py`, die Bedienungsanleitung, dieses Dokument und die Tests konsistent halten. `?v=` und der Versions-Chip werden automatisch aus `version.py` gesetzt. Keine ungültigen verschachtelten `<script>`-/`<style>`-Tags erzeugen.
