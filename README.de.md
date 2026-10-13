<p align="center"><img src="static/logo.png" alt="Logo LG WebOS Channel Editor" width="256" height="256"></p>

# LG WebOS Channel Editor

[English](README.md) · **Deutsch**

Bearbeite die Sender- und Favoritenlisten deines LG-webOS-Fernsehers bequem im Browser: Favoritenlisten A–H sortieren, Sender hinzufügen und entfernen, Sendernummern ändern oder eine ganze Liste automatisch durchnummerieren, Listen umbenennen, kopieren, exportieren und importieren. Der Editor **läuft lokal auf deinem Computer**, arbeitet mit einer Kopie der Senderliste und ändert den Fernseher erst, wenn du deine Änderungen ausdrücklich überträgst – nach einer Sicherung, einer Vorschau und deiner Bestätigung.

Der Editor **kommuniziert direkt mit dem Fernseher** über dein Heimnetz: Er liest die Senderliste vom TV und schreibt deine Änderungen zurück – ohne USB-Stick, ohne Umweg über LGs eigenen Export. **Diese direkte Verbindung setzt einen gerooteten LG-Fernseher voraus, auf dem SSH aktiviert ist** (siehe [Was du brauchst](#was-du-brauchst)).

**Installation, Docker, Datenordner und technische Details:** siehe [Installation und Technik](TECHNICAL.de.md).

Version 0.8.1. Getestet an einem LG OLED55C27LA (webOS 22) mit Satellitenempfang Astra 19,2° E; andere Fernseher und Satelliten sind noch nicht getestet. Nutzung auf eigenes Risiko – siehe [Gut zu wissen](#gut-zu-wissen).

## Inhalt

<!-- toc -->
- [Was du brauchst](#was-du-brauchst)
- [Die Oberfläche im Überblick](#die-oberfläche-im-überblick)
- [Erste Schritte](#erste-schritte)
- [Favoritenlisten bearbeiten](#favoritenlisten-bearbeiten)
- [Sendernummern](#sendernummern)
- [Einzelne Listen kopieren, exportieren und importieren](#einzelne-listen-kopieren-exportieren-und-importieren)
- [Änderungen auf den Fernseher übertragen](#änderungen-auf-den-fernseher-übertragen)
- [Prüfen und neu laden](#prüfen-und-neu-laden)
- [Sicherungen, Export und Import](#sicherungen-export-und-import)
- [Sprache](#sprache)
- [Gut zu wissen](#gut-zu-wissen)
- [Lizenz](#lizenz)
<!-- /toc -->

## Was du brauchst

- Einen **gerooteten LG-webOS-Fernseher**, auf dem **SSH aktiviert** ist, mit SSH-Zugang für den Benutzer `root` (IP-Adresse oder Hostname, SSH-Port, Root-Passwort).
- Den Editor auf deinem Computer oder Heimserver ([Installation](TECHNICAL.de.md#installation-und-start)), im Browser geöffnet, standardmäßig unter **http://127.0.0.1:8765**.

Ohne TV-Verbindung kannst du trotzdem eine gesicherte Senderdatei laden, bearbeiten und exportieren.

## Die Oberfläche im Überblick

- **Kopfbereich:** TV-Status (grüner Punkt = TV erreichbar, Prüfung alle 30 Sekunden), mit dem TV verbinden bzw. abmelden, Sprache, Einstellungen und **?** (Hinweise zur Bearbeitung). Die Symbole der Werkzeugleiste zeigen ihren Namen, wenn du mit der Maus darüberfährst: **Auf TV übertragen**, **Sync-Bericht**, **Vom TV importieren**, **Import**, **Backup zurückspielen**, **Export**.
- **Favoritenlisten** (links): Listen A–H mit der Anzahl ihrer Sender. Ein Klick wählt eine Liste aus. Darunter: **Kopieren**, **Einfügen**, **Exportieren**, **Importieren**, **Liste umbenennen**, **Sender automatisch nummerieren**.
- **Ausgewählte Liste** (Mitte): die Sender der ausgewählten Liste in ihrer Reihenfolge, mit Suche und Filtern.
- **Alle übrigen Sender** (rechts): alle Sender, die nicht in der ausgewählten Liste stehen, mit Suche, Filtern und Sortierung.

In Sprachen, die von rechts nach links geschrieben werden (Arabisch), ist die Oberfläche gespiegelt. Änderungen werden automatisch in der lokalen Arbeitskopie gespeichert.

## Erste Schritte

1. Beim Öffnen der Seite fragt der Editor nach der TV-Anmeldung: **IP-Adresse / Hostname**, **SSH-Port** (meist 22) und **Root-Passwort**. Das Passwort bleibt nur im Speicher des Browsers, bis du die Seite neu lädst oder dich abmeldest; es wird nie gespeichert. Bei der ersten Verbindung zu einem Fernseher bestätigst du einmal seinen SSH-Fingerprint.
   Ohne Fernseher: **Ohne TV fortfahren** wählen.
2. Nach der Anmeldung wählst du, ob die aktuelle Senderliste vom TV geladen wird oder ob du mit deiner lokalen Arbeitskopie weiterarbeitest.
3. **Vom TV importieren** (Werkzeugleiste) liest jederzeit die aktuelle Senderliste vom TV. Das **ersetzt deine lokale Arbeitskopie** nach einer Rückfrage; exportiere sie vorher, wenn du sie behalten willst.

## Favoritenlisten bearbeiten

- **Hinzufügen:** bei **Alle übrigen Sender** auf **Hinzufügen** klicken – der Sender kommt ans Ende der ausgewählten Liste.
- **Entfernen:** in der ausgewählten Liste auf **Entfernen** klicken.
- **Reihenfolge ändern:** Sender in der ausgewählten Liste am Griff (⠿) ziehen.
- **Sender finden:** nach Name oder Nummer suchen; nach TV/Radio, frei/verschlüsselt und Empfangsart (Satellit, Kabel, Antenne, IP) filtern. Die Suche wirkt nur auf die Anzeige. Die Liste der übrigen Sender lässt sich sortieren (Name, Nummer, Empfangsart, Satellit, frei vor verschlüsselt); die Wahl merkt sich der Browser.
- **Liste umbenennen:** Liste auswählen und auf **Liste umbenennen** klicken.

**IP-Sender** (Streams von LG Channels) erscheinen als Empfangsart „IP (LG Channels)“. Du kannst sie wie alle anderen Sender in Listen aufnehmen und sortieren; ihre Nummer lässt sich nicht ändern.

**Vom TV ausgeblendete Sender:** Der TV blendet manche Sender in seiner Senderliste selbst aus (z. B. Regionalvarianten oder Dienste ohne Namen). Der Editor zeigt sie mit dem Hinweis „Vom TV ausgeblendet“. Du kannst sie wie alle anderen Sender in Favoritenlisten aufnehmen; der TV zeigt sie dann in dieser Liste an, in seiner Gesamtliste bleiben sie ausgeblendet. Aufnehmen und Entfernen ist am TV bestätigt; Sortieren und Umnummerieren ausgeblendeter Sender ist am TV noch nicht getestet.

## Sendernummern

- **Einzelne Nummer ändern:** auf die Nummer eines Senders klicken (✎) und die neue Nummer eingeben.
- **Erlaubt sind 1–99** für neue Nummern, wie im Nummerneditor des Fernsehers. Vorhandene Nummern über 99 bleiben, bis du sie änderst.
- **Belegte Nummer:** Hat bereits ein anderer Sender die Nummer, tauschen die beiden Sender ihre Plätze.
- **Automatisch nummerieren:** Liste auswählen und auf **Sender automatisch nummerieren** klicken. Du wählst die erste Nummer; die Sender werden in Listenreihenfolge durchnummeriert. Sender, die im Weg stehen, werden verschoben; die Rückfrage nennt sie, auch Sender anderer Listen.
- Jede Empfangsart (Satellit, Kabel, Antenne) hat eigene Nummern. Eine Liste lässt sich nur automatisch nummerieren, wenn alle ihre Sender dieselbe Empfangsart haben.

## Einzelne Listen kopieren, exportieren und importieren

- **Kopieren und einfügen:** Liste auswählen, **Kopieren** klicken, Zielliste auswählen, **Einfügen** klicken. Du wählst, ob die Zielliste **ersetzt** wird (genau die kopierten Sender in ihrer Reihenfolge) oder die Sender **angehängt** werden (nur noch nicht enthaltene Sender kommen ans Ende), und ob der Listenname übernommen wird.
- **Liste exportieren:** **Exportieren** unter den Listen speichert nur die ausgewählte Liste als JSON oder CSV, wahlweise mit Listennamen und Sendernummern.
- **In eine Liste importieren:** **Importieren** unter den Listen liest eine Export- oder Sicherungsdatei. Du wählst, welche Liste der Datei in die ausgewählte Liste kommt (z. B. Liste C der Datei in Liste A), ersetzen oder anhängen und optional den Listennamen. Nicht mehr vorhandene Sender werden übersprungen und genannt.

Nummern und die übrigen Listen bleiben unverändert. Das alles geschieht lokal; der Fernseher ändert sich erst mit **Auf TV übertragen**.

## Änderungen auf den Fernseher übertragen

Alle Bearbeitungen ändern zunächst nur deine lokale Arbeitskopie. So kommen sie auf den Fernseher:

1. Auf **Auf TV übertragen** klicken. Der Editor sichert die Senderliste des Fernsehers, vergleicht sie mit seinem aktuellen Zustand und zeigt eine **Vorschau** aller geplanten Schritte: Listenänderungen, Nummernänderungen, Platztausche, Senderkopien (siehe unten) und Zusammenführungen doppelter Favoriten.
2. Die Vorschau prüfen und **bestätigen**. Vorher wird nichts geschrieben.
3. Ein Fortschrittsdialog zeigt jeden Schritt; Bearbeiten ist so lange gesperrt. **Abbrechen** stoppt vor dem nächsten Schritt – der laufende Schritt wird noch zu Ende geführt und geprüft.
4. Danach – nach Erfolg, Fehler oder Abbruch – **liest der Editor die Senderliste erneut vom TV**. So siehst du, was tatsächlich angekommen ist. Arbeite immer von diesem Stand aus weiter.

Sender, die der Fernseher seit deinem Import selbst angelegt hat (z. B. nach einer Senderaktualisierung), werden übernommen und in der Vorschau genannt. Wurden am TV Sender entfernt oder umbenannt, zuerst erneut vom TV importieren.

**Senderkopien:** Bekommt ein Satellitensender mit einer Nummer über 99 eine Nummer von 1–99, legt der Fernseher einen zweiten Eintrag (eine Kopie) an, statt ihn zu verschieben. Der Editor überträgt die Favoritenlisten des Senders auf die Kopie; das Original bleibt in der Gesamtsenderliste des Fernsehers.

## Prüfen und neu laden

- **Sync-Bericht** (Werkzeugleiste): vergleicht den Fernseher mit deiner Arbeitskopie, ohne etwas zu ändern, und listet die Unterschiede (Nummern, Favoriten A–H, Sender nur lokal oder nur am TV).
- **Vom TV neu laden** (↻-Knöpfe): alle Favoritenlisten (Listen-Spalte), nur die ausgewählte Liste (Mitte) oder den Senderbestand (rechts, übernimmt neue TV-Sender). Lokal geänderte Listen werden nur nach Rückfrage ersetzt.

## Sicherungen, Export und Import

- **Export** (Werkzeugleiste): speichert die Arbeitskopie als **SQLite** (immer vollständig, die beste Sicherung), **CSV** (für Tabellenkalkulationen) oder **JSON**. Bei CSV/JSON wählst du den Inhalt: alle Sender oder nur die in Listen, welche Listen, Listennamen, Nummern und optional die LG-Rohdaten. Exportdateien sind unabhängig von der Oberflächensprache immer englisch.
- **Import** (Werkzeugleiste): liest eine SQLite-, CSV-, ZIP- oder JSON-Datei; das Format wird automatisch erkannt. Du wählst, was auf deine aktuelle Arbeitskopie übernommen wird: Favoritenlisten (einzeln), Listennamen und Sendernummern. Sender werden auch dann zugeordnet, wenn sich der Fernseher seit der Sicherung verändert hat; nicht mehr vorhandene werden übersprungen und genannt. Alternativ kann eine SQLite-Datei (oder ein JSON-Export mit LG-Rohdaten) die Arbeitskopie komplett ersetzen.
- **Backup zurückspielen** (Werkzeugleiste): Der Editor sichert den Fernseher vor jeder Übertragung und bei jedem Lesen vom TV. Fernseher und Sicherung nach Datum wählen; sie wird wie ein Import auf die Arbeitskopie übernommen.
- **Einstellungen:** Anzahl aufbewahrter TV-Sicherungen pro Fernseher (Standard 30); ältere werden automatisch gelöscht.

Einen älteren Stand auf den Fernseher zurückbringen: zuerst vom TV importieren, dann die Sicherung zurückspielen und **Auf TV übertragen**.

## Sprache

Die Oberfläche gibt es in 20 Sprachen: Arabisch, Dänisch, Deutsch, Englisch, Finnisch, Französisch, Griechisch, Isländisch, Italienisch, Japanisch, Koreanisch, Norwegisch (Bokmål), Polnisch, Portugiesisch (Portugal und Brasilien), Russisch, Schwedisch, Spanisch, Türkisch und Ukrainisch. Standardmäßig richtet sie sich nach der Sprache deines Browsers, sonst Englisch. Die **Sprachauswahl im Kopfbereich** hat Vorrang, wirkt sofort ohne Neuladen und wird in diesem Browser gemerkt; **Browsersprache** kehrt zur Browsereinstellung zurück.

## Gut zu wissen

- **Übertragungen sind nicht atomar:** Tritt ein Fehler auf, können frühere Schritte bereits am Fernseher ausgeführt sein. Es gibt keine automatische Rückabwicklung. Lies den Stand erneut vom TV und plane neu.
- **Eine TV-Sicherung nicht durch Kopieren von Dateien auf den Fernseher zurückspielen.** Nutze **Backup zurückspielen** oder **Import** und übertrage die Änderungen.
- **Bestätigt ist nur die getestete Kombination:** ein LG OLED55C27LA (webOS 22) mit Astra 19,2° E. Andere Modelle, Firmware-Stände, Satelliten oder Übertragungen von Kabel-, Antennen- und IP-Sendern können sich anders verhalten.
- Die **Nummerngrenze 1–99** folgt dem Nummerneditor des getesteten Fernsehers; sie gilt für alle neuen Nummern.
- Der Editor hat **keine eigene Anmeldung**. Betreibe ihn nur auf deinem Computer oder im vertrauenswürdigen Heimnetz, nie im Internet ([Sicherheit](TECHNICAL.de.md#sicherheit)).
- Behalte bei Updates den Ordner `data/` – er enthält deine Arbeitskopie und die Sicherungen ([Details](TECHNICAL.de.md#lokale-daten-und-sicherungen)).

## Lizenz

[MIT](LICENSE) © 2026 robNice. Nutzung auf eigenes Risiko: Änderungen an der Senderliste des TV erfolgen über undokumentierte LG-Schnittstellen und lassen sich nicht automatisch rückgängig machen.
