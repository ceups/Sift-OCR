import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
from functools import partial
import rapid_latex_ocr.main as main
import rapid_latex_ocr.models as models
from rapid_latex_ocr.utils_load import OrtInferSession
main.OrtInferSession = models.OrtInferSession = partial(OrtInferSession,num_threads=2)
from rapid_latex_ocr import LaTeXOCR
from pylatexenc.latex2text import LatexNodes2Text
from symbol_fixtures import CASES,fixture
root=Path('math-models')
engine=LaTeXOCR(image_resizer_path=root/'image_resizer.onnx',encoder_path=root/'encoder.onnx',decoder_path=root/'decoder.onnx',tokenizer_json=root/'tokenizer.json')
engine.encoder_decoder.max_seq_len=192
for name,text,size,font,dark,mode in CASES:
    if mode!='math':continue
    img=fixture(text,size,font,dark)
    latex,elapsed=engine(np.array(img))
    print(json.dumps({'name':name,'expected':text,'latex':latex,'text':LatexNodes2Text().latex_to_text(latex),'seconds':round(elapsed,2)}),flush=True)
