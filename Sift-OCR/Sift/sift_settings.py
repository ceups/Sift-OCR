"""Validated preferences and a transactional Windows global shortcut service."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass
import json
import os
from pathlib import Path
import queue
import threading

MODIFIERS = {"Ctrl": 2, "Alt": 1, "Shift": 4, "Win": 8}
KEYS = {chr(n): n for n in range(ord("A"), ord("Z") + 1)}
KEYS.update({str(n): ord(str(n)) for n in range(10)})
KEYS.update({f"F{n}": 0x6F + n for n in range(1, 25)})
KEYS.update({"Space": 0x20, "PrintScreen": 0x2C, "Insert": 0x2D,
             "Home": 0x24, "End": 0x23, "PageUp": 0x21, "PageDown": 0x22})


@dataclass(frozen=True)
class Hotkey:
    modifiers: int = 2
    key: str = "B"

    def __post_init__(self):
        if type(self.modifiers) is not int or self.modifiers < 0 or self.modifiers > 15:
            raise ValueError("Invalid shortcut modifiers.")
        if self.key not in KEYS:
            raise ValueError("Choose a letter, number, function key, or navigation key.")
        if not self.modifiers & 11 and not (self.key.startswith("F") and self.key[1:].isdigit()):
            raise ValueError("Include Ctrl, Alt, or Win so ordinary typing stays available.")

    @property
    def label(self):
        return " + ".join([name for name, flag in MODIFIERS.items() if self.modifiers & flag] + [self.key])


def settings_path():
    return Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Sift" / "settings.json"


def load_hotkey(path: Path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return Hotkey(data["modifiers"], data["key"]), None
    except FileNotFoundError:
        return Hotkey(), None
    except (OSError, ValueError, TypeError, KeyError):
        return Hotkey(), "Your saved shortcut could not be read. Using Ctrl + B for this session."


def save_hotkey(path: Path, hotkey: Hotkey):
    path.parent.mkdir(parents=True, exist_ok=True)
    # A unique sibling file keeps replacement atomic, even with two app instances.
    import tempfile
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix="settings-", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump({"version": 1, "modifiers": hotkey.modifiers, "key": hotkey.key}, stream, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


class HotkeyService:
    """Own registrations on one thread; never release a working key on failed saves."""

    def __init__(self, dispatch, on_activate):
        self.dispatch, self.on_activate = dispatch, on_activate
        self.commands = queue.Queue()
        self.thread = threading.Thread(target=self._run, daemon=True, name="Sift shortcuts")
        self.thread.start()

    def apply(self, hotkey, path, callback):
        self.commands.put((hotkey, path, callback))

    def close(self):
        self.commands.put(None)
        self.thread.join(timeout=2)

    def _run(self):
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        message = wintypes.MSG()
        current = None
        active_id = 0
        try:
            while True:
                try:
                    command = self.commands.get(timeout=0.025)
                except queue.Empty:
                    command = ()
                if command is None:
                    break
                if command:
                    hotkey, path, callback = command
                    new_id = active_id if hotkey == current else (2 if active_id == 1 else 1)
                    changed = hotkey != current
                    if changed and not user32.RegisterHotKey(None, new_id, hotkey.modifiers | 0x4000, KEYS[hotkey.key]):
                        self.dispatch(callback, False, f"{hotkey.label} is unavailable or reserved. Choose another shortcut.")
                        continue
                    try:
                        if path is not None:
                            save_hotkey(path, hotkey)
                    except OSError as exc:
                        if changed:
                            user32.UnregisterHotKey(None, new_id)
                        self.dispatch(callback, False, f"Could not save settings: {exc}")
                        continue
                    if changed and active_id:
                        user32.UnregisterHotKey(None, active_id)
                    active_id, current = new_id, hotkey
                    self.dispatch(callback, True, "")
                while user32.PeekMessageW(ctypes.byref(message), None, 0x0312, 0x0312, 1):
                    if message.wParam == active_id:
                        self.dispatch(self.on_activate)
        finally:
            if active_id:
                user32.UnregisterHotKey(None, active_id)
