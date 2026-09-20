"""Blockslot's Decky backend.

THE ONE THING THIS BACKEND DOES NOT DO IS WRITE A LAUNCH OPTION.

On a desktop, Blockslot closes Steam, edits localconfig.vdf and starts Steam
again, because Steam holds that file in memory and writes it out on exit. A
plugin cannot do that: it lives inside the Steam it would have to close.

In Game Mode it does not have to. The frontend asks Steam itself, through
SteamClient.Apps.SetAppLaunchOptions, and Steam writes the file when it feels
like it. So the split is:

    this backend      reads: what is installed, what has saves, what the hub
                      holds, whether sync is working. Builds the exact launch
                      option string for a game.
    the frontend      writes, by asking Steam.

Everything here is the same code the desktop window runs. `py_modules` carries
a copy of gui/core, so a rule about which save wins cannot drift between the
two faces of the same product.
"""

import asyncio
import os
import sys
import time
from pathlib import Path

import decky

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "py_modules"))

# HOME has to point at the deck user before the core reads a config path. The
# backend runs unprivileged here, but Decky's environment is not a login shell.
if not os.environ.get("HOME") or os.environ.get("HOME") == "/":
    os.environ["HOME"] = decky.DECKY_USER_HOME

from blockslot_core import backups, engine, logview, model    # noqa: E402
from blockslot_core import paths, settings as settings_mod    # noqa: E402
from blockslot_core import syncthing, wrap                    # noqa: E402

INDEX = HERE / "index" / "games.json"
ENGINE_SOURCE = HERE / "engine" / paths.ENGINE_NAME

# package.json names ludusavi's own release as a remote_binary, so Decky
# downloads the official archive here on install and checks its hash. The
# plugin carries no copy of ludusavi.
LUDUSAVI_ARCHIVE = HERE / "bin" / "ludusavi-linux.tar.gz"

# The Syncthing settings the Sync page edits, and the only ones it may write.
SYNC_FIELDS = ("url", "apikey", "folder", "hub_id", "hub_name", "device_dir")

# A hub scan starts ludusavi once per device. The panel and the full page both
# ask for one as they open, so an answer this fresh is handed back as it is.
HUB_FRESH = 60

# Decky ships a frozen python. Its bundle carries the standard library modules
# Decky itself needs and no others, so a module that is fine everywhere else can
# simply not be there. This says which, once, instead of leaving a feature that
# fails with no explanation.
OPTIONAL = ("urllib.request", "xml.etree.ElementTree", "subprocess", "shutil",
            "tarfile")


def _log(message):
    try:
        decky.logger.info("Blockslot: %s", message)
    except Exception:
        pass


async def _off_loop(work, *args):
    """Run blocking work on a thread, so the panel's other calls are not held."""
    return await asyncio.get_event_loop().run_in_executor(None, work, *args)


def _missing_modules():
    missing = []
    for name in OPTIONAL:
        try:
            __import__(name)
        except ImportError:
            missing.append(name)
    return missing


class Plugin:
    """Every method here is called from the panel and returns plain data.

    plugin.json says api_version 1, so the loader makes ONE instance of this
    class and hands each call its arguments by position, in the order they are
    declared here. Without that line the loader passes the class itself as
    `self`, and any method that calls another one fails.
    """

    async def _main(self):
        self.settings = settings_mod.Settings.load()
        self.library = model.Library.discover()
        self.library.settings = self.settings
        self.hub = {}
        self.hub_read = 0.0
        self._loaded = False
        missing = _missing_modules()
        if missing:
            _log("this python has no %s" % ", ".join(missing))
        _log("started, steam at %s" % (self.library.root or "not found"))

    async def _unload(self):
        # Nothing is awaited here on purpose: a coroutine awaited during
        # teardown never resumes, and the loader moves on without us.
        _log("stopped")

    async def _uninstall(self):
        # The engine, ludusavi and the settings stay. A game that was turned
        # on still names the engine in its launch option, and Steam would fail
        # to start that game if the engine went with the plugin.
        _log("uninstalled. The engine and the settings were left in place, "
             "because games that were turned on still start through them.")

    # ------------------------------------------------------------ reading

    def _load(self, force=False):
        if self._loaded and not force:
            return
        self.library.load_catalog(INDEX if INDEX.is_file() else None)
        self.library.load()
        self._loaded = True

    async def games(self, include_cloud=False, refresh=False):
        """The games worth showing, newest played first.

        Ordered by when they were last played, because on a handheld the game
        you want is nearly always the one you just put down.
        """
        try:
            self._load(force=refresh)
        except Exception as exc:
            _log("could not read the library: %s" % exc)
            return {"error": str(exc), "games": []}
        rows = self.library.visible(hide_cloud=not include_cloud)
        rows = sorted(rows, key=lambda row: (-row.last_played,
                                             (row.name or "").lower()))
        # The core decides which backup belongs to which row, for both faces.
        self.library.attach_backups(self.hub)
        out = []
        for row in rows:
            hub = row.synced
            out.append({
                "appid": row.appid,
                "name": row.name,
                "cloud": row.cloud,
                "saves": row.saves,
                "on": row.wrapped,
                "set": row.tree,
                "shortcut": row.kind == model.KIND_SHORTCUT,
                "hub": backups.when_text(hub[0]) if hub else "",
                "hub_device": self.settings.device_label(hub[1]) if hub else "",
            })
        return {"games": out, "counts": self.library.counts()}

    async def status(self):
        """One line per thing that has to be true, for the panel's header."""
        engine = paths.engine_path()
        ludusavi = paths.ludusavi_path()
        if not self.settings.sync_is_complete():
            steps = [{"label": "Sync", "ok": False,
                      "detail": "not set up on this device"}]
        else:
            steps = await self._sync_steps()
        steps.append({"label": "Engine", "ok": engine.is_file(),
                      "detail": str(engine) if engine.is_file()
                      else "not installed"})
        steps.append({"label": "ludusavi", "ok": ludusavi.is_file(),
                      "detail": str(ludusavi) if ludusavi.is_file()
                      else "missing"})
        ok = all(step["ok"] for step in steps)
        return {"ok": ok, "steps": steps,
                "device": self.settings.device_label(
                    self.settings.device_dir() or "this device")}

    async def _sync_steps(self):
        """Every Syncthing check, in the shape the panel draws."""
        found = await _off_loop(syncthing.check, self.settings.sync)
        return [{"label": label, "ok": bool(ok), "detail": detail or ""}
                for label, ok, detail in found]

    async def read_hub(self, force=False):
        """What the hub holds, per game. Slow enough to be asked for."""
        if not force and time.time() - self.hub_read < HUB_FRESH:
            return {"games": len(self.hub)}
        try:
            self.hub = await _off_loop(backups.newest_everywhere,
                                       paths.ludusavi_path())
            self.hub_read = time.time()
        except Exception as exc:
            _log("could not read the hub: %s" % exc)
            self.hub = {}
        return {"games": len(self.hub)}

    async def sets(self):
        return {"sets": [
            {"name": name, "root": root, "devices": devices}
            for name, root, devices, _every in self.settings.tree_rows()]}

    async def engine_state(self):
        """Everything the Settings page says about the engine and its tools."""
        installed = paths.engine_path()
        ludusavi = paths.ludusavi_path()
        return {
            "engine": str(installed),
            "installed": installed.is_file(),
            "current": engine.is_current(ENGINE_SOURCE),
            "have_source": ENGINE_SOURCE.is_file(),
            "ludusavi": str(ludusavi),
            "ludusavi_found": ludusavi.is_file(),
            "ludusavi_archive": LUDUSAVI_ARCHIVE.is_file(),
            "device_name": self.settings.device_label(
                self.settings.device_dir() or ""),
            "settings_file": str(self.settings.path),
            "log": str(paths.log_path()),
            "steam": str(self.library.root or ""),
        }

    async def sync_settings(self):
        """The Syncthing block, as the Sync page edits it."""
        block = self.settings.sync
        return {key: block.get(key, "") for key in SYNC_FIELDS}

    async def log_tail(self, lines=120):
        """The end of the engine's log, which is its only record of a launch."""
        path = paths.log_path()
        try:
            found = logview.tail(path, lines)
        except OSError as exc:
            return {"lines": [], "error": str(exc), "path": str(path)}
        return {"lines": [{"text": line, "kind": logview.classify(line)}
                          for line in found],
                "path": str(path)}

    # ------------------------------------------------------------ writing

    async def launch_option(self, appid, on, existing="", save_set=None):
        """The exact launch option Steam should be given for this game.

        The frontend hands back what Steam currently has, because while Steam
        is running that is the truth and the file on disk is not.

        A non-Steam shortcut needs a save set, since its app id means nothing
        to savepick. One whose name matches a set is matched to it, which is
        not a guess: it is the same name. Otherwise the sets are handed back
        and the panel asks.
        """
        try:
            self._load()
        except Exception:
            pass
        row = None
        for candidate in self.library.rows:
            if candidate.appid == int(appid):
                row = candidate
                break
        engine = paths.engine_path()
        python = paths.python_for_launch()
        if not on:
            return {"option": wrap.strip(existing), "ok": True}
        tree = row.tree if row is not None else None
        if row is not None and row.kind == model.KIND_SHORTCUT and not tree:
            tree = save_set or self._matching_set(row.name)
            if not tree:
                names = self.settings.tree_names()
                if not names:
                    return {"ok": False,
                            "error": "This is not a Steam game, so it needs a "
                                     "save set, and there are none yet."}
                return {"ok": False, "choose_set": names,
                        "error": "Which save set does %s use?" % row.name}
        option = wrap.build(python, engine, wrap.strip(existing), tree=tree)
        return {"option": option, "ok": True}

    def _matching_set(self, name):
        """A save set named after this game, or None. Matched, never guessed."""
        wanted = (name or "").strip().lower()
        for candidate in self.settings.tree_names():
            if candidate.strip().lower() == wanted:
                return candidate
        return None

    async def install_engine(self):
        """Copy the engine that ships with this plugin into ~/.local/bin."""
        if not ENGINE_SOURCE.is_file():
            return {"ok": False, "error": "this plugin has no engine to install"}
        try:
            target = engine.install(ENGINE_SOURCE)
        except OSError as exc:
            return {"ok": False, "error": str(exc)}
        _log("installed the engine to %s" % target)
        return {"ok": True, "path": str(target)}

    async def install_ludusavi(self):
        """Unpack the ludusavi that Decky downloaded. Never replaces one."""
        if not LUDUSAVI_ARCHIVE.is_file():
            return {"ok": False,
                    "error": "This install has no ludusavi download. Get it "
                             "from its own site and put it at %s."
                             % paths.ludusavi_path()}
        try:
            target = await _off_loop(engine.install_ludusavi, LUDUSAVI_ARCHIVE)
        except engine.AlreadyThere as exc:
            return {"ok": False, "error": str(exc)}
        except OSError as exc:
            return {"ok": False, "error": str(exc)}
        _log("installed ludusavi to %s" % target)
        return {"ok": True, "path": str(target)}

    def _save(self, **extra):
        """Write the settings file, and answer the way every write here does."""
        try:
            self.settings.save()
        except OSError as exc:
            _log("could not save the settings: %s" % exc)
            return {"ok": False, "error": str(exc)}
        return dict(extra, ok=True)

    async def save_sync(self, values):
        """Write the Syncthing block, then say whether it works.

        `values` is the block as sync_settings handed it out. Saved first and
        tested second on purpose: a setting that is right but untestable right
        now, because the hub is asleep, is still the setting you meant.
        """
        self.settings.set_sync(**{
            key: str((values or {}).get(key, "")).strip()
            for key in SYNC_FIELDS})
        answer = self._save()
        if answer["ok"]:
            answer["steps"] = await self._sync_steps()
        return answer

    async def set_device_name(self, name=""):
        device_dir = self.settings.device_dir()
        if not device_dir:
            return {"ok": False,
                    "error": "Set this device's folder in the share first."}
        self.settings.set_device_name(device_dir, (name or "").strip())
        return self._save()

    async def add_set(self, name="", every_file=False):
        try:
            self.settings.add_tree(name, every_file)
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        return self._save()

    async def set_root(self, name="", folder=""):
        """Point a save set at its folder ON THIS DEVICE."""
        try:
            folder = self.settings.set_tree_root(name, folder)
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        return self._save(exists=Path(folder).is_dir())

    async def remove_set(self, name=""):
        self.settings.remove_tree(name)
        return self._save()

    async def refresh(self):
        self._loaded = False
        try:
            self._load(force=True)
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
        return {"ok": True}
