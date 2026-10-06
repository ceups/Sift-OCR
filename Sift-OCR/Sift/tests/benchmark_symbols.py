"""Compare this update with the prior shipped pipeline on explicit fixtures."""
import importlib.util
import json
from pathlib import Path
import sys
import time
from difflib import SequenceMatcher
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sift_ocr import recognize
from sift_math import recognize_math
from symbol_fixtures import CASES, fixture

source = Path('validation/symbol-update/baseline_ocr.py')
spec=importlib.util.spec_from_file_location('sift_ocr_previous',source)
old=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=old
spec.loader.exec_module(old)
out=Path('validation/symbol-update')
out.mkdir(parents=True,exist_ok=True)
rows=[]
for name,expected,size,font,dark,mode in CASES:
    image=fixture(expected,size,font,dark)
    image.save(out/(name+'.png'))
    before=old.recognize(image,str(Path('ocr-runtime/tesseract.exe').resolve()))
    start=time.monotonic()
    if mode=='math':
        after=recognize_math(image,Path('math-models').resolve())
    else:
        after=recognize(image,str(Path('ocr-runtime/tesseract.exe').resolve()),language='spa' if mode=='spanish' else 'eng',symbols='bracket' in name)
    normalize=lambda s: ''.join(s.split())
    row={'case':name,'expected':expected,'before':before.text,'after':after.text,'latex':after.latex,
         'before_similarity':round(SequenceMatcher(None,normalize(expected),normalize(before.text)).ratio(),4),
         'after_similarity':round(SequenceMatcher(None,normalize(expected),normalize(after.text)).ratio(),4),
         'seconds':round(time.monotonic()-start,2)}
    rows.append(row)
    print(json.dumps(row),flush=True)
(out/'results.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
