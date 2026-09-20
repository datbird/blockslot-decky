"""The savepick launch option: build it, recognise it, take it off again.

A wrapped Steam game looks like this in localconfig.vdf:

    "LaunchOptions"  "<python> <savepick.py> -- %command%"

Steam replaces %command% with everything it would have run, so savepick gets
the real command line and starts it itself. That is the whole hook, and it is
the only point in a launch that is early enough to be safe: the restore has to
finish before the game opens its save file.

KEEPING WHAT WAS ALREADY THERE

A launch option is the player's, not ours. Three cases, and all three keep it:

    ""                       ->  <wrap> -- %command%
    "-windowed"              ->  <wrap> -- %command% -windowed
    "DXVK_HUD=1 %command%"   ->  <wrap> -- DXVK_HUD=1 %command%

The third is passed through untouched because the player put %command% exactly
where they meant it. Removing the wrap gives back what was there before.
"""

import re

COMMAND_TOKEN = "%command%"
SEPARATOR = "--"


def _parts(value):
    """Split a wrapped option into (head, args, rest), or None.

    Recognising our own work cannot be done by looking for one file name. The
    engine is deployed under whatever name and path a device uses, and an
    option written by an older install names a path that has since moved. What
    every wrap does have is a head that runs a .py file, then ` -- `, then the
    thing being launched.
    """
    if not value:
        return None
    at = _separator_at(value)
    if at is None:
        return None
    head = value[:at].strip()
    rest = value[at + 4:].strip()
    tokens = _split(head)
    # One token is enough: a wrapped SHORTCUT puts the interpreter in its exe
    # field, so its launch option starts with the engine itself.
    if not tokens:
        return None
    if not any(token.lower().endswith(".py") for token in tokens):
        return None
    return head, head, rest


def _separator_at(value):
    """Where ` -- ` sits, ignoring one inside quotes."""
    quoted = False
    for index in range(len(value) - 3):
        char = value[index]
        if char == '"':
            quoted = not quoted
            continue
        if quoted:
            continue
        if value[index:index + 4] == " -- ":
            return index
    return None


def quote(path):
    """Quote a path for a launch option only when it needs it."""
    text = str(path)
    if not text or any(space in text for space in " \t"):
        return '"%s"' % text
    return text


def build(python, engine, existing="", tree=None):
    """The launch option that wraps `existing` with savepick.

    `tree` names a save set in savepick.json for whole-tree mode, which is what
    a retro frontend needs. A normal Steam game leaves it out and savepick works
    the game out from the Steam app id.
    """
    existing = (existing or "").strip()
    head = "%s %s" % (quote(python), quote(engine))
    if tree:
        head += " --tree %s" % tree
    if not existing:
        return "%s %s %s" % (head, SEPARATOR, COMMAND_TOKEN)
    if COMMAND_TOKEN in existing:
        return "%s %s %s" % (head, SEPARATOR, existing)
    return "%s %s %s %s" % (head, SEPARATOR, COMMAND_TOKEN, existing)


def build_shortcut(python, engine, exe, options="", tree=None):
    """Wrap a non-Steam shortcut. Returns the new (exe, launch options).

    A shortcut cannot use %command%: on Windows it expands to the entry's own
    exe, so the wrapper would be handed its own path and nothing would start.
    The target is named after the separator instead, which is the form already
    proven on both operating systems.
    """
    head = quote(engine)
    if tree:
        head += " --tree %s" % tree
    rest = quote(exe)
    options = (options or "").strip()
    if options:
        rest += " " + options
    return str(python), "%s %s %s" % (head, SEPARATOR, rest)


def unwrap_shortcut(exe, options):
    """Give back the (exe, launch options) a wrapped shortcut started as."""
    found = _parts(options)
    if found is None:
        return exe, options or ""
    parts = _split_first(found[2])
    if not parts[0]:
        return exe, options or ""
    return parts[0], parts[1]


def _split_first(text):
    """The first token of a command line, and everything after it."""
    text = text.strip()
    if not text:
        return "", ""
    if text.startswith('"'):
        end = text.find('"', 1)
        if end < 0:
            return text.strip('"'), ""
        return text[1:end], text[end + 1:].strip()
    parts = text.split(" ", 1)
    return parts[0], (parts[1].strip() if len(parts) > 1 else "")


def is_wrapped(value):
    """True when this launch option already runs through savepick."""
    return _parts(value) is not None


def tree_of(value):
    """The save set named in a wrapped option, or None."""
    parts = _parts(value)
    if parts is None:
        return None
    found = re.search(r"--tree\s+(\S+)", parts[1])
    return found.group(1) if found else None


def engine_of(value):
    """The engine path a wrapped option points at, or None.

    This is how the GUI notices a launch option left behind by an older
    install: it names a savepick.py that is no longer the one being deployed.
    """
    parts = _parts(value)
    if parts is None:
        return None
    tokens = [token for token in _split(parts[0])
              if token.lower().endswith(".py")]
    return tokens[-1] if tokens else None


def strip(value):
    """The launch option with the wrap removed.

    An option that was only ever the wrap comes back empty, not as a bare
    %command%, because Steam treats those two the same and an empty box reads
    as "nothing set" to the player.
    """
    parts = _parts(value)
    if parts is None:
        return value or ""
    rest = parts[2]
    if rest == COMMAND_TOKEN:
        return ""
    return rest


def _split(text):
    """Split a command head on spaces, honouring double quotes."""
    out = []
    current = []
    quoted = False
    for char in text:
        if char == '"':
            quoted = not quoted
            continue
        if char == " " and not quoted:
            if current:
                out.append("".join(current))
                current = []
            continue
        current.append(char)
    if current:
        out.append("".join(current))
    return out
