# Sift Windows release

## Download

Attach the rebuilt `Sift.exe` to this GitHub Release. It is a self-contained 64-bit Windows build with the OCR engine, English and Spanish OCR data, and offline equation-recognition models bundled. This build was produced from the updated source with Python 3.12.14 and PyInstaller 6.22.3.

## Included

- Drag-to-select screen OCR, with automatic clipboard copy and editable result review.
- English, Spanish, and combined English + Spanish text recognition.
- Code and bracket recognition for `()`, `[]`, and `{}`.
- Offline printed-equation recognition, with Unicode text and LaTeX copy options.
- Configurable global shortcut, system-tray controls, and persistent preferences.
- Local processing without an added capture history, telemetry, or upload service.
- Gentler contrast clipping in math mode to try to retain faint strokes.

## Known limitations

OCR can misread small text, ambiguous characters, and complex layouts. Handwriting and rotated text are not specifically supported. Equation recognition is intended for one clear printed equation at a time; cursive or handwritten math symbols, especially Greek letters and similar-looking symbols, can still be misread. Gentler contrast clipping is a preprocessing attempt, not a handwriting model, and this build has not been functionally checked against cursive examples. The app does not check mathematical correctness. Mixed-DPI and negative-origin monitor behavior has not been fully validated.
