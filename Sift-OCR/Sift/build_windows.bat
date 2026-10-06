@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if errorlevel 1 (
  echo Python 3.11 is required to build Sift. Install it with the py launcher.
  pause
  exit /b 1
)

if not exist .venv-build\Scripts\python.exe py -3.11 -m venv .venv-build
if errorlevel 1 goto failed

.venv-build\Scripts\python -m pip install -r requirements.txt
if errorlevel 1 goto failed

if not exist ocr-runtime\tesseract.exe (
  echo Missing ocr-runtime\tesseract.exe. See README.md.
  goto failed
)
if not exist ocr-runtime\tessdata\eng.traineddata (
  echo Missing English OCR model. See README.md.
  goto failed
)
if not exist ocr-runtime\tessdata\spa.traineddata goto failed
if not exist ocr-runtime\tessdata\symbols.traineddata goto failed
if not exist math-models\encoder.onnx goto failed
if not exist math-models\decoder.onnx goto failed
if not exist math-models\image_resizer.onnx goto failed
if not exist math-models\tokenizer.json goto failed

.venv-build\Scripts\python -m unittest discover -s tests -v
if errorlevel 1 goto failed

.venv-build\Scripts\python -m PyInstaller --noconfirm --clean --distpath "%~dp0dist\updated" --workpath "%~dp0build" Sift.spec
if errorlevel 1 goto failed

echo.
echo Build complete: dist\updated\Sift.exe
pause
exit /b 0

:failed
echo.
echo Build failed. See the error above.
pause
exit /b 1
