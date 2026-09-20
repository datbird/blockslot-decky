"""savepick.json, the one config the engine already reads.

The GUI does not get a config of its own. Two files describing the same sync
would drift, and the one the engine reads is the one that decides behaviour, so
that is the file the GUI edits.

Every write is whole-file and atomic, and keeps a copy of what was there. The
file carries tree definitions that were built by hand over weeks; a partial
write would be expensive to notice and worse to recover.
"""

import json
import os
import shutil
from pathlib import Path

from . import paths

# The keys the engine insists on before it will trust the syncthing block.
SYNC_REQUIRED = ("url", "apikey", "folder", "device_dir")

DEFAULTS = {
    "syncthing": {
        "url": "http://127.0.0.1:8384",
        "apikey": "",
        "folder": "gamesaves",
        "hub_id": "",
        "hub_name": "",
        "device_dir": "",
        "device_names": {},
    },
    "trees": {},
}


class Settings(object):
    """savepick.json in memory, with the shape the engine expects."""

    def __init__(self, data=None, path=None):
        self.path = Path(path) if path else paths.config_path()
        self.data = data if data is not None else {}

    # ------------------------------------------------------------ loading

    @classmethod
    def load(cls, path=None):
        path = Path(path) if path else paths.config_path()
        try:
            with open(str(path), "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError):
            data = {}
        if not isinstance(data, dict):
            data = {}
        return cls(data, path)

    def save(self, path=None):
        target = Path(path) if path else self.path
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        if target.is_file():
            try:
                shutil.copy2(str(target), str(target) + ".blockslot.bak")
            except OSError:
                pass
        temp = str(target) + ".tmp"
        with open(temp, "w", encoding="utf-8") as handle:
            json.dump(self.data, handle, indent=2, sort_keys=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, str(target))

    # ------------------------------------------------------------ syncthing

    @property
    def sync(self):
        block = self.data.get("syncthing")
        return block if isinstance(block, dict) else {}

    def set_sync(self, **values):
        block = dict(self.sync)
        for key, value in values.items():
            if value is None:
                block.pop(key, None)
            else:
                block[key] = value
        self.data["syncthing"] = block

    def sync_is_complete(self):
        block = self.sync
        return all(block.get(key) for key in SYNC_REQUIRED)

    def missing_sync_keys(self):
        block = self.sync
        return [key for key in SYNC_REQUIRED if not block.get(key)]

    def device_dir(self):
        return self.sync.get("device_dir") or ""

    def device_names(self):
        names = self.sync.get("device_names")
        return dict(names) if isinstance(names, dict) else {}

    def device_label(self, dirname):
        names = self.sync.get("device_names")
        if not isinstance(names, dict):
            return dirname
        return names.get(dirname, dirname)

    def set_device_name(self, dirname, label):
        names = self.device_names()
        if label:
            names[dirname] = label
        else:
            names.pop(dirname, None)
        self.set_sync(device_names=names)

    # ------------------------------------------------------------ trees

    @property
    def trees(self):
        block = self.data.get("trees")
        return block if isinstance(block, dict) else {}

    def tree_names(self):
        return sorted(self.trees)

    def tree(self, name):
        tree = self.trees.get(name)
        return tree if isinstance(tree, dict) else {}

    def set_tree(self, name, definition):
        trees = dict(self.trees)
        trees[name] = definition
        self.data["trees"] = trees

    def remove_tree(self, name):
        trees = dict(self.trees)
        trees.pop(name, None)
        self.data["trees"] = trees

    def add_tree(self, name, every_file=False):
        """A new save set with no folders yet. ValueError says why not."""
        name = (name or "").strip()
        if not name:
            raise ValueError("A save set needs a name.")
        if name in self.trees:
            raise ValueError("There is already a save set called %s." % name)
        definition = {"roots": {}}
        if every_file:
            # One game's own folder: a console save often has no extension at
            # all, and an allow list would refuse every file in it.
            definition["extensions"] = "*"
        self.set_tree(name, definition)
        return name

    def set_tree_root(self, name, folder):
        """Point a save set at its folder ON THIS DEVICE. Returns the folder."""
        here = self.device_dir()
        if not here:
            raise ValueError("Set this device's folder in the share first.")
        folder = (folder or "").strip().rstrip("/\\")
        if not folder:
            raise ValueError("No folder given.")
        tree = dict(self.tree(name))
        roots = dict(tree.get("roots") or {})
        roots[here] = folder
        tree["roots"] = roots
        self.set_tree(name, tree)
        return folder

    def tree_rows(self):
        """(name, folder on this device, devices that know it, every file)."""
        here = self.device_dir()
        rows = []
        for name in self.tree_names():
            tree = self.tree(name)
            roots = tree.get("roots") or {}
            rows.append((name, roots.get(here, ""), len(roots),
                         tree.get("extensions") == "*"))
        return rows

    # ------------------------------------------------------------ the rest

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        if value is None:
            self.data.pop(key, None)
        else:
            self.data[key] = value

    def fill_defaults(self):
        """Add only the keys that are missing. Never change one that is set."""
        for key, value in DEFAULTS.items():
            if key not in self.data:
                self.data[key] = json.loads(json.dumps(value))
            elif isinstance(value, dict) and isinstance(self.data[key], dict):
                for inner, default in value.items():
                    self.data[key].setdefault(inner, default)
        return self
