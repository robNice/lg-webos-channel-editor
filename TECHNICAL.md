# LG WebOS Channel Editor – Installation and technical details

**English** · [Deutsch](TECHNICAL.de.md) · Back to the [user guide](README.md)

This document covers installation, operation as a server or container, local data, the technical model and development. How to use the editor is described in the [user guide](README.md).

## Contents

<!-- toc -->
- [Version status](#version-status)
- [Requirements](#requirements)
- [Installation and start](#installation-and-start)
- [Security](#security)
- [Docker](#docker)
- [Local data and backups](#local-data-and-backups)
- [Feature status (v0.8.1)](#feature-status-v081)
- [Channel numbers](#channel-numbers)
- [Languages](#languages)
- [Technical model and safety invariants](#technical-model-and-safety-invariants)
- [Project structure](#project-structure)
- [Tests](#tests)
- [Version and documentation maintenance](#version-and-documentation-maintenance)
<!-- /toc -->

## Version status

**Current version: v0.8.1.** Last version fully confirmed on a real TV: **v0.5.24** (October 10, 2026) – fully automatic renumbering of a favorite list on an **LG OLED55C27LA (webOS 22, Astra 19.2° E)**. This confirms the specific tested workflow, not every conceivable TV firmware or channel configuration. With v0.6.0, renumbering transfers (moves and swaps without the TV switching channels) and renaming a list were confirmed on the TV; channel copies with list migration have not yet been exercised there.

- v0.5.25 adds the read-only TV comparison report, the help popup, the version chip and localization; v0.5.26 shows and filters the reception mode (satellite, cable, antenna).
- v0.6.0 runs the transfer as a background job with progress dialog, cancellation and automatic re-import and changes numbers via `iepg`; v0.6.1 combines export and import into one dialog each and restores backups onto the current working copy; v0.6.2 adds the SSH port to the TV login, which v0.6.3 also uses for the transfer; v0.6.4 adds the LG Channels (IP) to the lists, transfers lists of every reception mode (satellite, cable, antenna, IP) and sorts the list of other channels.
- v0.7.0 copies, pastes, exports and imports single favorite lists; v0.8.0 adds the language selection in the header (switching without reload), 20 interface languages, a right-to-left layout and language-independent CSV/JSON exports; v0.8.1 splits the documentation into a user guide and this document.

## Requirements

- **Python 3.10+** on any operating system (Linux, macOS, Windows). Web server, SQLite and file import use the Python standard library only. Developed and tested on Linux.
- **Paramiko** for connecting to the TV (SSH import, sync report, transfer to the TV): `python3 -m pip install -r requirements.txt`. If you only load an already saved SQLite file and edit it locally, Paramiko is not needed.
- For the TV connection: a rooted LG TV with SSH enabled on the TV and SSH access for `root`, a reachable IP/host name, the root password, and `sqlite3` and `luna-send` on the TV.
- SSH port: the login dialog asks for IP address and SSH port (default 22); the port is remembered per TV in the browser.
- SSH host key: keys from `~/.ssh/known_hosts` are accepted. For an unknown TV the login dialog shows the SSH fingerprint once; after you confirm it, it is stored in `data/known_hosts`. A key that changes later is rejected.

## Installation and start

```bash
# In the project directory
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
python3 -m pip install -r requirements.txt
python3 app.py                   # Windows: python app.py
```

Then open **http://127.0.0.1:8765** in your browser. Optional:

```bash
python3 app.py --port 8766
python3 app.py --host 0.0.0.0     # reachable on the network (no login – trusted home network only)
python3 app.py --db /path/to/an/already/saved/channel.sqlite
```

After an update, restart the running server – Python loads the code only at startup.

## Security

By default the web server binds **only to `127.0.0.1`**, without user authentication (`--host` / `LG_EDITOR_HOST` change that, the Docker image listens on all interfaces). **Do not expose it directly to the internet or via a public reverse proxy.** The TV root password is used for the connection and not stored permanently; only the most recently used host names/IPs (at most 12) and SSH ports are kept in the `localStorage` of the respective browser.

## Docker

Images are published on the GitHub Container Registry for `linux/amd64` and `linux/arm64`:

| Tag | Content |
| --- | --- |
| `ghcr.io/robnice/lg-webos-channel-editor:latest` | latest release |
| `ghcr.io/robnice/lg-webos-channel-editor:0.8.1` | a fixed release version |
| `ghcr.io/robnice/lg-webos-channel-editor:dev` | current development state, for tests only |

A ready-to-copy example is [`docs/docker-compose.example.yml`](docs/docker-compose.example.yml): adjust the host port (left number, default `8765`) and the host directory for `/app/data`, then run `docker compose up -d` (or paste it into the OpenMediaVault Compose plugin) and open `http://<server>:8765`.

- `/app/data` holds the working copy, backups, `settings.json` and the confirmed TV host keys (`known_hosts`) – mount it so nothing is lost on updates.
- On the first TV login in the container the login dialog asks to confirm the TV's SSH fingerprint (there is no `~/.ssh/known_hosts` in the container).
- The editor has **no login of its own**: publish the port only in a trusted home network, never on the internet.

Releases are built automatically: a tag `vX.Y.Z` on `main` (must match `version.py`) builds `:X.Y.Z` and `:latest` after the tests passed; every push to `dev` builds `:dev`.

## Local data and backups

| Path | Purpose |
| --- | --- |
| `data/working.sqlite` | Current locally edited SQLite database |
| `data/previous.sqlite` | Previous working copy on **re-import** (may be replaced on the next import) |
| `data/before-renumber.sqlite` | Backup before a local automatic renumbering; overwritten by later runs |
| `data/before-single-number.sqlite` | Backup before a local manual number change |
| `data/before-tv-adopt.sqlite` | Backup before taking over channels the TV created by itself |
| `data/before-file-import.sqlite` | Backup before restoring a backup file onto the working copy or importing a list |
| `data/before-list-paste.sqlite` | Backup before pasting a copied list |
| `data/tv-backups/<model>-<serial>/tv-*.sqlite` | Timestamped TV backups (transfer preview, right before writing, reloads from the TV), one folder per TV (model and serial number, read from the TV; fallback `host-<ip>_<port>`), with `tv.json` (model, serial, last IP and port); only the newest ones per TV are kept as set in the settings |
| `data/settings.json` | Settings (number of TV backups to keep) |
| `data/known_hosts` | SSH host keys of TVs confirmed in the login dialog |

The `data/` folder is excluded in `.gitignore`. **Never delete it or replace it with an empty copy during updates.** Do not accidentally publish sensitive local backups in Git.

SQLite integrity check (requires the `sqlite3` command-line tool):

```bash
sqlite3 data/working.sqlite 'PRAGMA integrity_check;'
```

## Feature status (v0.8.1)

| Feature | Status |
| --- | --- |
| Import the LG database from a file or via SSH | Implemented; TV-side SQLite snapshot via `.backup` |
| Show favorite lists A–H, search/filter channels (TV/radio, encryption, reception mode), add/remove | Implemented; transfer to the TV via Luna |
| Restore backup (toolbar): choose a TV, its backups are listed newest first | Implemented; restores onto the local working copy only |
| Sort the list of other channels (remembered in the browser) | Implemented |
| IP channels (LG Channels streams) as reception mode “IP (LG Channels)” | Lists like every other channel, transferred with the same calls; programme number locked (the TV cannot renumber LG Channels); every read from the TV takes over new IP channels and drops deleted ones, local list changes stay. Transferring IP and cable channels is not yet confirmed on the TV |
| Transfer of all reception modes | Lists and numbers of satellite, cable and antenna channels and the lists of IP channels; programme numbers are unique per reception mode. The TV is asked like LG's own channel editor (`channelMode` `["Tuner", "IP"]`) |
| Sort channels within a favorite list | Implemented; transfer with state verification |
| Channels hidden by the TV (`invisible_flag`) | Marked “Hidden by the TV”; lists, order and numbers like every other channel. Adding to and removing from a list is confirmed on the TV (13.10.2026); sorting and renumbering them is not measured yet, the read-back catches a deviation and the error names the channel as hidden |
| Change a single channel number; assign an occupied number | Implemented; 1–99 for **newly assigned** numbers; occupied numbers as a **slot swap** if unambiguous |
| Number favorites sequentially and automatically | Implemented; multiple steps and swap chains; tested on a real TV with v0.5.24 |
| Channel copies (LG creates a second entry when a satellite channel above 99 gets a number from 1–99) | The copy takes over all favorite lists of the channel; the original stays in the global list without favorites; strict identity and state checks; a real move is accepted as well |
| Existing channel copies / duplicate A favorites | Conditional reuse or explicitly confirmed merge |
| Sync report (read-only) | Compares a temporary TV copy with the working copy (no backup kept) |
| Settings | Number of TV backups to keep (default 30), stored in `data/settings.json` |
| Transfer to TV | TV backup, live comparison, preview, confirmation; progress dialog, cancel between steps, automatic re-import; on error aborts **without automatic rollback** |
| Rename favorite lists | Transferred via `setGroupName` (as used by LG's own channel editor), verified in the TV database; confirmed on the TV with v0.6.0 |
| Export (SQLite, CSV, JSON) and import with restore selection | Implemented; CSV with raw data is a ZIP (one CSV per table), JSON with raw data is a complete backup; SQLite is always complete |
| Copy/paste, export and import a single list | Implemented; channels are matched like a backup restore |
| Reload favorite lists or the channel inventory from the TV | Implemented; replacing locally changed lists requires confirmation |
| User interface in 20 languages | Implemented; plural forms per language, right-to-left layout for Arabic |

## Channel numbers

**New programme numbers are limited to `1–99`**, matching the LG input dialog observed on the tested TV (Astra 19.2° E). This is a **deliberate UI rule** (`number_rules.py`), not a claim that the Luna API never accepts higher numbers; whether other satellites or operator lists allow more is unconfirmed. Existing numbers above 99 (e.g. 101, 1004, 4096) are imported and displayed unchanged. LG numbers each reception mode (satellite, cable, antenna) separately.

## Languages

The language follows the browser's `Accept-Language`; the selection in the header is stored as cookie `lang` (one year) and wins for the page and all API messages. Fallback: region → language → English. Only the catalog of the current language is embedded in the page; `GET /api/i18n` returns another one when switching. Export files (CSV header and values, JSON texts) are always English.

To add a language, create a folder `locales/<language code>/` (regional variants as `<language>-<REGION>`, e.g. `pt-BR`) with a translated `messages.json` (template: `locales/en/messages.json`); missing entries fall back to the base language and then to English. `language.name` is the language's own name, `language.dir` (`ltr`/`rtl`) sets the writing direction, `language.intl` the locale for plural forms. Texts with numbers use ICU plural syntax, e.g. `{count, plural, one {# channel} other {# channels}}`.

## Technical model and safety invariants

The relevant LG data is located in `/mnt/lg/cmn_data/iepg/db/channel.sql`, among others in `tuner_on`, `tuner_off`, `favorite_idx` and `channel_group_tuner`. `tuner_on` has the composite primary key **(`dvc_chan_id`, `mso_prdt_itm_code`)**. There is **no `channel_unique_id` field**. The DVB combination of ONID/TSID/SID is not unique for every *LG list entry* either: WELT HD, for example, existed on 13, 403 and 1015 at the same time.

- **Identification before changes:** Use the original `dvc_chan_id` from the fresh TV import as the anchor; never select by channel name or by locally assigned programme numbers. Use the DVB identifier plus the **original TV number** only as a strictly unambiguous fallback.
- **Identification after changes:** Renumbering can make LG change both IDs of a swap or create an additional entry (channel copy) when a satellite channel above 99 gets a number from 1–99; the editor accepts a copy as well as a real move. Only Astra 19.2° E has been tested on a real TV so far; other satellites are handled the same way but are unconfirmed. The **actually confirmed** new IDs must be kept as a runtime mapping until the final favorite sorting.
- **Two LG semantics:** Normal number change/slot swap (`changeChannelNumber`) versus copy behaviour: every change from above 99 into 1–99 observed so far created a second entry. The editor then moves all favorite lists of the channel to the copy, each step live-verified; the original stays without favorites. Never create or delete a copy blindly.
- **Favorite groups on slot swaps:** Compare the memberships of **both real IDs involved** directly before and after the specific swap, **not** with the final local editing state. This was the decisive fix in v0.5.24.
- **Write only via Luna and only when explicitly confirmed:** `com.webos.service.iepg` for lists/favorites, `com.webos.service.iepg/changeChannelNumber` for numbers. No direct writes to `/mnt/lg/cmn_data/iepg/db/channel.sql` or `/mnt/lg/cmn_data/ldb_chmap`; never call `copyDvbSatelliteChannelForAstra` as an automatic fallback.
- **Same scope live and in SQLite:** `getChannelList` is called without an attribute filter. With `Invisible: false` LG leaves out the channels it hides itself, which the SQLite database contains; a hidden channel in a list was then not found (“matches: 0”). Without the filter they come with `Invisible: true`.
- **Check before, read back afterwards:** LG's `returnValue` alone does not prove the desired TV state; in particular, `false` was observed for favorite calls and `true` for copy operations. Ambiguity ⇒ abort, don't guess.
- **Not atomic:** if an error occurs later, earlier steps may already have been executed on the TV. An SQLite backup in `data/tv-backups/` is **not an automatic rollback** and must not be “restored” by overwriting the active TV database.

## Project structure

```text
app.py                       Local HTTP server, SQLite working copy, import, plan and commit endpoints
number_rules.py              A single number range for new programme numbers: 1–99
tv_write.py                  TV live query, identity matching, operations, verification
tv_inventory.py              Takes over channels the TV added by itself; reloads a favorite list from the TV
tv_groups.py                 Transfers renamed favorite lists (setGroupName, verified in the TV database)
tv_login.py                  Checks the TV login (SSH, required tools) once per page view
tv_ping.py                   TV reachability for the online status (TCP to the SSH port, no login)
tv_address.py                SSH port of the TV: default (22) and validation in one place
ip_channels.py               IP channels (LG Channels, table ip): rows with locked number, local table on TV read
tv_identity.py               Identity of a TV (model + serial number via luna-send, read-only)
tv_backups.py                TV backups in one folder per TV: list, limit per TV
tv_hostkeys.py               SSH host keys: system known_hosts plus fingerprints confirmed at login (data/known_hosts)
tv_job.py                    Background TV write job: progress, cancel between steps, re-import
tv_compare.py                Read-only comparison TV snapshot ↔ working copy ("Sync report")
backup_retention.py          Settings file and automatic limit of the TV backups
backup_export.py             Export with selection: editor CSV/JSON, LG raw data (JSON with schema, CSV as ZIP)
backup_restore.py            File import: format detection, backup snapshot, restore onto the working copy
list_transfer.py             Paste/import into one list: replace or append (ListFill)
version.py                   Single source of the version number (APP_VERSION, ?v= cache busting, version chip)
i18n.py                      Localization: language negotiation, plural rules, message format, Message/LocalizedError
locales/<language>/          messages.json per language (20 languages); new folder = new language
static/index.html            HTML template with placeholders ({{t:key}}, {{version}}, {{lang}})
static/app.js                Browser interaction, preview, confirmation
static/style.css             Styling
static/logo.png, favicon…    Header logo, favicons and web app icons (manifest generated per language)
requirements.txt             Python dependency (paramiko)
Dockerfile, .dockerignore    Container image; docs/docker-compose.example.yml as example
.github/workflows/           Image builds: release on v* tags on main, :dev on pushes to dev
tests/                       Automated regression tests
data/                        Local SQLite data and backups (do not version)
```

Example HTTP endpoints: `GET /api/status`, `GET /api/channels`, `GET /api/i18n`, `GET /api/renumber/preview`, `POST /api/import` (upload and analysis), `POST /api/import-plan`, `POST /api/import-apply`, `POST /api/list-paste`, `POST /api/list-import`, `GET /download/<sqlite|csv|json>?lists=…&channels=all|lists&names=0|1&numbers=0|1&raw=0|1`, `POST /api/import-tv`, `POST /api/channel-number`, `POST /api/renumber`, `POST /api/tv-write-preview`, `POST /api/tv-write-commit` (starts a background job), `GET /api/tv-write-status`, `POST /api/tv-write-cancel` and `POST /api/tv-sync-report`, `GET`/`POST /api/settings`, `GET /api/tv-ping`, `GET /api/tv-backups[?tv=…]`, `POST /api/tv-backups/restore`. The web app works exclusively through the local HTTP server; Python/Paramiko handles the connection to the LG.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

For changes to numbering, identity and the TV write path, the tests for slot swaps, channel copies, existing copies, multiple occupancy, runtime IDs and the v0.5.24 group comparison in particular must pass. Simulations are no substitute for controlled device tests. **Never perform a real LG write operation without user confirmation.**

## Version and documentation maintenance

- **v0.5.24** remains the last feature state successfully tested on a real device until a newer one is confirmed on the TV.
- For app releases, keep `APP_VERSION` in `version.py`, the user guide, this document and the tests consistent. `?v=` and the version chip are set automatically from `version.py`. Do not create invalid nested `<script>`/`<style>` tags.
