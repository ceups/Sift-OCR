import ctypes
import json
from pathlib import Path
import queue
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from sift_ocr import parse_tsv, prepare_image
from sift_settings import Hotkey, HotkeyService, load_hotkey, save_hotkey, KEYS


class PreferencesTests(unittest.TestCase):
    def test_shortcut_roundtrip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nested/settings.json"
            key = Hotkey(6, "S")
            save_hotkey(path, key)
            self.assertEqual(load_hotkey(path), (key, None))
            self.assertEqual(list(path.parent.glob("*.tmp")), [])

    def test_bad_preferences_recover(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            for content in ('{', '[]', 'null', '{"key": "B", "modifiers": true}',
                            '{"key": "F", "modifiers": 0}', '{"key": "Bad", "modifiers": 2}'):
                path.write_text(content)
                key, warning = load_hotkey(path)
                self.assertEqual(key, Hotkey())
                self.assertIsNotNone(warning)

    def test_disallow_plain_typing_keys(self):
        for key in ("B", "F", "Space", "1"):
            for modifiers in (0, 4):
                with self.assertRaises(ValueError):
                    Hotkey(modifiers, key)
        self.assertEqual(Hotkey(0, "F8").label, "F8")

    def test_atomic_write_preserves_old_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            save_hotkey(path, Hotkey())
            with patch("sift_settings.os.replace", side_effect=OSError("disk full")):
                with self.assertRaises(OSError):
                    save_hotkey(path, Hotkey(6, "S"))
            self.assertEqual(load_hotkey(path)[0], Hotkey())
            self.assertEqual(list(path.parent.glob("*.tmp")), [])


class OCRTests(unittest.TestCase):
    def test_white_text_becomes_dark_on_light(self):
        image = Image.new("RGB", (30, 12), "#111111")
        image.putpixel((15, 6), (255, 255, 255))
        prepared = prepare_image(image)
        self.assertEqual(prepared.getpixel((0, 0)), 255)
        self.assertGreater(prepared.getpixel((20, 20)), 220)
        self.assertLess(prepared.getextrema()[0], 100)

    def test_large_image_is_bounded(self):
        prepared = prepare_image(Image.new("RGB", (8000, 2000), "white"))
        self.assertLessEqual(prepared.width, 6032)

    def test_tsv_preserves_lines_quotes_urls_and_low_confidence(self):
        header = "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"
        result = parse_tsv(header +
            '5\t1\t1\t1\t1\t1\t0\t0\t0\t0\t96\t"Hello"\n' +
            '5\t1\t1\t1\t1\t2\t0\t0\t0\t0\t60\tworld\n' +
            '5\t1\t2\t1\t1\t1\t0\t0\t0\t0\t90\thttps://sift.test/a?b=1\n')
        self.assertEqual(result.text, '"Hello" world\nhttps://sift.test/a?b=1')
        self.assertEqual(result.low_confidence_words, 1)
        self.assertEqual(result.words, 3)

    def test_empty_tsv(self):
        self.assertEqual(parse_tsv("").text, "")


@unittest.skipUnless(hasattr(ctypes, "windll"), "Windows hotkey registration")
class WindowsHotkeyTests(unittest.TestCase):
    def setUp(self):
        self.events = queue.Queue()
        self.service = HotkeyService(lambda callback, *args: self.events.put((callback, args)), lambda: None)
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "settings.json"

    def tearDown(self):
        self.service.close()
        self.directory.cleanup()

    def apply(self, key, path=None):
        self.service.apply(key, path, lambda *args: None)
        _, args = self.events.get(timeout=3)
        return args

    def test_conflict_and_save_failure_keep_original_key(self):
        old, occupied, new = Hotkey(7, "F9"), Hotkey(7, "F10"), Hotkey(7, "F11")
        user = ctypes.windll.user32
        self.assertTrue(self.apply(old, self.path)[0])
        self.assertTrue(user.RegisterHotKey(None, 71, occupied.modifiers, KEYS[occupied.key]))
        try:
            self.assertFalse(self.apply(occupied, self.path)[0])
            self.assertEqual(load_hotkey(self.path)[0], old)
            self.assertFalse(user.RegisterHotKey(None, 72, old.modifiers, KEYS[old.key]))
            with patch("sift_settings.save_hotkey", side_effect=OSError("disk unavailable")):
                self.assertFalse(self.apply(new, self.path)[0])
            self.assertFalse(user.RegisterHotKey(None, 72, old.modifiers, KEYS[old.key]))
            self.assertTrue(user.RegisterHotKey(None, 73, new.modifiers, KEYS[new.key]))
            user.UnregisterHotKey(None, 73)
            self.assertTrue(self.apply(new, self.path)[0])
            self.assertTrue(user.RegisterHotKey(None, 72, old.modifiers, KEYS[old.key]))
            user.UnregisterHotKey(None, 72)
            self.assertEqual(load_hotkey(self.path)[0], new)
        finally:
            for ident in (71, 72, 73):
                user.UnregisterHotKey(None, ident)


if __name__ == "__main__":
    unittest.main()
