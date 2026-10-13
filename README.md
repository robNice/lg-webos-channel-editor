<p align="center"><img src="static/logo.png" alt="LG WebOS Channel Editor logo" width="256" height="256"></p>

# LG WebOS Channel Editor

**English** · [Deutsch](README.de.md)

Edit the channel and favorite lists of your LG webOS TV comfortably in the browser: sort favorite lists A–H, add and remove channels, change channel numbers or number a whole list automatically, rename, copy, export and import lists. The editor **runs locally on your computer**, works on a copy of the TV's channel list and changes the TV only when you explicitly transfer your changes – after a backup, a preview and your confirmation.

The editor **communicates directly with the TV** over your home network: it reads the channel list from the TV and writes your changes back – no USB stick, no detour via LG's own export. **This direct connection requires a rooted LG TV on which SSH is enabled** (see [What you need](#what-you-need)).

**Installation, Docker, data folders and technical details:** see [Installation and technical details](TECHNICAL.md).

Version 0.8.1. Tested on an LG OLED55C27LA (webOS 22) with satellite reception Astra 19.2° E; other TVs and satellites have not been tested yet. Use at your own risk – see [Good to know](#good-to-know).

## Contents

<!-- toc -->
- [What you need](#what-you-need)
- [The screen at a glance](#the-screen-at-a-glance)
- [Getting started](#getting-started)
- [Editing favorite lists](#editing-favorite-lists)
- [Channel numbers](#channel-numbers)
- [Copying, exporting and importing a single list](#copying-exporting-and-importing-a-single-list)
- [Transferring changes to the TV](#transferring-changes-to-the-tv)
- [Checking and reloading](#checking-and-reloading)
- [Backups, export and import](#backups-export-and-import)
- [Language](#language)
- [Good to know](#good-to-know)
- [License](#license)
<!-- /toc -->

## What you need

- A **rooted LG webOS TV** with **SSH enabled** on the TV, and SSH access for the user `root` (IP address or host name, SSH port, root password).
- The editor running on your computer or home server ([installation](TECHNICAL.md#installation-and-start)), opened in the browser, by default at **http://127.0.0.1:8765**.

Without a TV connection you can still load a saved channel file, edit it and export it.

## The screen at a glance

- **Header:** TV status (green dot = TV reachable, checked every 30 seconds), connect to/log out from the TV, language, settings and **?** (editing notes). The toolbar icons show their name when you hover over them: **Transfer to TV**, **Sync report**, **Import from TV**, **Import**, **Restore backup**, **Export**.
- **Favorite lists** (left): lists A–H with the number of channels. Click a list to select it. Below: **Copy**, **Paste**, **Export**, **Import**, **Rename list**, **Number channels automatically**.
- **Selected list** (middle): the channels of the selected list in their order, with search and filters.
- **All other channels** (right): all channels that are not in the selected list, with search, filters and sort order.

In right-to-left languages (Arabic) the layout is mirrored. Changes are saved automatically in the local working copy.

## Getting started

1. When the page opens, the editor asks for the TV login: **IP address / host name**, **SSH port** (usually 22) and the **root password**. The password is kept only in the browser's memory until you reload the page or log out; it is never saved. On the first connection to a TV you confirm its SSH fingerprint once.
   Without a TV: choose **Continue without TV**.
2. After the login you choose whether to load the current channel list from the TV or to keep working with your local working copy.
3. **Import from TV** (toolbar) reads the current channel list from the TV at any time. It **replaces your local working copy** after a confirmation; export it beforehand if you want to keep it.

## Editing favorite lists

- **Add:** in **All other channels**, click **Add** – the channel is appended to the selected list.
- **Remove:** in the selected list, click **Remove**.
- **Change the order:** drag channels by the handle (⠿) in the selected list.
- **Find channels:** search by name or number; filter by TV/radio, free/encrypted and reception mode (satellite, cable, antenna, IP). The search only affects the display. The list of other channels can be sorted (name, number, reception mode, satellite, free before encrypted); the choice is remembered in the browser.
- **Rename list:** select the list and click **Rename list**.

**IP channels** (LG Channels streams) appear as reception mode “IP (LG Channels)”. You can put them into lists and sort them like every other channel; their number cannot be changed.

**Channels hidden by the TV:** the TV hides some channels in its channel list by itself (e.g. regional variants or services without a name). The editor shows them with the note “Hidden by the TV”. You can put them into favorite lists like every other channel; the TV then shows them in that list, and they stay hidden in its overall channel list. Adding and removing is confirmed on the TV; sorting and renumbering hidden channels has not been tested on a TV yet.

## Channel numbers

- **Change a single number:** click the number of a channel (✎) and enter the new number.
- **Allowed are 1–99** for new numbers, as in the TV's own number editor. Existing numbers above 99 stay as they are until you change them.
- **Occupied number:** if another channel already has the number, the two channels swap their slots.
- **Number automatically:** select a list and click **Number channels automatically**. Choose the first number; the channels are numbered in list order. Other channels that are in the way are moved; the confirmation shows which ones, including channels of other lists.
- Each reception mode (satellite, cable, antenna) has its own numbers. A list can only be numbered automatically if all its channels have the same reception mode.

## Copying, exporting and importing a single list

- **Copy and paste:** select a list, click **Copy**, select the target list, click **Paste**. Choose whether the target list is **replaced** (exactly the copied channels in their order) or the channels are **appended** (only channels not yet in it are added at the end), and optionally take over the list name.
- **Export a list:** **Export** below the lists saves only the selected list as JSON or CSV, optionally with list name and channel numbers.
- **Import into a list:** **Import** below the lists reads an export or backup file. You choose which list of the file goes into the selected list (e.g. list C of the file into list A), replace or append, and optionally the list name. Channels that no longer exist are skipped and listed.

Numbers and the other lists stay unchanged. All of this happens locally; the TV changes only with **Transfer to TV**.

## Transferring changes to the TV

All edits first change only your local working copy. To bring them to the TV:

1. Click **Transfer to TV**. The editor backs up the TV's channel list, compares it with the TV's current state and shows a **preview** of every planned step: list changes, number changes, slot swaps, channel copies (see below) and merges of duplicate favorites.
2. Check the preview and **confirm** it. Nothing is written before.
3. A progress dialog shows each step; editing is locked meanwhile. **Cancel** stops before the next step – the running step is still completed and checked.
4. Afterwards – after success, an error or a cancellation – the editor **reads the channel list from the TV again**, so you see what actually arrived on the TV. Always continue working from this state.

Channels the TV has added by itself since your import (e.g. after a channel update) are taken over and named in the preview. If channels were removed or renamed on the TV, import from the TV again first.

**Channel copies:** when a satellite channel numbered above 99 gets a number from 1–99, the TV creates a second entry (a copy) instead of moving it. The editor moves the channel's favorite lists to the copy; the original stays in the TV's overall channel list.

## Checking and reloading

- **Sync report** (toolbar): compares the TV with your working copy without changing anything and lists the differences (numbers, favorites A–H, channels only local or only on the TV).
- **Reload from the TV** (↻ buttons): all favorite lists (list panel), only the selected list (middle) or the channel inventory (right, takes over new TV channels). Locally changed lists are only replaced after a confirmation.

## Backups, export and import

- **Export** (toolbar): saves the working copy as **SQLite** (always complete, the best backup), **CSV** (for spreadsheets) or **JSON**. For CSV/JSON you choose the contents: all channels or only those in lists, which lists, list names, numbers and optionally the LG raw data. Export files are always in English, whatever the interface language.
- **Import** (toolbar): reads an SQLite, CSV, ZIP or JSON file; the format is detected automatically. You choose what to take over onto your current working copy: favorite lists (each separately), list names and channel numbers. Channels are matched even if the TV has changed since the backup; channels that no longer exist are skipped and listed. Alternatively an SQLite file (or a JSON export with LG raw data) can replace the working copy completely.
- **Restore backup** (toolbar): the editor keeps a backup of the TV before every transfer and every read from the TV. Choose the TV and the backup by date; it is restored onto the working copy like an import.
- **Settings:** number of TV backups to keep per TV (default 30); older ones are deleted automatically.

To restore an older state on the TV: import from the TV first, then restore the backup and use **Transfer to TV**.

## Language

The interface is available in 20 languages: Arabic, Danish, English, Finnish, French, German, Greek, Icelandic, Italian, Japanese, Korean, Norwegian (Bokmål), Polish, Portuguese (Portugal and Brazil), Russian, Spanish, Swedish, Turkish and Ukrainian. By default it follows your browser's language, otherwise English. The **language selection in the header** overrides it, takes effect immediately without reloading and is remembered in this browser; **Browser language** returns to the browser setting.

## Good to know

- **Transfers are not atomic:** if an error occurs, earlier steps may already have been executed on the TV. There is no automatic rollback. Read the state from the TV again and plan anew.
- **Do not restore a TV backup by copying files onto the TV.** Use **Restore backup** or **Import** and transfer the changes.
- **Only the tested combination is confirmed:** an LG OLED55C27LA (webOS 22) with Astra 19.2° E. Other models, firmware versions, satellites or cable/antenna/IP transfers may behave differently.
- The **number limit 1–99** follows the TV's own editor on the tested TV; it applies to all new numbers.
- The editor has **no login of its own**. Run it only on your computer or in a trusted home network, never on the internet ([security](TECHNICAL.md#security)).
- Keep the `data/` folder when updating – it holds your working copy and backups ([details](TECHNICAL.md#local-data-and-backups)).

## License

[MIT](LICENSE) © 2026 robNice. Use at your own risk: changes to the TV's channel list are made via undocumented LG interfaces and cannot be rolled back automatically.
