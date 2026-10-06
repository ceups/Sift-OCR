"""Verify the distributable's exact embedded OCR files and execute that runtime."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import subprocess

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image, ImageDraw, ImageFont
from PyInstaller.archive.readers import CArchiveReader
from sift_ocr import recognize

executable = Path(sys.argv[1] if len(sys.argv)>1 else "dist/updated/Sift.exe").resolve()
archive = CArchiveReader(str(executable))
with tempfile.TemporaryDirectory(prefix="sift-package-check-") as directory:
    for name in archive.toc:
        relative = Path(name.replace("\\", "/"))
        if relative.parts[0] not in ("ocr-runtime", "math-models"):
            continue
        assert not relative.is_absolute() and ".." not in relative.parts
        destination = Path(directory) / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        contents = archive.extract(name)
        assert contents == relative.read_bytes(), name
        destination.write_bytes(contents)
    model = Path(directory) / "ocr-runtime/tessdata/eng.traineddata"
    assert hashlib.sha256(model.read_bytes()).hexdigest() == "8280aed0782fe27257a68ea10fe7ef324ca0f8d85bd2fd145d1c2b560bcb66ba"
    image = Image.new("RGB", (600, 80), "white")
    ImageDraw.Draw(image).text((20, 20), "Sift packaged OCR works 2048", fill="black",
                               font=ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 26))
    result = recognize(image, str(Path(directory) / "ocr-runtime/tesseract.exe"))
    assert result.text == "Sift packaged OCR works 2048", result
    formula = Image.new("RGB", (400,80), "white")
    ImageDraw.Draw(formula).text((15,18),"12 ÷ 3 = 4",fill="black",font=ImageFont.truetype("C:/Windows/Fonts/cambria.ttc",28))
    source, target=Path(directory)/"formula.png",Path(directory)/"formula.json"
    formula.save(source)
    process=subprocess.run([str(executable),"--math-worker",str(source),str(target),"@bundled"],
                           timeout=60,capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW)
    assert process.returncode==0, process.stderr
    math_result=json.loads(target.read_text(encoding="utf-8"))
    assert "".join(math_result.get("text","").split())=="12÷3=4",math_result
    assert "\\div" in math_result["latex"]
report = {"sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
          "bytes": executable.stat().st_size,
          "embedded_runtime_matches_source": True,
          "embedded_english_model_verified": True,
          "embedded_ocr_result": result.text,
          "frozen_math_worker":math_result}
Path("validation/symbol-update/package-check.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
