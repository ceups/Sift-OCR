"""Offline formula OCR in a bounded, isolated worker process."""
from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unicodedata

from PIL import Image
from sift_ocr import OCRResult, normalized_gray


def readable_math(latex):
    from pylatexenc.latex2text import LatexNodes2Text

    class FormulaText(LatexNodes2Text):
        def macro_node_to_text(self, node):
            args = node.nodeargd.argnlist if node.nodeargd else []
            if node.macroname in ("frac", "dfrac", "tfrac") and len(args) == 2:
                numerator, denominator = [self._groupnodecontents_to_text(arg) for arg in args]
                return f"({numerator})/({denominator})"
            if node.macroname == "sqrt" and len(args) == 2:
                index, radicand = [self._groupnodecontents_to_text(arg) for arg in args]
                return f"√[{index}]({radicand})" if index else f"√({radicand})"
            return super().macro_node_to_text(node)

    text = FormulaText(keep_braced_groups=True, keep_braced_groups_minlen=2).latex_to_text(latex).strip()
    # Remove font styling only. NFKC over the entire output would erase powers.
    return "".join(unicodedata.normalize("NFKC", c) if 0x1D400 <= ord(c) <= 0x1D7FF else c for c in text)


def recognize_math(image, model_dir):
    # Keep more faint stroke pixels than the general text pipeline. Cursive
    # operators and letter tails can occupy less than half a percent of pixels.
    gray = normalized_gray(image, cutoff=0.05)
    low, high = gray.getextrema()
    if high-low < 8:
        return OCRResult("", 0, 0)
    with tempfile.TemporaryDirectory(prefix="sift-math-") as directory:
        source, target = Path(directory)/"formula.png", Path(directory)/"result.json"
        gray.save(source)
        if getattr(sys, "frozen", False):
            command = [sys.executable, "--math-worker"]
        else:
            command = [sys.executable, str(Path(__file__).resolve()), "--math-worker"]
        process = subprocess.run(command + [str(source), str(target), str(model_dir)],
                                 capture_output=True, timeout=45,
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if process.returncode or not target.exists():
            raise RuntimeError("Could not read this equation. Select one clear equation and try again.")
        result = json.loads(target.read_text(encoding="utf-8"))
        if "error" in result:
            raise RuntimeError(result["error"])
        return OCRResult(result["text"], 0, len(result["text"].split()), latex=result["latex"], review=True)


def math_worker(source, target, model_dir):
    try:
        from functools import partial
        import numpy as np
        from rapid_latex_ocr import LaTeXOCR
        import rapid_latex_ocr.main as main
        import rapid_latex_ocr.models as models
        from rapid_latex_ocr.utils_load import OrtInferSession
        directory = Path(model_dir)
        required = ["image_resizer.onnx", "encoder.onnx", "decoder.onnx", "tokenizer.json", "config.yaml"]
        if not all((directory / name).is_file() for name in required):
            raise RuntimeError("The bundled math models are missing. Restore the complete Sift build.")
        # This is an isolated worker; bound CPU use and decoding length.
        main.OrtInferSession = models.OrtInferSession = partial(OrtInferSession, num_threads=2)
        engine = LaTeXOCR(config_path=directory/"config.yaml", image_resizer_path=directory/required[0],
                          encoder_path=directory/required[1], decoder_path=directory/required[2],
                          tokenizer_json=directory/required[3])
        image = Image.open(source).convert("RGB")
        latex, _ = engine(np.array(image))
        text = readable_math(latex)
        result = {"text": text, "latex": latex}
    except Exception as exc:
        result = {"error": f"Math recognition failed: {exc}"}
    Path(target).write_text(json.dumps(result), encoding="utf-8")


if __name__ == "__main__":
    if len(sys.argv) != 5 or sys.argv[1] != "--math-worker":
        raise SystemExit("This module is Sift's internal math worker.")
    math_worker(*sys.argv[2:])
