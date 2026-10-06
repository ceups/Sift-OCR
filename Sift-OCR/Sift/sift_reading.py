"""Separate OCR preferences so shortcut updates cannot overwrite reading options."""
import json
import os
from pathlib import Path
import tempfile

MODES = {"Text": "text", "Code & brackets": "code", "Math / equations": "math"}
LANGUAGES = {"English + Spanish": "eng+spa", "English": "eng", "Español": "spa"}


def load_reading(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if data.get("mode") in MODES and data.get("language") in LANGUAGES:
            return data["mode"], data["language"]
    except (OSError, ValueError, AttributeError, TypeError):
        pass
    return "Text", "English"


def save_reading(path, mode, language):
    if mode not in MODES or language not in LANGUAGES:
        raise ValueError("Unsupported reading options")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            json.dump({"mode": mode, "language": language}, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()
