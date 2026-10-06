import json
from pathlib import Path
import subprocess
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cv2
import numpy as np
from PIL import Image, ImageOps
from sift_ocr import prepare_image, parse_tsv
from symbol_fixtures import CASES, fixture

out = Path("build/symbol-probe")
results = []
for name, expected, size, font, dark, mode in CASES[:9]:
    image = fixture(expected, size, font, dark)
    base = ImageOps.grayscale(image)
    if dark: base = ImageOps.invert(base)
    base = ImageOps.autocontrast(base)
    for scale in (3, 4):
        for method in (Image.Resampling.LANCZOS,Image.Resampling.NEAREST):
            prepared = base.resize((image.width*scale,image.height*scale),method)
            for threshold in (False, True):
                if threshold:
                    _, binary = cv2.threshold(np.array(prepared),0,255,cv2.THRESH_BINARY+cv2.THRESH_OTSU)
                    prepared = Image.fromarray(binary)
                path = out / "probe.png"
                ImageOps.expand(prepared,border=16,fill=255).save(path)
                for model, oem in (("eng",1),("symbols",0)) if mode!="spanish" else (("spa+eng",1),):
                    process = subprocess.run(["ocr-runtime/tesseract.exe",str(path),"stdout","-l",model,"--oem",str(oem),"--psm","6","-c","load_system_dawg=0","-c","load_freq_dawg=0","tsv"],capture_output=True,text=True,encoding="utf-8",creationflags=subprocess.CREATE_NO_WINDOW)
                    result=parse_tsv(process.stdout)
                    row={"name":name,"expected":expected,"scale":scale,"method":str(method),"binary":threshold,"model":model,"text":result.text,"conf":round(result.confidence,1)}
                    results.append(row)
    print(json.dumps([r for r in results if r["name"]==name]),flush=True)
(out/"legacy-results.json").write_text(json.dumps(results,indent=2),encoding="utf-8")
