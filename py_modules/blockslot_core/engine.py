"""The engine that ships with Blockslot, and the copy installed on this device.

Both faces install it and both say whether the installed copy is current. The
rule lives here so that one of them cannot quietly install it differently.
"""

import os
import shutil
import subprocess

from . import paths


def source(extra=None):
    """The engine that came with this copy of Blockslot, or None.

    `extra` is a path to try first, for a face that carries the engine
    somewhere `paths.resource` does not look.
    """
    if extra is not None and extra.is_file():
        return extra
    return paths.resource("engine/" + paths.ENGINE_NAME)


def is_current(shipped):
    """True when the installed engine is byte for byte the shipped one."""
    installed = paths.engine_path()
    try:
        if installed.stat().st_size != shipped.stat().st_size:
            return False
        return installed.read_bytes() == shipped.read_bytes()
    except (OSError, AttributeError):
        return False


def install(shipped):
    """Copy the shipped engine to where Steam will start it. Raises OSError."""
    target = paths.engine_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(shipped), str(target))
    # Steam starts it through python, but a person may start it by hand.
    os.chmod(str(target), 0o755)
    return target


class AlreadyThere(Exception):
    """ludusavi is already installed, and is never replaced from here."""


def install_ludusavi(archive):
    """Unpack ludusavi's own release archive to where the engine looks for it.

    `archive` is the .tar.gz that ludusavi publishes, exactly as downloaded.
    Blockslot does not carry a copy of ludusavi: each device fetches the
    official file, and this only unpacks it.

    An installed ludusavi is left alone. It may be newer than the pinned
    release, or built by hand, and replacing it would change how saves are
    read on a device that is already syncing.
    """
    target = paths.ludusavi_path()
    if target.exists():
        raise AlreadyThere("ludusavi is already installed at %s" % target)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.parent / (target.name + ".blockslot.tmp")
    try:
        _unpack_member(archive, target.name, temp)
        os.chmod(str(temp), 0o755)
        os.replace(str(temp), str(target))
    finally:
        if temp.exists():
            temp.unlink()
    return target


def _unpack_member(archive, name, destination):
    """Write one file out of a .tar.gz. Raises OSError when it is not there."""
    try:
        import tarfile
    except ImportError:
        # Decky's python is a frozen build with part of the standard library
        # left out. SteamOS always has tar.
        with open(str(destination), "wb") as out:
            done = subprocess.run(["tar", "-xzOf", str(archive), name],
                                  stdout=out, stderr=subprocess.PIPE)
        if done.returncode != 0 or not destination.stat().st_size:
            raise OSError("tar could not read %s from %s" % (name, archive))
        return
    try:
        with tarfile.open(str(archive), "r:gz") as bundle:
            member = bundle.extractfile(name)
            if member is None:
                raise OSError("%s holds no file called %s" % (archive, name))
            with open(str(destination), "wb") as out:
                shutil.copyfileobj(member, out)
    except (tarfile.TarError, KeyError) as exc:
        raise OSError("could not unpack %s: %s" % (archive, exc))
