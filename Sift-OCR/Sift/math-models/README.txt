Offline math recognition models for Sift

Model source: RapidAI/RapidLaTeXOCR release v0.0.0
https://github.com/RapidAI/RapidLaTeXOCR/releases/tag/v0.0.0

Download source for each file:
https://github.com/RapidAI/RapidLaTeXOCR/releases/download/v0.0.0/image_resizer.onnx
https://github.com/RapidAI/RapidLaTeXOCR/releases/download/v0.0.0/encoder.onnx
https://github.com/RapidAI/RapidLaTeXOCR/releases/download/v0.0.0/decoder.onnx
https://github.com/RapidAI/RapidLaTeXOCR/releases/download/v0.0.0/tokenizer.json

Inference: rapid-latex-ocr 0.0.9, ONNX Runtime CPU.
The installed wheel's license is included in rapid-latex-ocr-LICENSE.txt.
Upstream project and model lineage:
https://github.com/RapidAI/RapidLaTeXOCR
https://github.com/lukas-blecher/LaTeX-OCR

config.yaml is Sift's bounded decoding configuration (192 tokens, two CPU
threads per ONNX session). Sift supplies all paths explicitly and performs
no model download at runtime. A separate subprocess has a 45-second limit.

File hashes: validation/symbol-update/model-manifest.json.
Math mode is intended for one printed equation, not a page of prose.
Review all results. Greek letters, tiny symbols, and complex layouts may
still be misread. The text preview is a linear representation; Copy LaTeX
preserves the original recognized formula structure.
