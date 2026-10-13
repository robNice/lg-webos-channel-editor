<p align="center"><img src="static/logo.png" alt="Logo LG WebOS Channel Editor" width="256" height="256"></p>

# LG WebOS Channel Editor

[English](README.md) · **Deutsch**

**Aktuelle Version: v0.8.0.** Zuletzt vollständig am echten TV bestätigter Stand: **v0.5.24** (10. Oktober 2026). Mit v0.6.0 wurden Neunummerierungen (Verschieben und Tauschen, ohne dass der TV umschaltet) und das Umbenennen einer Liste am TV bestätigt; Kopien mit Listenübernahme sind dort noch nicht erprobt. v0.6.1 bündelt Export und Import in je einem Dialog; ein Import stellt ein Backup auf der aktuellen Arbeitskopie wieder her. v0.6.2 ergänzt ein Feld für den SSH-Port im TV-Login; v0.6.3 nutzt diesen Port auch bei der Übertragung; v0.6.4 nimmt die LG Channels (IP) in die Listen auf, überträgt Listen aller Empfangsarten (Satellit, Kabel, Antenne, IP) und bietet eine Sortierung für die Liste der übrigen Sender. v0.7.0 kopiert eine Favoritenliste in eine andere Liste und exportiert oder importiert einzelne Listen; v0.8.0 ergänzt eine Sprachauswahl im Kopfbereich (Wechsel ohne Neuladen), 20 Oberflächensprachen und sprachunabhängige CSV-/JSON-Exporte.

Browserbasierte, **lokal auf dem Computer laufende** Verwaltung der LG-webOS-Sender- und Favoritenlisten. Die Anwendung importiert eine SQLite-Sicherung des LG-TV per Root-SSH oder aus einer Datei, bearbeitet eine lokale Arbeitskopie und kann ausgewählte Änderungen **nach TV-Backup, Live-Abgleich, Vorschau und ausdrücklicher Bestätigung über LG-Luna-APIs zurückübertragen**. Eine laufende LG-SQLite- oder LevelDB-Datei wird niemals direkt überschrieben.

**Praxistest:** Die vollständige automatische Neunummerierung einer Favoritenliste wurde mit **v0.5.24** am **LG OLED55C27LA (webOS 22, Astra 19,2° E)** erfolgreich abgeschlossen. Das bestätigt den konkreten getesteten Ablauf, nicht sämtliche denkbaren TV-Firmware- oder Senderkonstellationen.

## Voraussetzungen und Start

- **Python 3.10+** auf einem beliebigen Betriebssystem (Linux, macOS, Windows). Webserver, SQLite und Dateiimport nutzen ausschließlich die Python-Standardbibliothek. Entwickelt und getestet unter Linux.
- **Paramiko** für die Verbindung zum TV (Import per SSH, Sync-Bericht, Übertragung auf den TV): `python3 -m pip install -r requirements.txt`. Wer nur eine bereits gesicherte SQLite-Datei lädt und lokal bearbeitet, braucht Paramiko nicht.
- Für die TV-Verbindung: gerooteter LG-TV mit SSH-Zugang für `root`, erreichbare IP/Hostname, Root-Passwort, `sqlite3` und `luna-send` auf dem TV.
- SSH-Port: Der Login-Dialog fragt IP-Adresse und SSH-Port ab (Standard 22); der Port wird pro TV im Browser gemerkt.
- SSH-Hostschlüssel: Schlüssel aus `~/.ssh/known_hosts` werden akzeptiert. Bei einem unbekannten TV zeigt der Login-Dialog einmal den SSH-Fingerprint; nach deiner Bestätigung wird er in `data/known_hosts` gespeichert. Ändert sich der Schlüssel später, wird die Verbindung abgelehnt.

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

Standardmäßig bindet sich der Webserver **nur an `127.0.0.1`**, ohne Benutzeranmeldung (`--host` / `LG_EDITOR_HOST` ändern das, das Docker-Image lauscht auf allen Schnittstellen). **Nicht direkt ins Internet oder über einen öffentlichen Reverse Proxy freigeben.** Das TV-Root-Passwort wird für die Verbindung verwendet und nicht dauerhaft gespeichert; nur die zuletzt verwendeten Hostnamen/IPs (maximal 12) stehen im `localStorage` des jeweiligen Browsers.

Nach einem Update den laufenden Server neu starten – Python lädt den Code nur beim Start.

## Docker

Images werden in der GitHub Container Registry für `linux/amd64` und `linux/arm64` veröffentlicht:

| Tag | Inhalt |
| --- | --- |
| `ghcr.io/robnice/lg-webos-channel-editor:latest` | neueste Release-Version |
| `ghcr.io/robnice/lg-webos-channel-editor:0.8.0` | eine feste Release-Version |
| `ghcr.io/robnice/lg-webos-channel-editor:dev` | aktueller Entwicklungsstand, nur zum Testen |

Ein Beispiel zum Kopieren ist [`docs/docker-compose.example.yml`](docs/docker-compose.example.yml): Host-Port (linke Zahl, Standard `8765`) und Host-Verzeichnis für `/app/data` anpassen, dann `docker compose up -d` (oder in das Compose-Plugin von OpenMediaVault einfügen) und `http://<server>:8765` öffnen.

- `/app/data` enthält Arbeitskopie, Sicherungen, `settings.json` und die bestätigten TV-Hostschlüssel (`known_hosts`) – einbinden, damit bei Updates nichts verloren geht.
- Beim ersten TV-Login im Container fragt der Login-Dialog nach dem SSH-Fingerprint des TV (im Container gibt es keine `~/.ssh/known_hosts`).
- Der Editor hat **keine eigene Anmeldung**: Port nur im vertrauenswürdigen Heimnetz freigeben, nie ins Internet.

Releases entstehen automatisch: Ein Tag `vX.Y.Z` auf `main` (muss zu `version.py` passen) baut nach erfolgreichen Tests `:X.Y.Z` und `:latest`; jeder Push auf `dev` baut `:dev`.

## Aktueller Funktionsumfang (v0.8.0)

| Funktion | Stand |
| --- | --- |
| LG-Datenbank aus Datei oder per SSH importieren | Implementiert; TV-seitiger SQLite-Snapshot über `.backup` |
| Favoritenlisten A–H anzeigen, Sender suchen/filtern (TV/Radio, Verschlüsselung, Empfangsart), hinzufügen/entfernen | Implementiert; TV-Übertragung über Luna |
| Backup zurückspielen (Toolbar): Fernseher wählen, seine Sicherungen erscheinen nach Datum (neueste zuerst); die gewählte öffnet den gewohnten Wiederherstellen-Dialog (nur lokale Arbeitskopie) | Implementiert |
| Liste der übrigen Sender sortieren (Name, Nummer, Empfangsart, Satellit, frei vor verschlüsselt; im Browser gemerkt) | Implementiert |
| IP-Sender (Streams von LG Channels) als Empfangsart „IP (LG Channels)“ | In Listen aufnehmen, entfernen und sortieren wie alle anderen Sender; Übertragung zum TV mit denselben Aufrufen. Die Programmnummer ist gesperrt (der TV kann LG Channels nicht umnummerieren). Jeder Abruf vom TV übernimmt neue IP-Sender und entfernt gelöschte, lokale Listenänderungen bleiben erhalten. Übertragung von IP- und Kabelsendern am TV noch nicht erprobt |
| Übertragung aller Empfangsarten | Listen und Nummern von Satelliten-, Kabel- und Antennensendern sowie die Listen der IP-Sender; Programmnummern sind je Empfangsart eindeutig. Der TV wird wie von LGs eigener Senderbearbeitung abgefragt (`channelMode` `["Tuner", "IP"]`) |
| Sender innerhalb einer Favoritenliste sortieren | Implementiert; TV-Übertragung und Zustandsprüfung |
| Einzelne Sendernummer durch Klick auf die Nummer ändern | Implementiert; 1–99 für **neu vergebene** Nummern |
| Belegte Sendernummer vergeben | Unterstützter **Platztausch**, sofern eindeutig und zulässig |
| Favoriten automatisch fortlaufend nummerieren | Implementiert; mehrere Schritte und Platztauschketten; auf realem TV mit v0.5.24 erfolgreich getestet |
| Sender, bei denen LG beim Nummernwechsel einen zweiten Eintrag erzeugt (bisher jeder Wechsel von über 99 auf 1–99) | Die Kopie übernimmt alle Favoritenlisten des Senders; das Original verbleibt ohne Favoriten in der globalen Liste; nur unter strengen Identitäts- und Zustandsprüfungen |
| Vorhandene Astra-Kopien / doppelte A-Favoriten | Bedingte Wiederverwendung bzw. ausdrücklich bestätigte Zusammenführung |
| Sync-Bericht (nur lesend) | Implementiert; vergleicht eine temporäre TV-Kopie mit der Arbeitskopie (keine Sicherung), Bericht nennt die betroffenen Sender (Nummer, Favoriten A–H, nur lokal / nur TV) |
| Einstellungen | Implementiert; Anzahl aufbewahrter TV-Sicherungen (Standard 30, ältere werden automatisch gelöscht), gespeichert in `data/settings.json` |
| TV-Zustand vergleichen, sichern, Vorschau erstellen, Live-Schreiben bestätigen | Implementiert; Fortschrittsdialog (Schritt x von n), Abbruch zwischen den Schritten, danach automatischer Re-Import vom TV; bei Fehler Abbruch **ohne automatische Rückabwicklung** |
| Favoritenlisten umbenennen | Implementiert; Übertragung mit „Auf TV übertragen“ über `setGroupName` (wie LGs eigene Senderbearbeitung), Prüfung in der TV-Datenbank; mit v0.6.0 an Liste H am TV bestätigt |
| Arbeitskopie als SQLite, CSV oder JSON exportieren | Implementiert; ein **Export**-Button; für CSV/JSON ist der Inhalt wählbar (alle Sender oder nur Listensender, Listen A–H, Listennamen, Nummern, LG-Rohdaten); CSV mit Rohdaten ist ein ZIP (eine CSV pro Tabelle), JSON mit Rohdaten ein vollständiges Backup; SQLite ist immer vollständig |
| Favoritenliste kopieren und in eine andere Liste einfügen | Implementiert; Buttons **Kopieren** und **Einfügen** unter den Listen: ausgewählte Liste kopieren, Zielliste auswählen, einfügen. Die Zielliste wird entweder **ersetzt** (genau die kopierten Sender in ihrer Reihenfolge) oder die kopierten Sender werden **angehängt** (ihre Sender und Reihenfolge bleiben, nur fehlende kommen ans Ende); optional wird der Listenname übernommen. Nummern und andere Listen bleiben unverändert; wirkt auf dem TV mit „Auf TV übertragen“ |
| Einzelne Liste exportieren oder importieren | Implementiert; **Exportieren** unter den Listen exportiert nur die ausgewählte Liste (JSON oder CSV, wahlweise mit Listennamen und Nummern; keine weiteren Optionen); **Importieren** unter den Listen liest jede Export- oder Sicherungsdatei und übernimmt eine ihrer Listen (wählbar, z. B. Liste C der Datei in Liste A) in die ausgewählte Liste – ersetzen oder anhängen wie beim Einfügen, optional mit Listennamen. Sender werden wie beim Wiederherstellen eines Backups zugeordnet; nicht mehr vorhandene werden übersprungen und genannt |
| Backup importieren (SQLite, CSV, JSON) | Implementiert; ein **Import**-Button, Format wird automatisch erkannt; du wählst, welche Listen, Listennamen und Programmnummern auf die aktuelle Arbeitskopie übernommen werden (oder ersetzt sie mit einer SQLite-Datei komplett) |
| Favoritenlisten oder Senderbestand vom TV neu laden | Implementiert; alle Listen A–H (Listen-Spalte), die gewählte Liste (Mitte) oder den Senderbestand (rechts); lokal geänderte Listen werden nur nach Bestätigung ersetzt |
| Oberfläche in 20 Sprachen | Implementiert; Sprache aus der Browsereinstellung oder per Auswahl im Kopfbereich (gemerkt, Wechsel ohne Neuladen), Pluralformen je Sprache, Arabisch von rechts nach links; weitere Sprachen ergänzbar |

**Neue Programmnummern sind in dieser Anwendung auf `1–99` begrenzt**, entsprechend dem LG-Eingabedialog. Das ist eine **bewusste UI-Regel**, keine Behauptung, dass die Luna-API niemals höhere Nummern akzeptiert. Bereits existierende Nummern über 99 (z. B. 101, 1004, 4096) werden unverändert eingelesen und angezeigt. Automatisches Umnummerieren kann andere Sender und die globale Nummerierung beeinflussen; die Vorschau weist darauf hin. LG nummeriert jede Empfangsart (Satellit, Kabel, Antenne) getrennt; eine Favoritenliste lässt sich daher nur durchnummerieren, wenn alle ihre Sender dieselbe Empfangsart haben. Senderlisten aus früheren Kabel- oder Antennensuchläufen bleiben auf dem TV erhalten, auch wenn dort nichts mehr angeschlossen ist.

### Empfohlener Bedienablauf

1. Beim Öffnen der Seite einmal am TV anmelden (IP und Root-Passwort; nur im Speicher des Browsers, bis die Seite neu geladen wird oder du dich abmeldest). Nach dem Login wählst du, ob die aktuellen TV-Daten geladen werden oder die lokale Arbeitskopie bleibt. Die Toolbar zeigt Icons; der Name erscheint beim Darüberfahren. Der TV-Chip zeigt, ob der TV erreichbar ist (grüner/roter Punkt, Prüfung alle 30 Sekunden). Danach **„Vom TV importieren“** benutzen (Startbildschirm oder Toolbar) oder eine gesicherte SQLite-Datei über **Import** laden. Ein Import vom TV **ersetzt die bisherige lokale Arbeitskopie** nach einer Rückfrage (abbrechbar); vorher bei Bedarf über **Export** sichern.
   Um ein älteres Backup wiederherzustellen, zuerst den aktuellen Stand vom TV importieren, dann **Import** benutzen: Das Backup wird auf die aktuelle Arbeitskopie angewendet. Nach dem Hochladen fragt ein Dialog, was übernommen werden soll: Favoritenlisten (einzeln), Listennamen und Programmnummern. Nummern nur für Sender der gewählten Listen und nur 1–99; Sender auf einer Zielnummer weichen auf eine freie Nummer aus (die Vorschau warnt, wenn Sender anderer Listen betroffen sind). Sender werden über die Kanal-ID zugeordnet, sonst über DVB-Dienst, Name, Satellit und Empfangsart; nicht mehr vorhandene oder mehrdeutige Sender werden übersprungen und aufgelistet. So bleibt die Übertragung zum TV möglich, auch wenn sich der TV seit dem Backup verändert hat. Alternativ kann eine SQLite-Datei oder ein JSON-Export mit LG-Rohdaten die Arbeitskopie komplett ersetzen (dann kann die Übertragung scheitern, falls sich der TV geändert hat). Angeboten wird nur, was die Datei enthält: nicht exportierte Listen werden nie geleert.
2. Favoriten A–H bearbeiten, Sendernummern einzeln ändern oder „Sender automatisch nummerieren“ ausführen. Diese Änderungen finden **zunächst ausschließlich lokal** statt.
3. Für TV-Änderungen **„Auf TV übertragen“** aufrufen. Der Editor erstellt eine TV-Sicherung, holt eine Live-Senderliste, berechnet die konkreten Luna-Operationen und zeigt sie zur Bestätigung. Sender, die der TV seit dem Import selbst angelegt hat (automatische Senderaktualisierung von LG, z. B. nach dem Umschalten auf einen anderen Transponder), werden in die Arbeitskopie übernommen und in der Vorschau genannt; vom TV entfernte oder umbenannte Sender erfordern einen neuen Import.
4. Die Vorschau prüfen (insbesondere **Platztausche**, betroffene Fremdsender, **Astra-Kopien** und mögliche **Zusammenführungen doppelter Favoriten**) und die Ausführung ausdrücklich bestätigen. Unmittelbar vor dem Schreiben wird erneut gesichert und geprüft.
5. Während des Schreibens zeigt ein Fortschrittsdialog jeden Schritt; Bearbeiten ist so lange gesperrt. **Abbrechen** stoppt vor dem nächsten Schritt – ein bereits begonnener Schritt wird noch zu Ende geführt und geprüft.
6. Nach Erfolg, Fehler oder Abbruch **liest der Editor die Senderliste automatisch vom TV neu ein** (mit dem für diese Übertragung eingegebenen Passwort). So siehst du, was tatsächlich am TV angekommen ist. Die vorherige Arbeitskopie bleibt in `data/previous.sqlite`. Stoppt die Übertragung, bevor etwas geschrieben wurde, bleiben deine lokalen Änderungen unverändert. Immer vom neu eingelesenen Stand aus weiterarbeiten: LG kann bei Änderungen die `channelId` verändern oder zusätzliche Astra-Einträge anlegen.

**Nicht atomar:** Bei einem späteren Fehler können vorangehende Schritte bereits am TV ausgeführt worden sein. Ein SQLite-Backup in `data/tv-backups/` ist **kein automatisches Rollback** und darf nicht durch Überschreiben der aktiven TV-Datenbank „zurückgespielt“ werden. Bei Abbruch erst Ist-Zustand ermitteln, dann neue Planung erstellen.

## Sprachen

Die Oberfläche und alle Meldungen gibt es in 20 Sprachen: Arabisch, Dänisch, Deutsch, Englisch, Finnisch, Französisch, Griechisch, Isländisch, Italienisch, Japanisch, Koreanisch, Norwegisch (Bokmål), Polnisch, Portugiesisch (Portugal und Brasilien), Russisch, Schwedisch, Spanisch, Türkisch und Ukrainisch. Standardmäßig richtet sich die Sprache nach der Spracheinstellung des Browsers (`Accept-Language`); ist keine passende Sprache vorhanden, wird **Englisch** verwendet. Die **Sprachauswahl im Kopfbereich** hat Vorrang: Die gewählte Sprache wird in diesem Browser gemerkt (Cookie `lang`, ein Jahr) und gilt für die Seite und alle Meldungen; **„Browsersprache“** kehrt zur Browsereinstellung zurück. Der Wechsel wirkt sofort, ohne die Seite neu zu laden; eine TV-Anmeldung bleibt bestehen. Geladen werden nur die Texte der aktuellen Sprache; eine andere Sprache wird erst beim Umschalten abgerufen. Arabisch wird von rechts nach links dargestellt (das Layout für Rechts-nach-links-Sprachen wird noch verfeinert). Exportdateien (CSV, JSON) sind unabhängig von der Oberflächensprache immer englisch, damit sie zwischen Nutzern verschiedener Sprachen austauschbar sind; ältere CSV-Dateien mit deutscher oder englischer Kopfzeile lassen sich weiterhin importieren.

Weitere Sprachen: Ordner `locales/<sprachkürzel>/` (Regionalvarianten als `<sprache>-<REGION>`, z. B. `pt-BR`) mit einer übersetzten `messages.json` anlegen (Vorlage: `locales/en/messages.json`); fehlende Einträge fallen auf die Grundsprache und dann auf Englisch zurück. `language.dir` (`ltr`/`rtl`) legt die Schreibrichtung fest, `language.intl` die Locale für Pluralformen. Texte mit Zahlen nutzen die ICU-Pluralsyntax, z. B. `{count, plural, one {# Sender} other {# Sender}}`.

## Lokale Daten und Sicherungen

| Pfad | Funktion |
| --- | --- |
| `data/working.sqlite` | Aktuelle lokal bearbeitete SQLite-Datenbank |
| `data/previous.sqlite` | Vorherige Arbeitskopie beim **erneuten Import** (kann beim nächsten Import ersetzt werden) |
| `data/before-renumber.sqlite` | Sicherung vor lokalem automatischem Nummerierungsvorgang; bei späteren Vorgängen wieder überschreibbar |
| `data/before-single-number.sqlite` | Sicherung vor lokaler manueller Nummernänderung |
| `data/before-tv-adopt.sqlite` | Sicherung vor Übernahme von Sendern, die der TV selbst angelegt hat |
| `data/before-file-import.sqlite` | Sicherung vor dem Wiederherstellen einer Backup-Datei auf die Arbeitskopie |
| `data/tv-backups/<Modell>-<Seriennummer>/tv-*.sqlite` | Zeitgestempelte TV-Sicherungen (Übertragungsvorschau, unmittelbar vor dem Schreiben, Neu-Einlesen vom TV), je Fernseher ein Ordner (Modell und Seriennummer, vom TV gelesen; ersatzweise `host-<IP>_<Port>`), mit `tv.json` (Modell, Seriennummer, letzte IP und Port); es bleiben je Fernseher nur die neuesten laut Einstellungen |
| `data/settings.json` | Einstellungen (Anzahl aufbewahrter TV-Sicherungen) |
| `data/known_hosts` | Im Login-Dialog bestätigte SSH-Hostschlüssel von TVs |

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
tv_ping.py                   Erreichbarkeit des TV für den Online-Status (TCP zum SSH-Port, ohne Login)
tv_address.py                SSH-Port des TV: Standard (22) und Prüfung an einer Stelle
ip_channels.py               IP-Sender (LG Channels, Tabelle ip): Zeilen mit gesperrter Nummer, lokale Tabelle beim TV-Abruf
tv_identity.py               Identität eines TV (Modell + Seriennummer per luna-send, nur lesend)
tv_backups.py                TV-Sicherungen je Fernseher in einem Ordner: Liste, Begrenzung je TV
tv_hostkeys.py               SSH-Hostschlüssel: System-known_hosts plus beim Login bestätigte Fingerprints (data/known_hosts)
requirements.txt             Python-Abhängigkeit (paramiko)
Dockerfile, .dockerignore    Container-Image; Beispiel in docs/docker-compose.example.yml
.github/workflows/           Image-Builds: Release bei v*-Tags auf main, :dev bei Pushes auf dev
tv_job.py                    Hintergrund-Job für TV-Übertragung: Fortschritt, Abbruch zwischen Schritten, Re-Import
tv_compare.py                Nur lesender Vergleich TV-Snapshot ↔ Arbeitskopie („Sync-Bericht“)
backup_retention.py          Einstellungsdatei und automatische Begrenzung der TV-Sicherungen
backup_export.py             Export mit Auswahl: Editor-CSV/JSON, LG-Rohdaten (JSON mit Schema, CSV als ZIP)
backup_restore.py            Datei-Import: Formaterkennung, Backup-Abbild, Wiederherstellen auf die Arbeitskopie
list_transfer.py             Einfügen/Importieren in eine Liste: ersetzen oder anhängen (ListFill)
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

Beispielhafte HTTP-Endpunkte: `GET /api/status`, `GET /api/channels`, `GET /api/renumber/preview`, `POST /api/import` (Upload und Analyse), `POST /api/import-plan`, `POST /api/import-apply`, `GET /download/<sqlite|csv|json>?lists=…&channels=all|lists&names=0|1&numbers=0|1&raw=0|1`, `POST /api/import-tv`, `POST /api/channel-number`, `POST /api/renumber`, `POST /api/tv-write-preview`, `POST /api/tv-write-commit` (startet einen Hintergrund-Job), `GET /api/tv-write-status`, `POST /api/tv-write-cancel` und `POST /api/tv-sync-report`, `GET`/`POST /api/settings`, `GET /api/tv-ping`, `GET /api/tv-backups[?tv=…]`, `POST /api/tv-backups/restore`. Die Web-App arbeitet ausschließlich über den lokalen HTTP-Server; die Verbindung zum LG übernimmt Python/Paramiko.

### Tests

```bash
python3 -m unittest discover -s tests -v
```

Für Änderungen an Nummerierung, Identität und TV-Schreibpfad müssen insbesondere die Tests zu Platztausch, Astra-Kopien, vorhandenen Kopien, Mehrfachbelegungen, Laufzeit-IDs und v0.5.24-Gruppenvergleich bestehen. Simulationen sind kein Ersatz für kontrollierte Gerätetests. **Ohne Nutzerbestätigung niemals eine reale LG-Schreiboperation ausführen.**

### Versions- und Dokumentationspflege

- **v0.5.24** bleibt der letzte erfolgreich am realen Gerät getestete Funktionsstand. v0.5.25 ergänzt den lesenden TV-Abgleichsbericht, das Hilfe-Popup, den Versions-Chip und die Lokalisierung; v0.5.26 zeigt und filtert die Empfangsart (Satellit, Kabel, Antenne); v0.6.0 führt die Übertragung als Hintergrund-Job mit Fortschrittsdialog, Abbruch und automatischem Re-Import aus und ändert Nummern über `iepg` (Neunummerierung und Listen-Umbenennung am TV bestätigt); v0.6.1 bündelt Export und Import in je einem Dialog und stellt Backups auf der aktuellen Arbeitskopie wieder her; v0.6.2 ergänzt den SSH-Port im TV-Login, den v0.6.3 auch für die Übertragung nutzt; v0.6.4 nimmt die LG Channels in die Listen auf, überträgt alle Empfangsarten und sortiert die Liste der übrigen Sender; v0.7.0 kopiert, fügt ein, exportiert und importiert einzelne Favoritenlisten; v0.8.0 ergänzt die Sprachauswahl, 20 Sprachen und englische Exportdateien.
- Bei künftigen App-Releases `APP_VERSION` in `version.py`, beide READMEs und Tests konsistent halten. `?v=` und der Versions-Chip werden automatisch aus `version.py` gesetzt. Keine ungültigen verschachtelten `<script>`-/`<style>`-Tags erzeugen.

## Lizenz

[MIT](LICENSE) © 2026 robNice. Nutzung auf eigenes Risiko: Änderungen an der Senderliste des TV erfolgen über undokumentierte LG-Schnittstellen und lassen sich nicht automatisch rückgängig machen.
