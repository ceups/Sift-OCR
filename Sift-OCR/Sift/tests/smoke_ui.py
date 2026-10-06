r"""Exercise the real Tk application and local OCR, without altering user settings.

Run from the project root with .venv-build\Scripts\python tests\smoke_ui.py.
Native shortcut registration is real; activation messages and pointer events are
injected at the app boundary rather than through physical keyboard/mouse input.
"""
import ctypes
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import tkinter as tk
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image, ImageDraw, ImageFont, ImageGrab, ImageTk
from sift import Sift, enable_dpi_awareness
from sift_ocr import OCRResult
from sift_settings import Hotkey, load_hotkey
from sift_reading import load_reading

enable_dpi_awareness()
output = Path("validation")
output.mkdir(exist_ok=True)
checks = []

with tempfile.TemporaryDirectory(prefix="sift-test-") as directory:
    app = Sift(config_path=Path(directory) / "settings.json")
    errors = []
    app.root.report_callback_exception = lambda *exc: errors.append(str(exc))

    def wait(predicate, timeout=8):
        until = time.monotonic() + timeout
        while time.monotonic() < until:
            app.root.update()
            if predicate():
                assert not errors, errors
                return
            time.sleep(0.015)
        raise AssertionError("Timed out waiting for UI")

    def screenshot(name):
        app.root.update_idletasks()
        handle = ctypes.windll.user32.GetParent(app.root.winfo_id())
        ImageGrab.grab(window=handle).save(output / name)

    try:
        app.start_services()
        wait(lambda: app._shortcut_ready or app._page == "settings")
        assert app.icon is not None
        app.show_page("home")
        screenshot("home.png")
        checks.append("Startup home window and real system tray")

        app.nav_settings.invoke()
        app._set_draft(Hotkey(7, "F8"))
        app.save_button.invoke()
        wait(lambda: not app._saving)
        assert app.hotkey == Hotkey(7, "F8"), app.settings_message.get()
        assert load_hotkey(app.config_path)[0] == app.hotkey
        screenshot("settings.png")
        checks.append("Save custom shortcut; settings file and active label agree")

        app.record_button.invoke()
        app.root.event_generate("<Escape>")
        app.root.update()
        assert not app._recording
        app.record_button.invoke()
        with patch("ctypes.windll.user32.GetKeyState", side_effect=lambda key: 0x8000 if key in (0x11, 0x10) else 0):
            app._record_key(SimpleNamespace(keysym="K", keycode=ord("K")))
        assert app.draft_text.get() == "Ctrl + Shift + K"
        assert app.hotkey == Hotkey(7, "F8")
        checks.append("Record shortcut and cancel; draft does not change active shortcut")

        # Test the complete actual screen capture -> selector -> worker -> clipboard.
        expected = "Sift capture test 2048"
        fixture = tk.Toplevel(app.root)
        fixture.geometry("640x180+180+180")
        fixture.configure(bg="white")
        fixture.attributes("-topmost", True)
        tk.Label(fixture, text=expected, font=("Arial", 24), bg="white", fg="black").pack(expand=True)
        fixture.update()
        box = (fixture.winfo_rootx(), fixture.winfo_rooty(), fixture.winfo_rootx() + fixture.winfo_width(), fixture.winfo_rooty() + fixture.winfo_height())
        app.hide()
        assert app.root.state() == "withdrawn"
        ctypes.windll.user32.PostThreadMessageW(app.service.thread.native_id, 0x0312, 1, 0)
        # Hotkey IDs alternate during replacement; post the other ID as well.
        ctypes.windll.user32.PostThreadMessageW(app.service.thread.native_id, 0x0312, 2, 0)
        wait(lambda: app._overlay is not None)
        canvas = app._overlay.winfo_children()[0]
        x_offset = ctypes.windll.user32.GetSystemMetrics(76)
        y_offset = ctypes.windll.user32.GetSystemMetrics(77)
        canvas.event_generate("<ButtonPress-1>", x=box[0] - x_offset, y=box[1] - y_offset)
        canvas.event_generate("<B1-Motion>", x=box[2] - x_offset, y=box[3] - y_offset)
        canvas.event_generate("<ButtonRelease-1>", x=box[2] - x_offset, y=box[3] - y_offset)
        ticks = [0]
        def tick():
            ticks[0] += 1
            if app._busy:
                app.root.after(10, tick)
        tick()
        wait(lambda: not app._busy, 35)
        assert app.root.clipboard_get() == expected, repr(app.result.get("1.0", "end-1c"))
        assert ticks[0] > 2
        assert app.root.state() == "withdrawn"
        fixture.destroy()
        checks.append("Real desktop image capture, region selection, background OCR, clipboard; UI remains responsive")

        app.show()
        app.result.insert("end", " edited")
        app.copy_button.invoke()
        assert app.root.clipboard_get() == expected + " edited"
        app._ocr_complete(OCRResult("", 0, 0), None)
        assert app.root.clipboard_get() == expected + " edited"
        checks.append("Edit and recopy; empty OCR preserves clipboard")
        app.capture_button.invoke()
        wait(lambda: app._overlay is not None)
        app._overlay.event_generate("<Escape>")
        wait(lambda: app._overlay is None)
        assert app.root.state() == "normal" and not app._busy
        checks.append("Cancel selection restores home window")
        # Exercise the actual asynchronous worker routing for the new modes.
        app.reading_mode.set("Math / equations")
        app._reading_changed()
        assert str(app.language_combo.cget("state")) == "disabled"
        assert load_reading(app.reading_path)[0] == "Math / equations"
        math_image = Image.new("RGB", (400, 80), "white")
        ImageDraw.Draw(math_image).text((15, 18), "12 ÷ 3 = 4", fill="black", font=ImageFont.truetype("C:/Windows/Fonts/cambria.ttc", 28))
        app._busy = True
        threading.Thread(target=app._recognize_worker, args=(math_image,"math","eng"), daemon=True).start()
        wait(lambda: not app._busy, 50)
        assert "".join(app.root.clipboard_get().split()) == "12÷3=4", app.root.clipboard_get()
        app.latex_button.invoke()
        assert "\\div" in app.root.clipboard_get()
        screenshot("math-result.png")
        checks.append("Math mode worker, persisted mode, Unicode result, and Copy LaTeX")
        app.reading_mode.set("Text")
        app.reading_language.set("Español")
        app._reading_changed()
        assert str(app.language_combo.cget("state")) == "readonly"
        spanish = Image.new("RGB", (650, 90), "white")
        ImageDraw.Draw(spanish).text((15,18), "¿Cómo estás? ¡Buenos días!", fill="black", font=ImageFont.truetype("C:/Windows/Fonts/arial.ttf",26))
        app._busy = True
        threading.Thread(target=app._recognize_worker,args=(spanish,"text","spa"),daemon=True).start()
        wait(lambda: not app._busy, 35)
        assert app.root.clipboard_get() == "¿Cómo estás? ¡Buenos días!", app.root.clipboard_get()
        assert str(app.latex_button.cget("state")) == "disabled"
        checks.append("Spanish mode preserves accents and inverted punctuation; stale LaTeX disabled")
        app.show_page("home")
        screenshot("capture-result.png")
        app.show_page("settings")
        app.root.geometry(f"{round(900 * app.ui_scale)}x{round(760 * app.ui_scale)}")
        app.settings_message.set("Ctrl + B is unavailable or reserved. Choose another shortcut. Your previous shortcut is still active.")
        app.root.update()
        assert app.save_button.winfo_viewable()
        assert app.save_button.winfo_rooty() + app.save_button.winfo_height() < app.content.winfo_rooty() + app.content.winfo_height()
        screenshot("settings-minimum.png")
        checks.append("Minimum-size settings keeps save button visible with conflict message")
    finally:
        app.exit()
    assert not app.service.thread.is_alive()
    checks.append("Quit unregisters hotkey service and stops tray")

(output / "ui-smoke.json").write_text(json.dumps(checks, indent=2), encoding="utf-8")
print("PASS", json.dumps(checks, indent=2))
