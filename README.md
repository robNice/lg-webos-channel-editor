<p align="center"><img src="static/logo.png" alt="LG WebOS Channel Editor logo" width="256" height="256"></p>

# LG WebOS Channel Editor

**English** · [Deutsch](README.de.md)

**Current version: v0.6.0.** Last version confirmed on a real TV: **v0.5.24** (October 10, 2026). v0.6.0 adds a progress display, cancellation between steps and an automatic re-import to the transfer; the Luna write operations themselves are unchanged, but this version has not yet been tested on a TV.

Browser-based management of LG webOS channel and favorite lists that **runs locally on your computer**. The application imports an SQLite backup of the LG TV via root SSH or from a file, edits a local working copy and can transfer selected changes back **via LG Luna APIs after a TV backup, live comparison, preview and explicit confirmation**. A running LG SQLite or LevelDB file is never overwritten directly.

**Field test:** Fully automatic renumbering of a favorite list was completed successfully with **v0.5.24** on an **LG OLED55C27LA (webOS 22, Astra 19.2° E)**. This confirms the specific tested workflow, not every conceivable TV firmware or channel configuration.

## Requirements and start

- **Python 3.10+** on any operating system (Linux, macOS, Windows). Web server, SQLite and file import use the Python standard library only. Developed and tested on Linux.
- **Paramiko** for connecting to the TV (SSH import, TV comparison, transfer to the TV): `python3 -m pip install paramiko`. If you only load an already saved SQLite file and edit it locally, Paramiko is not needed.
- For the TV connection: a rooted LG TV with SSH access for `root`, a reachable IP/host name, the root password, and `sqlite3` and `luna-send` on the TV.
- On the first connection, verify the real SSH host key separately and add it to `known_hosts`. The editor rejects unknown host keys.

```bash
# In the project directory
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
python3 -m pip install paramiko
python3 app.py                   # Windows: python app.py
```

Then open **http://127.0.0.1:8765** in your browser. Optional:

```bash
python3 app.py --port 8766
python3 app.py --db /path/to/an/already/saved/channel.sqlite
```

The web server binds **exclusively to `127.0.0.1`**, without user authentication. **Do not expose it directly to the internet or via a public reverse proxy.** The TV root password is used for the connection and not stored permanently; only the most recently used host names/IPs (at most 12) are kept in the `localStorage` of the respective browser.

After an update, restart the running server – Python loads the code only at startup.

## Current features (v0.6.0)

| Feature | Status |
| --- | --- |
| Import the LG database from a file or via SSH | Implemented; TV-side SQLite snapshot via `.backup` |
| Show favorite lists A–H, search/filter channels (TV/radio, encryption, reception mode), add/remove | Implemented; transfer to the TV via Luna |
| Sort channels within a favorite list | Implemented; transfer to the TV with state verification |
| Change a single channel number by clicking the number | Implemented; 1–99 for **newly assigned** numbers |
| Assign an occupied channel number | Supported **slot swap**, if unambiguous and permitted |
| Number favorites sequentially and automatically | Implemented; multiple steps and swap chains; successfully tested on a real TV with v0.5.24 |
| Channels for which LG creates a second entry when the number changes (every change from above 99 into 1–99 observed so far) | The copy takes over all favorite lists of the channel; the original stays in the global list without favorites; only under strict identity and state checks |
| Existing Astra copies / duplicate A favorites | Conditional reuse or explicitly confirmed merge |
| TV comparison / backup (read-only) | Implemented; TV snapshot to `data/tv-backups/`, report lists the affected channels (number, favorites A–H, local only / TV only) |
| Compare TV state, back up, create preview, confirm live write | Implemented; progress dialog (step x of n), cancel between steps, automatic re-import from the TV afterwards; on error aborts **without automatic rollback** |
| Rename favorite lists | Implemented; transferred with “Transfer to TV” via `setGroupName` (as used by LG's own channel editor), verified in the TV database; confirmed on the TV with v0.6.0 for list H |
| Export the working database, CSV and JSON | Implemented |
| Reload a favorite list or the channel inventory from the TV | Implemented; replacing a locally changed list requires confirmation |
| User interface in English / German | Implemented; language from the browser setting, more languages can be added |

**New programme numbers are limited to `1–99` in this application**, matching the LG input dialog. This is a **deliberate UI rule**, not a claim that the Luna API never accepts higher numbers. Existing numbers above 99 (e.g. 101, 1004, 4096) are imported and displayed unchanged. Automatic renumbering can affect other channels and the global numbering; the preview points this out. LG numbers each reception mode (satellite, cable, antenna) separately, so a favorite list can only be renumbered if all its channels share one reception mode; channel lists from earlier cable or antenna scans stay on the TV even if nothing is connected there anymore.

### Recommended workflow

1. When the page opens, log in to the TV once (IP and root password; kept in the browser's memory only until the page is reloaded or you log out). Then use **“Import from LG”** or load an existing SQLite snapshot. An import **replaces the current local working copy**; save it beforehand via the export function if needed.
2. Edit favorites A–H, change channel numbers individually or run “Number channels automatically”. These changes happen **locally only** at first.
3. For TV changes, use **“Transfer to TV”**. The editor creates a TV backup, fetches a live channel list, computes the concrete Luna operations and shows them for confirmation. Channels the TV has created by itself since the import (LG's automatic channel update, e.g. after zapping onto another transponder) are taken over into the working copy and listed in the preview; channels removed or renamed on the TV require a new import.
4. Review the preview (especially **slot swaps**, affected other channels, **Astra copies** and possible **merges of duplicate favorites**) and explicitly confirm the execution. Immediately before writing, another backup and check are performed.
5. A progress dialog shows each step while the TV is being written; editing is locked during that time. **Cancel** stops before the next step – a step that has already started is completed and verified.
6. After success, an error or a cancellation, the editor **automatically re-imports the channel list from the TV** (with the password entered for this transfer), so you see what actually arrived on the TV. The previous working copy remains in `data/previous.sqlite`. If the transfer stops before anything was written, your local changes stay untouched. Always work on from the re-imported state: LG may change the `channelId` or create additional Astra entries when changes are made.

**Not atomic:** If an error occurs later, earlier steps may already have been executed on the TV. An SQLite backup in `data/tv-backups/` is **not an automatic rollback** and must not be “restored” by overwriting the active TV database. After an abort, first determine the actual state, then create a new plan.

## Languages

The user interface and all messages are currently available in **English** and **German**. The language follows the browser's language setting (`Accept-Language`); if no matching language is available, **English** is used. To add a language, create a folder `locales/<language code>/` with a translated `messages.json` (template: `locales/en/messages.json`); missing entries automatically fall back to English.

## Local data and backups

| Path | Purpose |
| --- | --- |
| `data/working.sqlite` | Current locally edited SQLite database |
| `data/previous.sqlite` | Previous working copy on **re-import** (may be replaced on the next import) |
| `data/before-renumber.sqlite` | Backup before a local automatic renumbering; overwritten by later runs |
| `data/before-single-number.sqlite` | Backup before a local manual number change |
| `data/before-tv-adopt.sqlite` | Backup before taking over channels the TV created by itself |
| `data/tv-backups/tv-*.sqlite` | Timestamped TV snapshots from the sync preflight |

The `data/` folder is excluded in `.gitignore`. **Never delete it or replace it with an empty copy during updates.** Do not accidentally publish sensitive local backups in Git.

SQLite integrity check (requires the `sqlite3` command-line tool):

```bash
sqlite3 data/working.sqlite 'PRAGMA integrity_check;'
```

## Technical model and safety invariants

The relevant LG data is located in `/mnt/lg/cmn_data/iepg/db/channel.sql`, among others in `tuner_on`, `tuner_off`, `favorite_idx` and `channel_group_tuner`. `tuner_on` has the composite primary key **(`dvc_chan_id`, `mso_prdt_itm_code`)**. There is **no `channel_unique_id` field**. The DVB combination of ONID/TSID/SID is not unique for every *LG list entry* either: WELT HD, for example, existed on 13, 403 and 1015 at the same time.

- **Identification before changes:** Use the original `dvc_chan_id` from the fresh TV import as the anchor; never select by channel name or by locally assigned programme numbers. Use the DVB identifier plus the **original TV number** only as a strictly unambiguous fallback.
- **Identification after changes:** Renumbering can make LG change both IDs of a swap or create an additional entry for Astra LCN. The **actually confirmed** new IDs must be kept as a runtime mapping until the final favorite sorting.
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
tv_job.py                    Background TV write job: progress, cancel between steps, re-import
tv_compare.py                Read-only comparison TV snapshot ↔ working copy ("TV comparison" report)
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

Example HTTP endpoints: `GET /api/status`, `GET /api/channels`, `GET /api/renumber/preview`, `POST /api/import`, `POST /api/import-tv`, `POST /api/channel-number`, `POST /api/renumber`, `POST /api/tv-write-preview`, `POST /api/tv-write-commit` (starts a background job), `GET /api/tv-write-status`, `POST /api/tv-write-cancel` and `POST /api/tv-sync-preflight`. The web app works exclusively through the local HTTP server; Python/Paramiko handles the connection to the LG.

### Tests

```bash
python3 -m unittest discover -s tests -v
```

For changes to numbering, identity and the TV write path, the tests for slot swaps, Astra copies, existing copies, multiple occupancy, runtime IDs and the v0.5.24 group comparison in particular must pass. Simulations are no substitute for controlled device tests. **Never perform a real LG write operation without user confirmation.**

### Version and documentation maintenance

- **v0.5.24** remains the last feature state successfully tested on a real device. v0.5.25 adds the read-only TV comparison report, the help popup, the version chip and localization; v0.5.26 shows and filters the reception mode (satellite, cable, antenna); v0.6.0 runs the transfer as a background job with progress dialog, cancellation and automatic re-import. The Luna write operations are unchanged; v0.6.0 has not yet been confirmed on a TV.
- For future app releases, keep `APP_VERSION` in `version.py`, both READMEs and the tests consistent. `?v=` and the version chip are set automatically from `version.py`. Do not create invalid nested `<script>`/`<style>` tags.

## License

[MIT](LICENSE) © 2026 robNice. Use at your own risk: changes to the TV's channel list are made via undocumented LG interfaces and cannot be rolled back automatically.
