"""Local OCR with conservative image preparation and confidence-based retries."""
from __future__ import annotations

import csv
from dataclasses import dataclass
from difflib import SequenceMatcher
import io
import math
from pathlib import Path
import statistics
import subprocess
import tempfile
import time

from PIL import Image, ImageOps


@dataclass
class OCRResult:
    text: str
    confidence: float
    words: int
    low_confidence_words: int = 0
    latex: str = ""
    review: bool = False


def normalized_gray(image: Image.Image, cutoff: float = 0.5) -> Image.Image:
    # Composite alpha before conversion; screenshots are normally RGB.
    rgba = image.convert("RGBA")
    white = Image.new("RGBA", rgba.size, "white")
    gray = ImageOps.grayscale(Image.alpha_composite(white, rgba))
    # Border samples estimate the background without confusing glyphs with it.
    small = gray.resize((min(128, gray.width), min(128, gray.height)))
    border = [small.getpixel((x, y)) for x in range(small.width)
              for y in (0, small.height - 1)]
    border += [small.getpixel((x, y)) for y in range(small.height)
               for x in (0, small.width - 1)]
    if statistics.median(border) < 128:
        gray = ImageOps.invert(gray)
    return ImageOps.autocontrast(gray, cutoff=cutoff)


def character_height(gray):
    import cv2
    import numpy as np
    # Work on a bounded thumbnail for unusually large multi-monitor selections.
    ratio = min(1, 2000 / max(gray.size))
    small = gray.resize((max(1, round(gray.width*ratio)), max(1, round(gray.height*ratio))))
    _, ink = cv2.threshold(np.asarray(small), 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    _, _, stats, _ = cv2.connectedComponentsWithStats(ink)
    heights = [int(h)/ratio for x,y,w,h,area in stats[1:] if h >= 4 and area >= 5 and 0.08 < w/h < 4]
    return statistics.median(heights) if heights else 16


def prepare_image(image: Image.Image, scale=None, binary=False, resample=Image.Resampling.LANCZOS) -> Image.Image:
    gray = normalized_gray(image)
    if scale is None:
        scale = max(1.5, min(5.0, 32 / character_height(gray)))
    # Bound time/memory for selections across multiple high-resolution displays.
    scale = min(scale, 6000 / max(gray.size), math.sqrt(12_000_000 / (gray.width * gray.height)))
    if scale != 1:
        gray = gray.resize((max(1, round(gray.width * scale)), max(1, round(gray.height * scale))), resample)
    if binary:
        import cv2
        import numpy as np
        _, array = cv2.threshold(np.asarray(gray), 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
        gray = Image.fromarray(array)
    return ImageOps.expand(gray, border=16, fill=255)


def parse_tsv(tsv: str) -> OCRResult:
    lines = []
    line_key = None
    words = []
    weighted = 0.0
    characters = 0
    count = low = 0
    for row in csv.DictReader(io.StringIO(tsv), delimiter="\t", quoting=csv.QUOTE_NONE):
        if row.get("level") != "5":
            continue
        text = (row.get("text") or "").strip()
        if not text:
            continue
        try:
            confidence = float(row["conf"])
        except (ValueError, KeyError):
            continue
        key = tuple(row.get(k) for k in ("page_num", "block_num", "par_num", "line_num"))
        if line_key is not None and key != line_key:
            lines.append(" ".join(words))
            words = []
        line_key = key
        words.append(text)
        count += 1
        low += confidence < 65
        weighted += max(0, confidence) * len(text)
        characters += len(text)
    if words:
        lines.append(" ".join(words))
    return OCRResult("\n".join(lines), weighted / max(1, characters), count, low)


def bracket_errors(text):
    stack = []
    errors = 0
    for character in text:
        if character in "([{":
            stack.append(character)
        elif character in ")]}":
            if stack and stack[-1] == dict(zip(")]}", "([{"))[character]:
                stack.pop()
            else:
                errors += 1
    return errors + len(stack)


def choose_result(candidates, symbols=False):
    maximum = max(len(r.text.replace(" ", "")) for r in candidates)
    def score(result):
        completeness = len(result.text.replace(" ", "")) / max(1, maximum)
        score = result.confidence - 10 * (1 - completeness)
        score -= 5 * result.low_confidence_words / max(1, result.words)
        if symbols:
            score -= min(18, bracket_errors(result.text) * 6)
        return score
    best = max(candidates, key=score)
    # Preserve punctuation supported by an actual alternate OCR pass when the
    # letters/numbers agree. Never invent closing brackets or replace x with ×.
    import unicodedata
    def letters(text):
        return "".join(c for c in text if c.isalnum())
    for candidate in sorted(candidates, key=score, reverse=True):
        if candidate.confidence < 65 or letters(candidate.text) != letters(best.text):
            continue
        a, b = "".join(best.text.split()), "".join(candidate.text.split())
        # A separate pass can recover a word boundary that scaling merged.
        # Leave spacing in code, addresses, and numbers alone.
        if (not symbols and a == b and candidate.words > best.words
                and not any(c.isdigit() or c in ":/@_=<>" for c in best.text)):
            best = candidate
            continue
        edits = SequenceMatcher(None, a, b).get_opcodes()
        additions = [b[j:k] for op, _, _, j, k in edits if op == "insert"]
        if additions and all(op in ("equal", "insert") for op, *_ in edits):
            if all(all(unicodedata.category(c).startswith("P") for c in part) for part in additions):
                if not symbols or bracket_errors(candidate.text) <= bracket_errors(best.text):
                    best = candidate
    best.review = any("".join(c.text.split()) != "".join(best.text.split())
                      for c in candidates if c.confidence >= 65)
    return best


def recognize(image: Image.Image, executable: str, language="eng", symbols=False) -> OCRResult:
    if language not in ("eng", "spa", "eng+spa"):
        raise ValueError("Choose English, Spanish, or English + Spanish.")
    prepared = prepare_image(image)
    deadline = time.monotonic() + 30
    candidates = []
    with tempfile.TemporaryDirectory(prefix="sift-") as directory:
        source = Path(directory) / "selection.png"
        prepared.save(source)

        data_dir = Path(executable).parent / "tessdata"
        # Preserve compatibility with an explicitly selected English-only engine.
        if language == "eng+spa" and not (data_dir / "spa.traineddata").is_file():
            language = "eng"

        def run(path, mode, model=None, oem=1):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(executable, 30)
            command = [executable, str(path), "stdout", "-l", model or language, "--oem", str(oem), "--psm", str(mode),
                       "--dpi", "300"]
            if (data_dir / "eng.traineddata").is_file():
                command += ["--tessdata-dir", str(data_dir)]
            if symbols or model == "symbols":
                command += ["-c", "load_system_dawg=0", "-c", "load_freq_dawg=0"]
            process = subprocess.run(
                command + ["tsv"],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=remaining,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if process.returncode:
                raise RuntimeError(process.stderr.strip() or "The OCR engine could not read the selection.")
            return parse_tsv(process.stdout)

        candidates.append(run(source, 6))
        try:
            candidates.append(run(source, 11))
            glyph_height = character_height(normalized_gray(image))
            small = glyph_height < 16
            technical = symbols or any(c in candidates[0].text for c in "[]{}()")
            if small or technical or candidates[0].confidence < 85:
                alternate = Path(directory) / "alternate.png"
                prepare_image(image, scale=3.0).save(alternate)
                candidates.append(run(alternate, 6))
                binary = Path(directory) / "binary.png"
                prepare_image(image, scale=4.0, binary=True).save(binary)
                candidates.append(run(binary, 6))
                if symbols and language == "eng" and (data_dir / "spa.traineddata").is_file():
                    candidates.append(run(source, 6, model="eng+spa"))
                if glyph_height < 10:
                    pixel = Path(directory) / "pixel.png"
                    prepare_image(image, scale=4, resample=Image.Resampling.NEAREST).save(pixel)
                    candidates.append(run(pixel, 6))
                if technical and (data_dir / "symbols.traineddata").is_file():
                    candidates.append(run(alternate, 6, model="symbols", oem=0))
            if max(result.confidence for result in candidates) < 85:
                native = Path(directory) / "native.png"
                prepare_image(image, scale=1).save(native)
                candidates.append(run(native, 6))
        except (subprocess.TimeoutExpired, RuntimeError):
            if not any(result.text for result in candidates):
                raise
    return choose_result(candidates, symbols=technical if len(candidates)>1 else symbols)
