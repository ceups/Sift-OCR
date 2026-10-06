# Sift

**Screen text, without the retyping.** Sift is a local Windows app that lets you select an area of the screen, recognize its text or a printed equation, and copy the result.

## Download and run

Download `Sift.exe` from the project's GitHub Releases page and open it. The Windows build is self-contained: Python, Tesseract, OCR language models, and math models are bundled. No first-run internet connection is required.

Sift starts in the system tray. Select **Capture text** or press **Ctrl+B**, drag over the screen area, and release. Sift copies the recognized result to the clipboard. Reopen the app to review and edit **Last capture**. Press **Esc** while selecting to cancel.

## Features

- **Screen-region capture:** drag to select only the text or equation you want; Sift briefly hides its own window before capturing.
- **Clipboard-first workflow:** the recognition result is copied automatically, with an editable preview and a separate **Copy text** action for corrections.
- **English and Spanish OCR:** choose English, Español, or English + Spanish. Spanish accents and punctuation are supported.
- **Code and bracket reading:** a dedicated mode targets code-like selections and `()`, `[]`, and `{}` using an additional character recognizer.
- **Printed equation recognition:** an offline model recognizes individual printed equations. Copy the readable Unicode result or use **Copy LaTeX** to preserve the recognized formula structure, including fractions and superscripts.
- **Configurable global shortcut:** record a shortcut or choose its modifiers and key in Settings. Sift keeps the previous shortcut active if a new one cannot be registered.
- **Shortcut options:** letters, numbers, function keys, Space, PrintScreen, Insert, Home, End, PageUp, and PageDown are supported. Ordinary keys require Ctrl, Alt, or Win; function keys can stand alone. Esc cancels shortcut recording. Ctrl+B is the default.
- **System-tray operation:** closing the window hides Sift to the tray, where the shortcut remains active. Reopen it from the tray icon or quit from the tray menu.
- **OCR tuned for screen text:** character-height-based enlargement, contrast normalization, dark-background inversion, crop padding, alternate preprocessing, layout comparison, and a native-resolution fallback. Math mode uses gentler contrast clipping to try to preserve faint strokes.
- **Responsive capture:** OCR runs on a worker thread. Sift shows a review notice when recognition may be uncertain.
- **Local processing:** captures are processed on the computer. Sift adds no capture-history database, telemetry, or upload service. Capture history is not persisted.
- **Standalone Windows build:** the release executable includes the OCR engine, language models, and offline math models.

## Recognition limits

OCR can misread very small text, complex layouts, or ambiguous characters. Confidence is a heuristic, not a guarantee. The supported text target is horizontal printed English or Spanish. Math mode is intended for one clear printed equation at a time; cursive or handwritten math, especially Greek letters and similar-looking symbols, can still be misread. The gentler contrast setting is a preprocessing improvement, not a handwriting model. Rotated text and handwriting are not specifically handled. Math results always include a review notice; recognition does not verify whether an equation is mathematically correct. Sample fixture results are not general accuracy estimates.

## Build from source

The repository keeps large third-party runtimes and model binaries out of Git. The GitHub Release is the simplest way to use Sift. To build locally, use 64-bit Python 3.11 on Windows 10 or later and restore the build assets described in `BUILD-ASSETS.md`. Then run:

```bat
build_windows.bat
```

The script installs Python requirements into `.venv-build`, runs the unit tests, and builds `dist\updated\Sift.exe` with PyInstaller. To launch the source app after restoring the assets:

```powershell
.venv-build\Scripts\python sift.py
```

## Privacy and settings

Screenshots stay on the computer. The selected region is temporarily written for OCR and removed after normal completion. Recognized text stays in memory and the clipboard until replaced or the app exits. Preferences are stored under `%LOCALAPPDATA%\Sift\` in `settings.json` and `ocr-settings.json`.

## Third-party components

Sift bundles Tesseract and its OCR models, plus RapidLaTeXOCR models for equation recognition. Their sources, model hashes, and license notes are documented in `OCR-RUNTIME.txt`, `math-models/README.txt`, and `dependencies.txt`. The source handoff did not include a license for Sift's own code; add the license you want before publishing the repository publicly.
