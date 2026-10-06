# Build assets

The OCR runtime and neural-network model files are large third-party assets. They are excluded from this source repository so that the GitHub source history stays compact. A packaged Sift release already contains everything needed to run the app.

For a source build, restore these files before running `build_windows.bat`:

1. Use 64-bit Tesseract 5.5.3.20260724 on Windows and extract its installed files into `ocr-runtime/` without running an installer on the build machine. The runtime needs `tesseract.exe`, its adjacent DLLs, `doc/`, `tessdata/eng.traineddata`, `tessdata/spa.traineddata`, `tessdata/symbols.traineddata`, and `tessdata/configs/`.
2. Obtain the official `tessdata_best` English and Spanish models from the 4.1.0 tag and the legacy English model from the official `tessdata` 4.1.0 tag. The Spanish model is saved as `spa.traineddata`; the legacy English model is saved as `symbols.traineddata`.
3. Download `image_resizer.onnx`, `encoder.onnx`, `decoder.onnx`, and `tokenizer.json` from RapidAI/RapidLaTeXOCR release `v0.0.0`. Keep `config.yaml` from this repository in `math-models/`.
4. Compare downloaded model hashes with the values in `OCR-RUNTIME.txt` and `math-models/README.txt` before building.

The existing handoff ZIP contains a locally extracted copy of these assets, but this public source package intentionally does not. It also excludes the original installer, vendored Tesseract source tree, virtual environments, generated build files, and the compiled executable. Do not commit those files to the source repository; attach the Windows executable to a GitHub Release instead.
