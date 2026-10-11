<p align="center"><img src="static/logo.png" alt="Logo LG WebOS Channel Editor" width="256" height="256"></p>

# LG WebOS Channel Editor

[English](README.md) · **Deutsch**

**Aktuelle Version: v0.6.0.** Zuletzt am echten TV bestätigter Stand: **v0.5.24** (10. Oktober 2026). v0.6.0 ergänzt die Übertragung um Fortschrittsanzeige, Abbruch zwischen den Schritten und automatischen Re-Import; die Luna-Schreiboperationen selbst sind unverändert, diese Version ist aber noch nicht am TV getestet.

Browserbasierte, **lokal auf dem Computer laufende** Verwaltung der LG-webOS-Sender- und Favoritenlisten. Die Anwendung importiert eine SQLite-Sicherung des LG-TV per Root-SSH oder aus einer Datei, bearbeitet eine lokale Arbeitskopie und kann ausgewählte Änderungen **nach TV-Backup, Live-Abgleich, Vorschau und ausdrücklicher Bestätigung über LG-Luna-APIs zurückübertragen**. Eine laufende LG-SQLite- oder LevelDB-Datei wird niemals direkt überschrieben.

**Praxistest:** Die vollständige automatische Neunummerierung einer Favoritenliste wurde mit **v0.5.24** am **LG OLED55C27LA (webOS 22, Astra 19,2° E)** erfolgreich abgeschlossen. Das bestätigt den konkreten getesteten Ablauf, nicht sämtliche denkbaren TV-Firmware- oder Senderkonstellationen.

## Voraussetzungen und Start

- **Python 3.10+** auf einem beliebigen Betriebssystem (Linux, macOS, Windows). Webserver, SQLite und Dateiimport nutzen ausschließlich die Python-Standardbibliothek. Entwickelt und getestet unter Linux.
- **Paramiko** für die Verbindung zum TV (Import per SSH, TV-Abgleich, Übertragung auf den TV): `python3 -m pip install paramiko`. Wer nur eine bereits gesicherte SQLite-Datei lädt und lokal bearbeitet, braucht Paramiko nicht.
- Für die TV-Verbindung: gerooteter LG-TV mit SSH-Zugang für `root`, erreichbare IP/Hostname, Root-Passwort, `sqlite3` und `luna-send` auf dem TV.
- Bei der ersten Verbindung den echten SSH-Hostschlüssel separat prüfen und in `known_hosts` hinterlegen. Der Editor lehnt unbekannte Hostschlüssel ab.

```bash
# Im Projektverzeichnis
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
python3 -m pip install paramiko
python3 app.py                   # Windows: python app.py
```

Anschließend **http://127.0.0.1:8765** im Browser öffnen. Optional:

```bash
python3 app.py --port 8766
python3 app.py --db /pfad/zur/bereits/gesicherten/channel.sqlite
```

Der Webserver bindet sich **ausschließlich an `127.0.0.1`**, ohne Benutzeranmeldung. **Nicht direkt ins Internet oder über einen öffentlichen Reverse Proxy freigeben.** Das TV-Root-Passwort wird für die Verbindung verwendet und nicht dauerhaft gespeichert; nur die zuletzt verwendeten Hostnamen/IPs (maximal 12) stehen im `localStorage` des jeweiligen Browsers.

Nach einem Update den laufenden Server neu starten – Python lädt den Code nur beim Start.

## Aktueller Funktionsumfang (v0.6.0)

| Funktion | Stand |
| --- | --- |
| LG-Datenbank aus Datei oder per SSH importieren | Implementiert; TV-seitiger SQLite-Snapshot über `.backup` |
| Favoritenlisten A–H anzeigen, Sender suchen/filtern (TV/Radio, Verschlüsselung, Empfangsart), hinzufügen/entfernen | Implementiert; TV-Übertragung über Luna |
| Sender innerhalb einer Favoritenliste sortieren | Implementiert; TV-Übertragung und Zustandsprüfung |
| Einzelne Sendernummer durch Klick auf die Nummer ändern | Implementiert; 1–99 für **neu vergebene** Nummern |
| Belegte Sendernummer vergeben | Unterstützter **Platztausch**, sofern eindeutig und zulässig |
| Favoriten automatisch fortlaufend nummerieren | Implementiert; mehrere Schritte und Platztauschketten; auf realem TV mit v0.5.24 erfolgreich getestet |
| Sender, bei denen LG beim Nummernwechsel einen zweiten Eintrag erzeugt (bisher jeder Wechsel von über 99 auf 1–99) | Die Kopie übernimmt alle Favoritenlisten des Senders; das Original verbleibt ohne Favoriten in der globalen Liste; nur unter strengen Identitäts- und Zustandsprüfungen |
| Vorhandene Astra-Kopien / doppelte A-Favoriten | Bedingte Wiederverwendung bzw. ausdrücklich bestätigte Zusammenführung |
| TV-Abgleich / Sicherung (nur lesend) | Implementiert; TV-Snapshot nach `data/tv-backups/`, Bericht nennt die betroffenen Sender (Nummer, Favoriten A–H, nur lokal / nur TV) |
| TV-Zustand vergleichen, sichern, Vorschau erstellen, Live-Schreiben bestätigen | Implementiert; Fortschrittsdialog (Schritt x von n), Abbruch zwischen den Schritten, danach automatischer Re-Import vom TV; bei Fehler Abbruch **ohne automatische Rückabwicklung** |
| Favoritenlisten umbenennen | Implementiert; Übertragung mit „Auf TV übertragen“ über `setGroupName` (wie LGs eigene Senderbearbeitung), Prüfung in der TV-Datenbank; mit v0.6.0 an Liste H am TV bestätigt |
| Arbeitsdatenbank, CSV und JSON exportieren | Implementiert |
| Favoritenliste oder Senderbestand vom TV neu laden | Implementiert; eine lokal geänderte Liste wird nur nach Bestätigung ersetzt |
| Oberfläche Deutsch / Englisch | Implementiert; Sprache aus der Browsereinstellung, weitere Sprachen ergänzbar |

**Neue Programmnummern sind in dieser Anwendung auf `1–99` begrenzt**, entsprechend dem LG-Eingabedialog. Das ist eine **bewusste UI-Regel**, keine Behauptung, dass die Luna-API niemals höhere Nummern akzeptiert. Bereits existierende Nummern über 99 (z. B. 101, 1004, 4096) werden unverändert eingelesen und angezeigt. Automatisches Umnummerieren kann andere Sender und die globale Nummerierung beeinflussen; die Vorschau weist darauf hin. LG nummeriert jede Empfangsart (Satellit, Kabel, Antenne) getrennt; eine Favoritenliste lässt sich daher nur durchnummerieren, wenn alle ihre Sender dieselbe Empfangsart haben. Senderlisten aus früheren Kabel- oder Antennensuchläufen bleiben auf dem TV erhalten, auch wenn dort nichts mehr angeschlossen ist.

### Empfohlener Bedienablauf

1. Beim Öffnen der Seite einmal am TV anmelden (IP und Root-Passwort; nur im Speicher des Browsers, bis die Seite neu geladen wird oder du dich abmeldest). Danach **„Vom LG importieren“** benutzen oder einen vorhandenen SQLite-Abzug laden. Ein Import **ersetzt die bisherige lokale Arbeitskopie**; vorher bei Bedarf über die Export-Funktion sichern.
2. Favoriten A–H bearbeiten, Sendernummern einzeln ändern oder „Sender automatisch nummerieren“ ausführen. Diese Änderungen finden **zunächst ausschließlich lokal** statt.
3. Für TV-Änderungen **„Auf TV übertragen“** aufrufen. Der Editor erstellt eine TV-Sicherung, holt eine Live-Senderliste, berechnet die konkreten Luna-Operationen und zeigt sie zur Bestätigung. Sender, die der TV seit dem Import selbst angelegt hat (automatische Senderaktualisierung von LG, z. B. nach dem Umschalten auf einen anderen Transponder), werden in die Arbeitskopie übernommen und in der Vorschau genannt; vom TV entfernte oder umbenannte Sender erfordern einen neuen Import.
4. Die Vorschau prüfen (insbesondere **Platztausche**, betroffene Fremdsender, **Astra-Kopien** und mögliche **Zusammenführungen doppelter Favoriten**) und die Ausführung ausdrücklich bestätigen. Unmittelbar vor dem Schreiben wird erneut gesichert und geprüft.
5. Während des Schreibens zeigt ein Fortschrittsdialog jeden Schritt; Bearbeiten ist so lange gesperrt. **Abbrechen** stoppt vor dem nächsten Schritt – ein bereits begonnener Schritt wird noch zu Ende geführt und geprüft.
6. Nach Erfolg, Fehler oder Abbruch **liest der Editor die Senderliste automatisch vom TV neu ein** (mit dem für diese Übertragung eingegebenen Passwort). So siehst du, was tatsächlich am TV angekommen ist. Die vorherige Arbeitskopie bleibt in `data/previous.sqlite`. Stoppt die Übertragung, bevor etwas geschrieben wurde, bleiben deine lokalen Änderungen unverändert. Immer vom neu eingelesenen Stand aus weiterarbeiten: LG kann bei Änderungen die `channelId` verändern oder zusätzliche Astra-Einträge anlegen.

**Nicht atomar:** Bei einem späteren Fehler können vorangehende Schritte bereits am TV ausgeführt worden sein. Ein SQLite-Backup in `data/tv-backups/` ist **kein automatisches Rollback** und darf nicht durch Überschreiben der aktiven TV-Datenbank „zurückgespielt“ werden. Bei Abbruch erst Ist-Zustand ermitteln, dann neue Planung erstellen.

## Sprachen

Die Oberfläche und alle Meldungen gibt es derzeit auf **Deutsch** und **Englisch**. Die Sprache richtet sich nach der Spracheinstellung des Browsers (`Accept-Language`); ist keine passende Sprache vorhanden, wird **Englisch** verwendet. Weitere Sprachen: Ordner `locales/<sprachkürzel>/` mit einer übersetzten `messages.json` anlegen (Vorlage: `locales/en/messages.json`); fehlende Einträge fallen automatisch auf Englisch zurück.

## Lokale Daten und Sicherungen

| Pfad | Funktion |
| --- | --- |
| `data/working.sqlite` | Aktuelle lokal bearbeitete SQLite-Datenbank |
| `data/previous.sqlite` | Vorherige Arbeitskopie beim **erneuten Import** (kann beim nächsten Import ersetzt werden) |
| `data/before-renumber.sqlite` | Sicherung vor lokalem automatischem Nummerierungsvorgang; bei späteren Vorgängen wieder überschreibbar |
| `data/before-single-number.sqlite` | Sicherung vor lokaler manueller Nummernänderung |
| `data/before-tv-adopt.sqlite` | Sicherung vor Übernahme von Sendern, die der TV selbst angelegt hat |
| `data/tv-backups/tv-*.sqlite` | Zeitgestempelte TV-Snapshots aus dem Sync-Preflight |

Der Ordner `data/` ist in `.gitignore` ausgeschlossen. **Bei Updates niemals löschen oder durch eine leere Kopie ersetzen.** Empfindliche lokale Backups nicht versehentlich in Git veröffentlichen.

SQLite-Integritätsprüfung (benötigt das `sqlite3`-Kommandozeilenprogramm):

```bash
sqlite3 data/working.sqlite 'PRAGMA integrity_check;'
```

## Technisches Modell und Sicherheitsinvarianten

Die relevanten LG-Daten liegen unter `/mnt/lg/cmn_data/iepg/db/channel.sql`, u. a. in `tuner_on`, `tuner_off`, `favorite_idx` und `channel_group_tuner`. `tuner_on` besitzt den zusammengesetzten Primärschlüssel **(`dvc_chan_id`, `mso_prdt_itm_code`)**. Es existiert dort **kein Feld `channel_unique_id`**. Auch die DVB-Kombination aus ONID/TSID/SID ist nicht eindeutig für jeden *LG-Listeneintrag*: WELT HD konnte z. B. gleichzeitig auf 13, 403 und 1015 vorliegen.

- **Identifikation vor Änderungen:** Originale `dvc_chan_id` aus dem frischen TV-Import als Anker; niemals anhand von Sendernamen oder lokal neu vergebenen Programmnummern auswählen. DVB-Kennung plus **ursprüngliche TV-Nummer** nur als strikt eindeutigen Fallback verwenden.
- **Identifikation nach Änderungen:** LG kann durch Umnummerieren beide IDs eines Tauschs ändern oder bei Astra-LCN einen zusätzlichen Eintrag erzeugen. Die **tatsächlich bestätigten** neuen IDs müssen bis zur abschließenden Favoritensortierung als Laufzeitzuordnung erhalten bleiben.
- **Zwei LG-Semantiken:** Normale Nummernänderung/Platztausch (`changeChannelNumber`) versus Kopierverhalten: Jeder bisher beobachtete Wechsel von über 99 auf 1–99 hat einen zweiten Eintrag erzeugt. Der Editor überträgt dann alle Favoritenlisten des Senders auf die Kopie, jeden Schritt live geprüft; das Original bleibt ohne Favoriten. Keine Kopie blind anlegen oder löschen.
- **Favoritengruppen bei Platztausch:** Die Mitgliedschaften **beider beteiligten realen IDs** jeweils direkt vor und nach dem konkreten Tausch vergleichen, **nicht** mit dem endgültigen lokalen Bearbeitungszustand. Das war der entscheidende Fix in v0.5.24.
- **Schreiben ausschließlich über Luna und ausdrücklich bestätigt:** `com.webos.service.iepg` für Listen/Favoriten, `com.webos.service.iepg/changeChannelNumber` für Nummern. Kein direktes Schreiben nach `/mnt/lg/cmn_data/iepg/db/channel.sql` oder `/mnt/lg/cmn_data/ldb_chmap`; `copyDvbSatelliteChannelForAstra` nicht eigenmächtig als Fallback aufrufen.
- **Vorher prüfen, hinterher rücklesen:** Die LG-Rückgabe `returnValue` allein beweist nicht den gewünschten TV-Zustand; insbesondere wurden `false` bei Favoritenaufrufen und `true` bei Kopiervorgängen beobachtet. Mehrdeutigkeit ⇒ Abbruch, nicht raten.

## Entwicklungsstruktur

```text
app.py                       Lokaler HTTP-Server, SQLite-Arbeitskopie, Import, Plan- und Commit-Endpunkte
number_rules.py              Ein einheitlicher Nummernbereich für neue Programmnummern: 1–99
tv_write.py                  TV-Live-Abfrage, Identitätsabgleich, Operationen, Verifikation
tv_inventory.py              Übernimmt vom TV selbst angelegte Sender; lädt eine Favoritenliste vom TV neu
tv_groups.py                 Überträgt umbenannte Favoritenlisten (setGroupName, Prüfung in der TV-Datenbank)
tv_login.py                  Prüft die TV-Anmeldung (SSH, benötigte Werkzeuge) einmal pro Seitenaufruf
tv_job.py                    Hintergrund-Job für TV-Übertragung: Fortschritt, Abbruch zwischen Schritten, Re-Import
tv_compare.py                Nur lesender Vergleich TV-Snapshot ↔ Arbeitskopie (Bericht „TV-Abgleich“)
version.py                   Einzige Quelle der Versionsnummer (APP_VERSION, ?v=-Cache-Busting, Versions-Chip)
i18n.py                      Lokalisierung: Sprachaushandlung, Message/LocalizedError, Fallback Englisch
locales/<sprache>/           messages.json je Sprache (derzeit de, en); neuer Ordner = neue Sprache
static/index.html            HTML-Template mit Platzhaltern ({{t:schlüssel}}, {{version}}, {{lang}})
static/app.js                Browserinteraktionen, Vorschau, Bestätigung
static/style.css             Darstellung
static/logo.png, favicon…    Header-Logo, Favicons und Web-App-Icons (Manifest wird je Sprache erzeugt)
tests/                       Automatisierte Regressionstests
data/                        Lokale SQLite-Daten und Backups (nicht versionieren)
```

Beispielhafte HTTP-Endpunkte: `GET /api/status`, `GET /api/channels`, `GET /api/renumber/preview`, `POST /api/import`, `POST /api/import-tv`, `POST /api/channel-number`, `POST /api/renumber`, `POST /api/tv-write-preview`, `POST /api/tv-write-commit` (startet einen Hintergrund-Job), `GET /api/tv-write-status`, `POST /api/tv-write-cancel` und `POST /api/tv-sync-preflight`. Die Web-App arbeitet ausschließlich über den lokalen HTTP-Server; die Verbindung zum LG übernimmt Python/Paramiko.

### Tests

```bash
python3 -m unittest discover -s tests -v
```

Für Änderungen an Nummerierung, Identität und TV-Schreibpfad müssen insbesondere die Tests zu Platztausch, Astra-Kopien, vorhandenen Kopien, Mehrfachbelegungen, Laufzeit-IDs und v0.5.24-Gruppenvergleich bestehen. Simulationen sind kein Ersatz für kontrollierte Gerätetests. **Ohne Nutzerbestätigung niemals eine reale LG-Schreiboperation ausführen.**

### Versions- und Dokumentationspflege

- **v0.5.24** bleibt der letzte erfolgreich am realen Gerät getestete Funktionsstand. v0.5.25 ergänzt den lesenden TV-Abgleichsbericht, das Hilfe-Popup, den Versions-Chip und die Lokalisierung; v0.5.26 zeigt und filtert die Empfangsart (Satellit, Kabel, Antenne); v0.6.0 führt die Übertragung als Hintergrund-Job mit Fortschrittsdialog, Abbruch und automatischem Re-Import aus. Die Luna-Schreiboperationen sind unverändert; v0.6.0 ist noch nicht am TV bestätigt.
- Bei künftigen App-Releases `APP_VERSION` in `version.py`, beide READMEs und Tests konsistent halten. `?v=` und der Versions-Chip werden automatisch aus `version.py` gesetzt. Keine ungültigen verschachtelten `<script>`-/`<style>`-Tags erzeugen.

## Lizenz

[MIT](LICENSE) © 2026 robNice. Nutzung auf eigenes Risiko: Änderungen an der Senderliste des TV erfolgen über undokumentierte LG-Schnittstellen und lassen sich nicht automatisch rückgängig machen.
