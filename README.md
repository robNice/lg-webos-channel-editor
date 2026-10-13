<p align="center"><img src="static/logo.png" alt="LG WebOS Channel Editor logo" width="256" height="256"></p>

# LG WebOS Channel Editor

**English** · [Deutsch](README.de.md)

**Current version: v0.8.0.** Last version fully confirmed on a real TV: **v0.5.24** (October 10, 2026). With v0.6.0, renumbering transfers (moves and swaps without the TV switching channels) and renaming a list were confirmed on the TV; copies with list migration have not yet been exercised there. v0.6.1 adds one export and one import dialog; an import restores a backup onto the current working copy. v0.6.2 adds an SSH port field to the TV login; v0.6.3 makes the transfer use that port too; v0.6.4 adds the LG Channels (IP) to the lists, transfers lists of every reception mode (satellite, cable, antenna, IP) and adds a sort order for the list of other channels. v0.7.0 copies a favorite list into another list and exports or imports a single list; v0.8.0 adds a language selection in the header (switching without reload), 20 interface languages and language-independent CSV/JSON exports.

Browser-based management of LG webOS channel and favorite lists that **runs locally on your computer**. The application imports an SQLite backup of the LG TV via root SSH or from a file, edits a local working copy and can transfer selected changes back **via LG Luna APIs after a TV backup, live comparison, preview and explicit confirmation**. A running LG SQLite or LevelDB file is never overwritten directly.

**Field test:** Fully automatic renumbering of a favorite list was completed successfully with **v0.5.24** on an **LG OLED55C27LA (webOS 22, Astra 19.2° E)**. This confirms the specific tested workflow, not every conceivable TV firmware or channel configuration.

## Requirements and start

- **Python 3.10+** on any operating system (Linux, macOS, Windows). Web server, SQLite and file import use the Python standard library only. Developed and tested on Linux.
- **Paramiko** for connecting to the TV (SSH import, sync report, transfer to the TV): `python3 -m pip install -r requirements.txt`. If you only load an already saved SQLite file and edit it locally, Paramiko is not needed.
- For the TV connection: a rooted LG TV with SSH access for `root`, a reachable IP/host name, the root password, and `sqlite3` and `luna-send` on the TV.
- SSH port: the login dialog asks for IP address and SSH port (default 22); the port is remembered per TV in the browser.
- SSH host key: keys from `~/.ssh/known_hosts` are accepted. For an unknown TV the login dialog shows the SSH fingerprint once; after you confirm it, it is stored in `data/known_hosts`. A key that changes later is rejected.

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

By default the web server binds **only to `127.0.0.1`**, without user authentication (`--host` / `LG_EDITOR_HOST` change that, the Docker image listens on all interfaces). **Do not expose it directly to the internet or via a public reverse proxy.** The TV root password is used for the connection and not stored permanently; only the most recently used host names/IPs (at most 12) are kept in the `localStorage` of the respective browser.

After an update, restart the running server – Python loads the code only at startup.

## Docker

Images are published on the GitHub Container Registry for `linux/amd64` and `linux/arm64`:

| Tag | Content |
| --- | --- |
| `ghcr.io/robnice/lg-webos-channel-editor:latest` | latest release |
| `ghcr.io/robnice/lg-webos-channel-editor:0.8.0` | a fixed release version |
| `ghcr.io/robnice/lg-webos-channel-editor:dev` | current development state, for tests only |

A ready-to-copy example is [`docs/docker-compose.example.yml`](docs/docker-compose.example.yml): adjust the host port (left number, default `8765`) and the host directory for `/app/data`, then run `docker compose up -d` (or paste it into the OpenMediaVault Compose plugin) and open `http://<server>:8765`.

- `/app/data` holds the working copy, backups, `settings.json` and the confirmed TV host keys (`known_hosts`) – mount it so nothing is lost on updates.
- On the first TV login in the container the login dialog asks to confirm the TV's SSH fingerprint (there is no `~/.ssh/known_hosts` in the container).
- The editor has **no login of its own**: publish the port only in a trusted home network, never on the internet.

Releases are built automatically: a tag `vX.Y.Z` on `main` (must match `version.py`) builds `:X.Y.Z` and `:latest` after the tests passed; every push to `dev` builds `:dev`.

## Current features (v0.8.0)

| Feature | Status |
| --- | --- |
| Import the LG database from a file or via SSH | Implemented; TV-side SQLite snapshot via `.backup` |
| Show favorite lists A–H, search/filter channels (TV/radio, encryption, reception mode), add/remove | Implemented; transfer to the TV via Luna |
| Restore backup (toolbar): choose a TV, its backups are listed newest first; the chosen one opens the usual restore dialog (local working copy only) | Implemented |
| Sort the list of other channels (name, number, reception mode, satellite, free before encrypted; remembered in the browser) | Implemented |
| IP channels (LG Channels streams) as reception mode “IP (LG Channels)” | Add to lists, remove and sort like every other channel; transferred to the TV with the same calls. Their programme number is locked (the TV cannot renumber LG Channels). Every read from the TV takes over new IP channels and drops deleted ones, local list changes stay. Transferring IP and cable channels is not yet confirmed on the TV |
| Transfer of all reception modes | Lists and numbers of satellite, cable and antenna channels and the lists of IP channels; programme numbers are unique per reception mode. The TV is asked like LG's own channel editor (`channelMode` `["Tuner", "IP"]`) |
| Sort channels within a favorite list | Implemented; transfer to the TV with state verification |
| Change a single channel number by clicking the number | Implemented; 1–99 for **newly assigned** numbers |
| Assign an occupied channel number | Supported **slot swap**, if unambiguous and permitted |
| Number favorites sequentially and automatically | Implemented; multiple steps and swap chains; successfully tested on a real TV with v0.5.24 |
| Channels for which LG creates a second entry when the number changes (every change from above 99 into 1–99 observed so far) | The copy takes over all favorite lists of the channel; the original stays in the global list without favorites; only under strict identity and state checks |
| Existing channel copies / duplicate A favorites | Conditional reuse or explicitly confirmed merge |
| Sync report (read-only) | Implemented; compares a temporary TV copy with the working copy (no backup kept), report lists the affected channels (number, favorites A–H, local only / TV only) |
| Settings | Implemented; number of TV backups to keep (default 30, older ones are deleted automatically), stored in `data/settings.json` |
| Compare TV state, back up, create preview, confirm live write | Implemented; progress dialog (step x of n), cancel between steps, automatic re-import from the TV afterwards; on error aborts **without automatic rollback** |
| Rename favorite lists | Implemented; transferred with “Transfer to TV” via `setGroupName` (as used by LG's own channel editor), verified in the TV database; confirmed on the TV with v0.6.0 for list H |
| Export the working copy as SQLite, CSV or JSON | Implemented; one **Export** button; for CSV/JSON choose the contents (all channels or only list channels, lists A–H, list names, numbers, LG raw data); CSV with raw data is a ZIP (one CSV per table), JSON with raw data is a complete backup; SQLite is always complete |
| Copy a favorite list and paste it into another list | Implemented; buttons **Copy** and **Paste** below the lists: copy the selected list, select the target list, paste. The target list is either **replaced** (exactly the copied channels in their order) or the copied channels are **appended** (its channels and order stay, only missing channels are added at the end); optionally the list name is taken over. Numbers and other lists stay unchanged; takes effect on the TV with “Transfer to TV” |
| Export or import a single list | Implemented; **Export** below the lists exports only the selected list (JSON or CSV, optionally with list name and numbers; no other options shown); **Import** below the lists reads any export or backup file and puts one of its lists (selectable, e.g. list C of the file into list A) into the selected list – replace or append as with pasting, optionally with the list name. Channels are matched like a backup restore; channels that no longer exist are skipped and listed |
| Import a backup (SQLite, CSV, JSON) | Implemented; one **Import** button, format detected automatically; you choose which lists, list names and channel numbers are restored onto the current working copy (or replace it completely with an SQLite file) |
| Reload favorite lists or the channel inventory from the TV | Implemented; all lists A–H (list panel), the selected list (middle panel) or the channel inventory (right panel); replacing locally changed lists requires confirmation |
| User interface in 20 languages | Implemented; language from the browser setting or chosen in the header (remembered, switches without reload), plural forms per language, right-to-left for Arabic; more languages can be added |

**New programme numbers are limited to `1–99` in this application**, matching the LG input dialog. This is a **deliberate UI rule**, not a claim that the Luna API never accepts higher numbers. Existing numbers above 99 (e.g. 101, 1004, 4096) are imported and displayed unchanged. Automatic renumbering can affect other channels and the global numbering; the preview points this out. LG numbers each reception mode (satellite, cable, antenna) separately, so a favorite list can only be renumbered if all its channels share one reception mode; channel lists from earlier cable or antenna scans stay on the TV even if nothing is connected there anymore.

### Recommended workflow

1. When the page opens, log in to the TV once (IP and root password; kept in the browser's memory only until the page is reloaded or you log out). After the login you choose whether to load the current TV data or keep the local working copy. The toolbar shows icons; hover for the name. The TV chip shows whether the TV is reachable (green/red dot, checked every 30 seconds). Then use **“Import from TV”** (start screen or toolbar) or load a saved SQLite file via **Import**. An import from the TV **replaces the current local working copy** after a confirmation dialog (cancellable); save it beforehand via **Export** if needed.
   To restore an older backup, first import the current state from the TV, then use **Import**: the backup is applied onto the current working copy. After the upload a dialog asks what to restore: favorite lists (each separately), list names and channel numbers. Numbers only for channels of the selected lists and only within 1–99; channels on a target number move to a free number (the preview warns if channels of other lists are affected). Channels are matched by channel ID, otherwise by DVB service, name, satellite and reception mode; channels that no longer exist or are ambiguous are skipped and listed. This way the transfer to the TV keeps working even if the TV changed since the backup. Alternatively an SQLite file or a JSON export with LG raw data can replace the working copy completely (then the transfer may fail if the TV changed). Only what the file contains is offered: lists that were not exported are never emptied.
2. Edit favorites A–H, change channel numbers individually or run “Number channels automatically”. These changes happen **locally only** at first.
3. For TV changes, use **“Transfer to TV”**. The editor creates a TV backup, fetches a live channel list, computes the concrete Luna operations and shows them for confirmation. Channels the TV has created by itself since the import (LG's automatic channel update, e.g. after zapping onto another transponder) are taken over into the working copy and listed in the preview; channels removed or renamed on the TV require a new import.
4. Review the preview (especially **slot swaps**, affected other channels, **channel copies** and possible **merges of duplicate favorites**) and explicitly confirm the execution. Immediately before writing, another backup and check are performed.
5. A progress dialog shows each step while the TV is being written; editing is locked during that time. **Cancel** stops before the next step – a step that has already started is completed and verified.
6. After success, an error or a cancellation, the editor **automatically re-imports the channel list from the TV** (with the password entered for this transfer), so you see what actually arrived on the TV. The previous working copy remains in `data/previous.sqlite`. If the transfer stops before anything was written, your local changes stay untouched. Always work on from the re-imported state: LG may change the `channelId` or create additional Astra entries when changes are made.

**Not atomic:** If an error occurs later, earlier steps may already have been executed on the TV. An SQLite backup in `data/tv-backups/` is **not an automatic rollback** and must not be “restored” by overwriting the active TV database. After an abort, first determine the actual state, then create a new plan.

## Languages

The user interface and all messages are available in 20 languages: Arabic, Danish, English, Finnish, French, German, Greek, Icelandic, Italian, Japanese, Korean, Norwegian (Bokmål), Polish, Portuguese (Portugal and Brazil), Russian, Spanish, Swedish, Turkish and Ukrainian. By default the language follows the browser's language setting (`Accept-Language`); if no matching language is available, **English** is used. The **language selection in the header** overrides it: the chosen language is remembered in this browser (cookie `lang`, one year) and applies to the page and all messages; **“Browser language”** returns to the browser setting. Switching takes effect immediately without reloading the page; a TV login stays. Only the texts of the current language are loaded; another language is fetched when you switch to it. Arabic is shown right to left with a mirrored layout; channel and list names keep their own writing direction. Export files (CSV, JSON) are always in English, whatever the interface language, so they can be exchanged between users of different languages; older CSV files with German or English headers can still be imported.

To add a language, create a folder `locales/<language code>/` (regional variants as `<language>-<REGION>`, e.g. `pt-BR`) with a translated `messages.json` (template: `locales/en/messages.json`); missing entries fall back to the base language and then to English. `language.dir` (`ltr`/`rtl`) sets the writing direction, `language.intl` the locale for plural forms. Texts with numbers use ICU plural syntax, e.g. `{count, plural, one {# channel} other {# channels}}`.

## Local data and backups

| Path | Purpose |
| --- | --- |
| `data/working.sqlite` | Current locally edited SQLite database |
| `data/previous.sqlite` | Previous working copy on **re-import** (may be replaced on the next import) |
| `data/before-renumber.sqlite` | Backup before a local automatic renumbering; overwritten by later runs |
| `data/before-single-number.sqlite` | Backup before a local manual number change |
| `data/before-tv-adopt.sqlite` | Backup before taking over channels the TV created by itself |
| `data/before-file-import.sqlite` | Backup before restoring a backup file onto the working copy |
| `data/tv-backups/<model>-<serial>/tv-*.sqlite` | Timestamped TV backups (transfer preview, right before writing, reloads from the TV), one folder per TV (model and serial number, read from the TV; fallback `host-<ip>_<port>`), with `tv.json` (model, serial, last IP and port); only the newest ones per TV are kept as set in the settings |
| `data/settings.json` | Settings (number of TV backups to keep) |
| `data/known_hosts` | SSH host keys of TVs confirmed in the login dialog |

The `data/` folder is excluded in `.gitignore`. **Never delete it or replace it with an empty copy during updates.** Do not accidentally publish sensitive local backups in Git.

SQLite integrity check (requires the `sqlite3` command-line tool):

```bash
sqlite3 data/working.sqlite 'PRAGMA integrity_check;'
```

## Technical model and safety invariants

The relevant LG data is located in `/mnt/lg/cmn_data/iepg/db/channel.sql`, among others in `tuner_on`, `tuner_off`, `favorite_idx` and `channel_group_tuner`. `tuner_on` has the composite primary key **(`dvc_chan_id`, `mso_prdt_itm_code`)**. There is **no `channel_unique_id` field**. The DVB combination of ONID/TSID/SID is not unique for every *LG list entry* either: WELT HD, for example, existed on 13, 403 and 1015 at the same time.

- **Identification before changes:** Use the original `dvc_chan_id` from the fresh TV import as the anchor; never select by channel name or by locally assigned programme numbers. Use the DVB identifier plus the **original TV number** only as a strictly unambiguous fallback.
- **Identification after changes:** Renumbering can make LG change both IDs of a swap or create an additional entry (channel copy) when a satellite channel above 99 gets a number from 1–99; the editor accepts a copy as well as a real move. Only Astra 19.2° E has been tested on a real TV so far; other satellites are handled the same way but are unconfirmed. The **actually confirmed** new IDs must be kept as a runtime mapping until the final favorite sorting.
- **Two LG semantics:** Normal number change/slot swap (`changeChannelNumber`) versus copy behaviour: every change from above 99 into 1–99 observed so far created a second entry. The editor then moves all favorite lists of the channel to the copy, each step live-verified; the original stays without favorites. Never create or delete a copy blindly.
- **Favorite groups on slot swaps:** Compare the memberships of **both real IDs involved** directly before and after the specific swap, **not** with the final local editing state. This was the decisive fix in v0.5.24.
- **Write only via Luna and only when explicitly confirmed:** `com.webos.service.iepg` for lists/favorites, `com.webos.service.iepg/changeChannelNumber` for numbers. No direct writes to `/mnt/lg/cmn_data/iepg/db/channel.sql` or `/mnt/lg/cmn_data/ldb_chmap`; never call `copyDvbSatelliteChannelForAstra` as an automatic fallback.
- **Check before, read back afterwards:** LG's `returnValue` alone does not prove the desired TV state; in particular, `false` was observed for favorite calls and `true` for copy operations. Ambiguity ⇒ abort, don't guess.

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
requirements.txt             Python dependency (paramiko)
Dockerfile, .dockerignore    Container image; docs/docker-compose.example.yml as example
.github/workflows/           Image builds: release on v* tags on main, :dev on pushes to dev
tv_job.py                    Background TV write job: progress, cancel between steps, re-import
tv_compare.py                Read-only comparison TV snapshot ↔ working copy ("Sync report")
backup_retention.py          Settings file and automatic limit of the TV backups
backup_export.py             Export with selection: editor CSV/JSON, LG raw data (JSON with schema, CSV as ZIP)
backup_restore.py            File import: format detection, backup snapshot, restore onto the working copy
list_transfer.py             Paste/import into one list: replace or append (ListFill)
version.py                   Single source of the version number (APP_VERSION, ?v= cache busting, version chip)
i18n.py                      Localization: language negotiation, Message/LocalizedError, English fallback
locales/<language>/          messages.json per language (currently de, en); new folder = new language
static/index.html            HTML template with placeholders ({{t:key}}, {{version}}, {{lang}})
static/app.js                Browser interaction, preview, confirmation
static/style.css             Styling
static/logo.png, favicon…    Header logo, favicons and web app icons (manifest generated per language)
tests/                       Automated regression tests
data/                        Local SQLite data and backups (do not version)
```

Example HTTP endpoints: `GET /api/status`, `GET /api/channels`, `GET /api/renumber/preview`, `POST /api/import` (upload and analysis), `POST /api/import-plan`, `POST /api/import-apply`, `GET /download/<sqlite|csv|json>?lists=…&channels=all|lists&names=0|1&numbers=0|1&raw=0|1`, `POST /api/import-tv`, `POST /api/channel-number`, `POST /api/renumber`, `POST /api/tv-write-preview`, `POST /api/tv-write-commit` (starts a background job), `GET /api/tv-write-status`, `POST /api/tv-write-cancel` and `POST /api/tv-sync-report`, `GET`/`POST /api/settings`, `GET /api/tv-ping`, `GET /api/tv-backups[?tv=…]`, `POST /api/tv-backups/restore`. The web app works exclusively through the local HTTP server; Python/Paramiko handles the connection to the LG.

### Tests

```bash
python3 -m unittest discover -s tests -v
```

For changes to numbering, identity and the TV write path, the tests for slot swaps, channel copies, existing copies, multiple occupancy, runtime IDs and the v0.5.24 group comparison in particular must pass. Simulations are no substitute for controlled device tests. **Never perform a real LG write operation without user confirmation.**

### Version and documentation maintenance

- **v0.5.24** remains the last feature state successfully tested on a real device. v0.5.25 adds the read-only TV comparison report, the help popup, the version chip and localization; v0.5.26 shows and filters the reception mode (satellite, cable, antenna); v0.6.0 runs the transfer as a background job with progress dialog, cancellation and automatic re-import and changes numbers via `iepg` (renumbering and list renaming confirmed on the TV); v0.6.1 combines export and import into one dialog each and restores backups onto the current working copy; v0.6.2 adds the SSH port to the TV login, which v0.6.3 also uses for the transfer; v0.6.4 adds the LG Channels to the lists, transfers every reception mode and sorts the list of other channels; v0.7.0 copies, pastes, exports and imports single favorite lists; v0.8.0 adds the language selection, 20 languages and English export files.
- For future app releases, keep `APP_VERSION` in `version.py`, both READMEs and the tests consistent. `?v=` and the version chip are set automatically from `version.py`. Do not create invalid nested `<script>`/`<style>` tags.

## License

[MIT](LICENSE) © 2026 robNice. Use at your own risk: changes to the TV's channel list are made via undocumented LG interfaces and cannot be rolled back automatically.
