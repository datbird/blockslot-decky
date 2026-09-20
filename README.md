# Blockslot

Save sync for the games Steam Cloud does not cover. A [Decky](https://decky.xyz)
plugin for the Steam Deck and anything else that runs SteamOS or Bazzite.

Open the Quick Access menu, see which of your games Steam Cloud misses, and turn
syncing on for the one you are about to play. After that the save follows you:
play on one device, stop, and pick up on the other.

## What it needs

**A Syncthing folder you own.** Blockslot does not run a server and has no
account. Your saves move through one Syncthing folder, shared between your
devices and one machine that is always on. Each device writes only its own
subfolder. Set Syncthing up first; the Sync page of the plugin then asks for its
address, its API key and the folder id, and tests them.

**ludusavi.** It knows where each game keeps its saves and does every copy.
Decky downloads the official ludusavi v0.31.0 release when the plugin installs,
and checks its hash. The Settings page unpacks it. Blockslot carries no copy of
it, and never replaces a ludusavi that is already installed.

**One limit, today.** ludusavi v0.31.0 cannot match a Windows save path to the
same game's path inside a Proton prefix. That is written and waiting in
ludusavi's unreleased changes. Until it ships, a save moves between SteamOS
devices with the stock install. Moving one between SteamOS and Windows needs a
ludusavi build that has the feature.

## Setting it up

1. Install the plugin, then open it from the Quick Access menu and choose
   **Open Blockslot**.
2. **Settings**: install the engine, and ludusavi if it is missing.
3. **Sync**: enter your Syncthing details. Every line under "What is working"
   should turn green.
4. **Games**: turn a game on. It syncs from its next launch.

A game that is not from Steam, such as an emulator or a retro frontend, has no
app id that says which saves are its own. **Save sets** is where you name one
and point it at its save folder on this device.

## How it works

Turning a game on sets its Steam launch option, so that Steam starts
Blockslot's engine in place of the game. Before the game opens, the engine
compares your live save with the newest backup from every other device.

- The backup is newer: it restores it, without asking.
- Your live save is newer: it asks, and shows both dates.

When you quit, it backs the save up and waits until Syncthing confirms the
server has it. Nothing is ever restored over a newer save without your say.

The plugin never edits Steam's files. It asks Steam to set the launch option,
through `SteamClient.Apps.SetAppLaunchOptions`, and Steam writes it.

## What it touches

| Path | Why |
|---|---|
| `~/.config/savepick.json` | the settings. The engine reads this same file at launch, so there is one copy |
| `~/.local/bin/savepick.py` | the engine, which Steam starts. It must outlive the plugin's own directory |
| `~/.local/bin/ludusavi` | only when it was missing |
| `/tmp/savepick.log` | the engine's log, shown on the Activity page |

The plugin runs without root.

## Building

```
pnpm install
pnpm build
```

`main.py` is the backend. `py_modules/blockslot_core` holds every rule about
which save wins, and the desktop edition of Blockslot runs that same code.
`defaults/` holds the engine, the game index and the third party notices; its
contents land in the plugin's root when the plugin is built.

This repository is generated from Blockslot's main source tree, so a change
made here by hand is overwritten by the next release. Open an issue instead.

Decky's python is a frozen build with part of the standard library left out.
`xml.etree` is not there, so reading Syncthing's own config to fill the
settings in is not offered on the Deck. The backend logs what is missing once,
on load.

## Licence and credit

MIT. See [LICENSE](LICENSE).

Blockslot drives [ludusavi](https://github.com/mtkennerly/ludusavi) for every
backup and restore, and its game index is derived from
[ludusavi-manifest](https://github.com/mtkennerly/ludusavi-manifest), which is
compiled from [PCGamingWiki](https://www.pcgamingwiki.com). Files move with
[Syncthing](https://syncthing.net/). The full notices ship with the plugin as
`THIRD-PARTY-NOTICES.md`.
