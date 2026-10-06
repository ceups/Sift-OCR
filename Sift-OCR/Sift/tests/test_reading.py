from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PIL import Image

from sift_ocr import OCRResult, bracket_errors, choose_result, character_height, normalized_gray
from sift_reading import load_reading, save_reading
from sift_math import readable_math, recognize_math


class ReadingTests(unittest.TestCase):
    def test_options_survive_restart_and_leave_shortcut_alone(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"ocr-settings.json"
            shortcut=Path(directory)/"settings.json"
            shortcut.write_text('{"modifiers":6,"key":"K"}')
            save_reading(path,"Math / equations","Español")
            self.assertEqual(load_reading(path),("Math / equations","Español"))
            self.assertEqual(shortcut.read_text(),'{"modifiers":6,"key":"K"}')
            path.write_text('[]')
            self.assertEqual(load_reading(path),("Text","English"))

    def test_bracket_pairing(self):
        self.assertEqual(bracket_errors("[(a+b)/(c-d)]"),0)
        self.assertGreater(bracket_errors("([)]"),0)

    def test_symbol_selection_does_not_invent_brackets(self):
        result=choose_result([OCRResult("items[2",96,1)],True)
        self.assertEqual(result.text,"items[2")
        result=choose_result([OCRResult("items[2",94,1),OCRResult("items[2]",90,1)],True)
        self.assertEqual(result.text,"items[2]")

    def test_punctuation_requires_ocr_evidence(self):
        result=choose_result([OCRResult("Read this",95,2),OCRResult("Read this.",75,2)])
        self.assertEqual(result.text,"Read this.")
        self.assertTrue(result.review)

    def test_math_structure_is_preserved(self):
        self.assertEqual(readable_math(r"\frac{a+b}{c+d}"),"(a+b)/(c+d)")
        self.assertEqual(readable_math(r"\sqrt[3]{8}"),"√[3](8)")
        self.assertEqual(readable_math(r"x^{a+b}"),"x^{a+b}")
        self.assertEqual(readable_math(r"\mathbf{x}\pm2\leq5"),"x±2≤5")

    def test_blank_math_does_not_spawn_a_model(self):
        with patch("sift_math.subprocess.run") as run:
            result=recognize_math(Image.new("RGB",(200,60),"white"),Path("absent"))
            self.assertEqual(result.text,"")
            run.assert_not_called()
