"""Reproducible screenshot-like fixtures; compare the handoff OCR with new OCR."""
import difflib
import json
from pathlib import Path
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image, ImageDraw, ImageFont
from sift import find_tesseract
from sift_ocr import recognize

OUT = Path(__file__).resolve().parents[1] / "validation"
OUT.mkdir(exist_ok=True)
ENGINE = find_tesseract()


def fixture(text, size, bg, fg, padding=8, font="segoeui.ttf"):
    face = ImageFont.truetype("C:/Windows/Fonts/" + font, size)
    bounds = ImageDraw.Draw(Image.new("RGB", (1, 1))).multiline_textbbox((0, 0), text, font=face, spacing=7)
    image = Image.new("RGB", (bounds[2] - bounds[0] + padding * 2, bounds[3] - bounds[1] + padding * 2), bg)
    ImageDraw.Draw(image).multiline_text((padding - bounds[0], padding - bounds[1]), text, font=face, fill=fg, spacing=7)
    return image


cases = [
    ("small-light", "The quick brown fox jumps over the lazy dog.", 11, "white", "black", 8, "segoeui.ttf"),
    ("small-dark", "Capture text from anywhere on your screen.", 11, "#181818", "#eeeeee", 8, "segoeui.ttf"),
    ("tight-crop", "Invoice 2847: Total $129.50", 14, "white", "black", 0, "arial.ttf"),
    ("paragraph", "Sift keeps your workflow simple.\nSelect a region and copy the text.\nEverything runs on your computer.", 14, "white", "black", 8, "segoeui.ttf"),
    ("dark-paragraph", "Settings and preferences\nChoose your activation shortcut.\nPress Escape to cancel.", 13, "#101010", "#eeeeee", 8, "segoeui.ttf"),
    ("low-contrast", "Your meeting starts at 10:30 AM.", 12, "#dddddd", "#999999", 8, "segoeui.ttf"),
    ("url", "https://example.com/docs?id=2048", 13, "white", "black", 8, "consola.ttf"),
    ("code", 'const total = price * 1.08;\nreturn items.length > 0;', 14, "#202020", "#eeeeee", 8, "consola.ttf"),
    ("large-type", "Make room for better ideas.", 32, "white", "black", 8, "segoeui.ttf"),
    ("numbers", "Order 2026-1042\nSubtotal: $84.99\nTax: $6.80\nTotal: $91.79", 14, "white", "black", 8, "arial.ttf"),
    ("punctuation", 'Email: hello@example.com\n"Copy this" (including punctuation).', 14, "white", "black", 8, "segoeui.ttf"),
    ("tiny-type", "Small text should still be readable.", 9, "white", "black", 8, "segoeui.ttf"),
]
results = []
for name, expected, size, bg, fg, padding, font in cases:
    image = fixture(expected, size, bg, fg, padding, font)
    path = OUT / (name + ".png")
    image.save(path)
    baseline = subprocess.run([ENGINE, str(path), "stdout", "-l", "eng", "--psm", "6"],
                              capture_output=True, text=True, encoding="utf-8", timeout=30,
                              creationflags=subprocess.CREATE_NO_WINDOW).stdout.strip()
    start = time.monotonic()
    result = recognize(image, ENGINE)
    score = lambda value: round(difflib.SequenceMatcher(None, " ".join(expected.split()), " ".join(value.split())).ratio(), 4)
    row = {"case": name, "expected": expected, "baseline": baseline, "improved": result.text,
           "baseline_similarity": score(baseline), "improved_similarity": score(result.text),
           "confidence": round(result.confidence, 1), "seconds": round(time.monotonic() - start, 2)}
    results.append(row)
    print(json.dumps(row), flush=True)
blank = recognize(Image.new("RGB", (300, 100), "white"), ENGINE)
assert blank.text == "", repr(blank.text)
(OUT / "ocr-benchmark.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
print("MEAN", sum(r["baseline_similarity"] for r in results) / len(results),
      sum(r["improved_similarity"] for r in results) / len(results))
