import json
from pathlib import Path
import subprocess
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import ImageOps
from sift_ocr import prepare_image, parse_tsv
from symbol_fixtures import CASES, fixture

out = Path("build/symbol-probe")
out.mkdir(exist_ok=True)
results = []
for name, expected, size, font, dark, mode in CASES:
    image = fixture(expected, size, font, dark)
    for scale in (2, 3, 4):
        prepared = prepare_image(image)
        # Prepare existing pipeline at alternate scale for a controlled comparison.
        prepared = prepared.crop((16,16,prepared.width-16,prepared.height-16))
        prepared = prepared.resize((image.width*scale,image.height*scale))
        prepared = ImageOps.expand(prepared,border=16,fill=255)
        path = out / f"{name}-{scale}.png"
        prepared.save(path)
        for psm in (6, 7, 13):
            langs = "spa+eng" if mode == "spanish" else "eng"
            process = subprocess.run(["ocr-runtime/tesseract.exe",str(path),"stdout","-l",langs,"--psm",str(psm),
                                      "-c","load_system_dawg=0","-c","load_freq_dawg=0","tsv"],capture_output=True,text=True,encoding="utf-8",creationflags=subprocess.CREATE_NO_WINDOW)
            result = parse_tsv(process.stdout)
            results.append({"name":name,"expected":expected,"scale":scale,"psm":psm,"text":result.text,"conf":round(result.confidence,1)})
    print(json.dumps([r for r in results if r["name"]==name]),flush=True)
(out/"results.json").write_text(json.dumps(results,indent=2),encoding="utf-8")
