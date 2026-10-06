"""Sift: screen text, without the retyping. Windows desktop application."""
from __future__ import annotations

import ctypes
import os
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import tkinter as tk
from tkinter import messagebox, ttk

import pystray
from PIL import Image, ImageDraw, ImageGrab, ImageTk

from sift_ocr import recognize
from sift_settings import Hotkey, HotkeyService, KEYS, MODIFIERS, load_hotkey, settings_path
from sift_reading import MODES, LANGUAGES, load_reading, save_reading

BG, PANEL, LINE, TEXT, MUTED = "#101010", "#191919", "#303030", "#f5f5f5", "#a3a3a3"


def resource_path(name):
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)) / name


def find_tesseract():
    candidates = [os.environ.get("TESSERACT_CMD"), str(resource_path("ocr-runtime/tesseract.exe")),
                  shutil.which("tesseract"),
                  str(Path(os.environ.get("LOCALAPPDATA", "")) / "Sift/tesseract/tesseract.exe"),
                  r"C:\Program Files\Tesseract-OCR\tesseract.exe",
                  r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"]
    return next((str(p) for p in candidates if p and Path(p).is_file()), None)


def enable_dpi_awareness():
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except (AttributeError, OSError):
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except (AttributeError, OSError):
            pass


class Sift:
    def __init__(self, config_path=None):
        self.root = tk.Tk()
        native_scale = float(self.root.tk.call("tk", "scaling")) / (96 / 72)
        self.ui_scale = min(native_scale, (self.root.winfo_screenwidth() - 80) / 980,
                            (self.root.winfo_screenheight() - 100) / 760)
        self.root.tk.call("tk", "scaling", self.ui_scale * 96 / 72)
        self.root.title("Sift")
        self.root.configure(bg=BG)
        self.root.geometry(f"{round(980 * self.ui_scale)}x{round(760 * self.ui_scale)}")
        self.root.minsize(round(900 * self.ui_scale), round(760 * self.ui_scale))
        self.root.protocol("WM_DELETE_WINDOW", self.hide)
        self.config_path = config_path or settings_path()
        self.reading_path = self.config_path.with_name("ocr-settings.json")
        mode, language = load_reading(self.reading_path)
        self.reading_mode = tk.StringVar(value=mode)
        self.reading_language = tk.StringVar(value=language)
        self._latex_result = ""
        self.hotkey, warning = load_hotkey(self.config_path)
        self.events = queue.Queue()
        self.service = self.icon = self._overlay = self._toast_window = None
        self._busy = self._recording = self._saving = self._closing = False
        self._restore_window = self._shortcut_ready = False
        self._page = "home"
        self.status = tk.StringVar(value=warning or "Ready when you are")
        self.shortcut_text = tk.StringVar(value=self.hotkey.label)
        self.settings_message = tk.StringVar()
        self.result_hint = tk.StringVar(value="Your next capture appears here. Capture history is not saved.")
        self._build_ui()
        self._scale_layout(self.root)
        self.root.bind("<KeyPress>", self._record_key)
        self.root.after(30, self._drain_events)
        self.root.update_idletasks()
        try:
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            dark = ctypes.c_int(1)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(ctypes.c_void_p(hwnd), 20, ctypes.byref(dark), 4)
        except (AttributeError, OSError):
            pass

    def _label(self, parent, text=None, size=11, color=TEXT, bold=False, **kwargs):
        return tk.Label(parent, text=text, bg=parent.cget("bg"), fg=color,
                        font=("Segoe UI", size, "bold" if bold else "normal"), **kwargs)

    def _scale_layout(self, parent):
        """Scale pixel spacing along with Tk's point-sized fonts on high-DPI screens."""
        for widget in parent.winfo_children():
            for option in ("padx", "pady", "highlightthickness", "wraplength"):
                if option in widget.keys():
                    value = widget.winfo_pixels(widget.cget(option))
                    widget.configure(**{option: round(value * self.ui_scale)})
            if isinstance(widget, (tk.Frame, tk.Canvas)):
                for option in ("width", "height"):
                    widget.configure(**{option: round(float(widget.cget(option)) * self.ui_scale)})
            if widget.winfo_manager() == "pack":
                info = widget.pack_info()
                for option in ("padx", "pady", "ipadx", "ipady"):
                    values = info[option] if isinstance(info[option], tuple) else self.root.tk.splitlist(str(info[option]))
                    widget.pack_configure(**{option: tuple(round(float(v) * self.ui_scale) for v in values)})
            self._scale_layout(widget)

    def _button(self, parent, text, command, primary=False, **kwargs):
        bg, fg = (TEXT, BG) if primary else (PANEL, TEXT)
        return tk.Button(parent, text=text, command=command, bg=bg, fg=fg,
                         activebackground="#d9d9d9" if primary else LINE,
                         activeforeground=fg, relief="flat", bd=0, cursor="hand2",
                         font=("Segoe UI", 11, "bold"), padx=18, pady=11,
                         highlightthickness=1, highlightbackground=LINE,
                         highlightcolor="#ffffff", **kwargs)

    def _build_ui(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("TCombobox", fieldbackground=PANEL, background=LINE,
                        foreground=TEXT, arrowcolor=TEXT, bordercolor=LINE, padding=8)
        style.map("TCombobox", fieldbackground=[("readonly", PANEL)],
                  foreground=[("readonly", TEXT)], selectbackground=[("readonly", PANEL)])
        self.root.option_add("*TCombobox*Listbox.background", PANEL)
        self.root.option_add("*TCombobox*Listbox.foreground", TEXT)
        self.root.option_add("*TCombobox*Listbox.selectBackground", "#444444")
        sidebar = tk.Frame(self.root, bg="#0b0b0b", width=184)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)
        brand = tk.Frame(sidebar, bg="#0b0b0b")
        brand.pack(fill="x", padx=24, pady=(32, 45))
        self._label(brand, "sift", 30, bold=True).pack(anchor="w")
        self.nav_home = self._button(sidebar, "  Capture", lambda: self.show_page("home"), anchor="w")
        self.nav_home.pack(fill="x", padx=14, pady=4)
        self.nav_settings = self._button(sidebar, "  Settings", lambda: self.show_page("settings"), anchor="w")
        self.nav_settings.pack(fill="x", padx=14, pady=4)
        bottom = tk.Frame(sidebar, bg="#0b0b0b")
        bottom.pack(side="bottom", fill="x", padx=24, pady=26)
        self._label(bottom, "ON YOUR DEVICE", 8, bold=True).pack(anchor="w")
        self._label(bottom, "Local OCR. No uploads.", 9, MUTED).pack(anchor="w", pady=(6, 20))
        tk.Button(bottom, text="Hide to tray", command=self.hide, bg="#0b0b0b", fg=MUTED,
                  activebackground=PANEL, activeforeground=TEXT, bd=0, cursor="hand2",
                  font=("Segoe UI", 10)).pack(anchor="w", pady=(0, 10))
        tk.Button(bottom, text="Quit Sift", command=self.exit, bg="#0b0b0b", fg=MUTED,
                  activebackground=PANEL, activeforeground=TEXT, bd=0, cursor="hand2",
                  font=("Segoe UI", 10)).pack(anchor="w")
        shell = tk.Frame(self.root, bg=BG)
        shell.pack(side="left", fill="both", expand=True)
        footer = tk.Frame(shell, bg=BG)
        footer.pack(side="bottom", fill="x", padx=32, pady=(10, 20))
        tk.Frame(footer, bg=LINE, height=1).pack(fill="x", pady=(0, 14))
        self._label(footer, textvariable=self.status, size=9, color=MUTED, anchor="w",
                    wraplength=640, justify="left").pack(side="left", fill="x", expand=True)
        self._label(footer, "SIFT / 01", 8, MUTED).pack(side="right", padx=(12, 0))
        self.content = tk.Frame(shell, bg=BG)
        self.content.pack(fill="both", expand=True, padx=34, pady=(30, 0))
        self.home, self.settings = tk.Frame(self.content, bg=BG), tk.Frame(self.content, bg=BG)
        self._build_home()
        self._build_settings()
        self.show_page("home")

    def _build_home(self):
        self._label(self.home, "SCREEN TO CLIPBOARD", 9, MUTED, bold=True).pack(anchor="w")
        self._label(self.home, "Take text. Anywhere.", 31, bold=True).pack(anchor="w", pady=(12, 6))
        self._label(self.home, "A screenshot becomes something you can copy, edit, and use.", 11, MUTED).pack(anchor="w")
        demo = tk.Canvas(self.home, bg=PANEL, height=130, highlightthickness=1, highlightbackground=LINE)
        demo.pack(fill="x", pady=(25, 21))
        def draw_demo(event):
            demo.delete("all")
            w = event.width / self.ui_scale
            demo.create_text(24, 25, anchor="w", text="A LITTLE LESS FRICTION", fill=MUTED, font=("Segoe UI", 8))
            demo.create_text(34, 68, anchor="w", text="If you can see it, you can sift it.",
                             fill=TEXT, font=("Segoe UI", 19))
            for x, dx in ((23, 13), (min(w - 24, 557), -13)):
                for y, dy in ((43, 12), (94, -12)):
                    demo.create_line(x + dx, y, x, y, x, y + dy, fill=TEXT, width=2)
            demo.create_text(w - 24, 113, anchor="e", text="SELECT  →  RECOGNIZE  →  COPY",
                             fill=MUTED, font=("Segoe UI", 8))
            demo.scale("all", 0, 0, self.ui_scale, self.ui_scale)
        demo.bind("<Configure>", draw_demo)
        reading = tk.Frame(self.home, bg=BG)
        reading.pack(fill="x", pady=(0, 14))
        self._label(reading, "READ AS", 8, MUTED).pack(side="left", padx=(0, 10))
        self.mode_combo = ttk.Combobox(reading, textvariable=self.reading_mode, values=list(MODES),
                                       state="readonly", width=19, font=("Segoe UI", 10))
        self.mode_combo.pack(side="left", padx=(0, 12))
        self.language_combo = ttk.Combobox(reading, textvariable=self.reading_language, values=list(LANGUAGES),
                                           state="readonly", width=19, font=("Segoe UI", 10))
        self.language_combo.pack(side="left")
        for combo in (self.mode_combo, self.language_combo):
            combo.bind("<<ComboboxSelected>>", self._reading_changed)
        if MODES[self.reading_mode.get()] == "math":
            self.language_combo.configure(state="disabled")
        actions = tk.Frame(self.home, bg=BG)
        actions.pack(fill="x")
        self.capture_button = self._button(actions, "Capture text  ↗", self.capture, primary=True)
        self.capture_button.pack(side="left")
        shortcut = tk.Frame(actions, bg=BG)
        shortcut.pack(side="left", padx=20)
        self._label(shortcut, "OR USE YOUR SHORTCUT", 8, MUTED).pack(anchor="w")
        self._label(shortcut, size=12, bold=True, textvariable=self.shortcut_text).pack(anchor="w", pady=(2, 0))
        self._label(self.home, "Drag around text. Release to copy. Esc to cancel.", 10, MUTED).pack(anchor="w", pady=(12, 24))
        header = tk.Frame(self.home, bg=BG)
        header.pack(fill="x")
        self._label(header, "LAST CAPTURE", 9, bold=True).pack(side="left")
        self.copy_button = tk.Button(header, text="Copy text", command=self.copy_result, state="disabled",
                                     font=("Segoe UI", 10), bg=BG, fg=TEXT, disabledforeground="#606060",
                                     activebackground=PANEL, activeforeground=TEXT, relief="flat", cursor="hand2")
        self.copy_button.pack(side="right")
        self.latex_button = tk.Button(header, text="Copy LaTeX", command=self.copy_latex, state="disabled",
                                      font=("Segoe UI", 10), bg=BG, fg=TEXT, disabledforeground="#606060",
                                      activebackground=PANEL, activeforeground=TEXT, relief="flat", cursor="hand2")
        self.latex_button.pack(side="right", padx=(0, 12))
        self.result = tk.Text(self.home, height=4, bg=PANEL, fg=TEXT, insertbackground=TEXT,
                              selectbackground="#454545", selectforeground=TEXT, relief="flat",
                              highlightthickness=1, highlightbackground=LINE, highlightcolor=MUTED,
                              padx=14, pady=12, font=("Segoe UI", 11), wrap="word", undo=True)
        self.result.pack(fill="both", expand=True, pady=(8, 8))
        self._label(self.home, textvariable=self.result_hint, size=9, color=MUTED,
                    wraplength=650, justify="left").pack(anchor="w")

    def _build_settings(self):
        self._label(self.settings, "MAKE IT YOURS", 9, MUTED, bold=True).pack(anchor="w")
        self._label(self.settings, "Settings", 31, bold=True).pack(anchor="w", pady=(12, 6))
        self._label(self.settings, "Your workflow. Your shortcut.", 11, MUTED).pack(anchor="w")
        card = tk.Frame(self.settings, bg=PANEL, highlightthickness=1, highlightbackground=LINE)
        card.pack(fill="x", pady=(22, 0))
        inner = tk.Frame(card, bg=PANEL)
        inner.pack(fill="both", padx=24, pady=18)
        self._label(inner, "Activation shortcut", 15, bold=True).pack(anchor="w")
        self._label(inner, "Open the capture tool from any app.", 10, MUTED).pack(anchor="w", pady=(6, 14))
        self.draft_text = tk.StringVar(value=self.hotkey.label)
        self._label(inner, textvariable=self.draft_text, size=22, bold=True).pack(anchor="w")
        self.record_button = self._button(inner, "Record shortcut", self._start_recording)
        self.record_button.bind("<KeyPress>", self._record_key)
        self.record_button.pack(anchor="w", pady=(10, 12))
        self._label(inner, "Or choose a combination", 9, MUTED).pack(anchor="w", pady=(0, 10))
        controls = tk.Frame(inner, bg=PANEL)
        controls.pack(fill="x")
        self.modifier_vars = {}
        for name, flag in MODIFIERS.items():
            var = tk.BooleanVar(value=bool(self.hotkey.modifiers & flag))
            self.modifier_vars[name] = var
            tk.Checkbutton(controls, text=name, variable=var, command=self._draft_changed,
                           bg=PANEL, fg=TEXT, selectcolor=BG, activebackground=PANEL,
                           activeforeground=TEXT, font=("Segoe UI", 11), cursor="hand2").pack(side="left", padx=(0, 9))
        self.key_var = tk.StringVar(value=self.hotkey.key)
        self.key_combo = ttk.Combobox(controls, textvariable=self.key_var, values=list(KEYS),
                                      state="readonly", width=11, font=("Segoe UI", 11))
        self.key_combo.pack(side="left", padx=(10, 0))
        self.key_combo.bind("<<ComboboxSelected>>", lambda _: self._draft_changed())
        self._label(inner, "Use Ctrl, Alt, or Win with a key, or choose a function key.\nSome combinations are reserved by Windows or other apps.",
                    9, MUTED, justify="left").pack(anchor="w", pady=(12, 0))
        self._label(self.settings, textvariable=self.settings_message, size=10, color=TEXT,
                    wraplength=630, justify="left", anchor="w").pack(fill="x", pady=(16, 10))
        row = tk.Frame(self.settings, bg=BG)
        row.pack(fill="x")
        self.save_button = self._button(row, "Save shortcut", self.save_settings, primary=True)
        self.save_button.pack(side="left")
        self._button(row, "Reset to Ctrl + B", self.reset_shortcut).pack(side="left", padx=12)
        self._label(self.settings, "Choose text, code, or math on the Capture screen. English + Spanish are built in.\nClosing this window keeps Sift in the tray. Use Quit Sift to exit.",
                    9, MUTED, justify="left").pack(anchor="w", pady=(10, 0))

    def show_page(self, name):
        self._stop_recording()
        self._page = name
        self.home.pack_forget()
        self.settings.pack_forget()
        (self.home if name == "home" else self.settings).pack(fill="both", expand=True)
        for button, page in ((self.nav_home, "home"), (self.nav_settings, "settings")):
            button.configure(bg="#252525" if page == name else "#0b0b0b")

    def _reading_changed(self, _event=None):
        mode = MODES[self.reading_mode.get()]
        self.language_combo.configure(state="disabled" if mode == "math" else "readonly")
        self.status.set("Math: select one equation. Review the result; Copy LaTeX preserves its structure."
                        if mode == "math" else "Ready to read " + self.reading_language.get())
        try:
            save_reading(self.reading_path, self.reading_mode.get(), self.reading_language.get())
        except OSError:
            self.status.set("Reading options changed for this session, but could not be saved.")

    def show(self, page="home"):
        self.show_page(page)
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def hide(self):
        self._stop_recording()
        if self.icon is None:
            self.root.iconify()
        else:
            self.root.withdraw()

    def _draft_changed(self):
        self._stop_recording()
        self.draft_text.set(" + ".join([name for name, var in self.modifier_vars.items() if var.get()] + [self.key_var.get()]))
        self.settings_message.set("Unsaved changes")

    def _set_draft(self, hotkey):
        for name, flag in MODIFIERS.items():
            self.modifier_vars[name].set(bool(hotkey.modifiers & flag))
        self.key_var.set(hotkey.key)
        self._draft_changed()

    def reset_shortcut(self):
        self._stop_recording()
        self._set_draft(Hotkey())

    def _start_recording(self):
        if self._recording:
            self._stop_recording()
            return
        self._recording = True
        self.record_button.configure(text="Listening…  Esc to cancel")
        self.settings_message.set("Press your shortcut now, or use the controls below.")
        self.record_button.focus_set()

    def _stop_recording(self):
        self._recording = False
        if hasattr(self, "record_button"):
            self.record_button.configure(text="Record shortcut")

    def _record_key(self, event):
        if not self._recording:
            return
        if event.keysym == "Escape":
            self._stop_recording()
            self.settings_message.set("Recording canceled. Your shortcut has not changed.")
            return "break"
        key = next((name for name, code in KEYS.items() if code == event.keycode), None)
        if key is None:
            return "break"
        user32 = ctypes.windll.user32
        modifiers = sum(flag for code, flag in ((0x11, 2), (0x12, 1), (0x10, 4))
                        if user32.GetKeyState(code) & 0x8000)
        if user32.GetKeyState(0x5B) & 0x8000 or user32.GetKeyState(0x5C) & 0x8000:
            modifiers |= 8
        try:
            hotkey = Hotkey(modifiers, key)
        except ValueError as exc:
            self.settings_message.set(str(exc))
            return "break"
        self._set_draft(hotkey)
        self._stop_recording()
        self.settings_message.set("Shortcut recorded. Save to apply it.")
        return "break"

    def save_settings(self):
        self._stop_recording()
        if self._saving or not self.service:
            return
        try:
            hotkey = Hotkey(sum(MODIFIERS[name] for name, var in self.modifier_vars.items() if var.get()), self.key_var.get())
        except ValueError as exc:
            self.settings_message.set(str(exc))
            return
        self._saving = True
        self.save_button.configure(state="disabled")
        self.settings_message.set("Checking shortcut…")
        def finished(success, error):
            self._saving = False
            self.save_button.configure(state="normal")
            if success:
                self.hotkey = hotkey
                self._shortcut_ready = True
                self.shortcut_text.set(hotkey.label)
                self.settings_message.set("Saved. Your shortcut is ready to use.")
                self.status.set(f"Ready  ·  {hotkey.label}")
                if self.icon:
                    self.icon.update_menu()
            else:
                self.settings_message.set(error + (" Your previous shortcut is still active." if self._shortcut_ready else ""))
        self.service.apply(hotkey, self.config_path, finished)

    def dispatch(self, callback, *args):
        if not self._closing:
            self.events.put((callback, args))

    def _drain_events(self):
        if self._closing:
            return
        for _ in range(50):
            try:
                callback, args = self.events.get_nowait()
            except queue.Empty:
                break
            callback(*args)
            if self._closing:
                return
        self.root.after(30, self._drain_events)

    def start_services(self):
        self._start_tray()
        self.service = HotkeyService(self.dispatch, self._activate_shortcut)
        def registered(success, error):
            self._shortcut_ready = success
            if success:
                self.status.set(f"Ready  ·  {self.hotkey.label}")
            else:
                self.status.set("Shortcut unavailable. Capture still works from this window or the tray.")
                self.settings_message.set(error)
                self.show_page("settings")
        self.service.apply(self.hotkey, None, registered)

    def start(self):
        self.start_services()
        self.root.mainloop()

    def _activate_shortcut(self):
        if self._recording:
            self._set_draft(self.hotkey)
            self._stop_recording()
            self.settings_message.set("This is your current shortcut.")
        elif not self._saving:
            self.capture()

    def _start_tray(self):
        image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((3, 3, 61, 61), radius=16, fill="#111111", outline="white", width=2)
        draw.line([(44, 20), (23, 20), (20, 23), (20, 29), (42, 35), (44, 38), (44, 43), (40, 46), (20, 46)], fill="white", width=5)
        self._app_icon = ImageTk.PhotoImage(image)
        self.root.iconphoto(True, self._app_icon)
        menu = pystray.Menu(
            pystray.MenuItem("Open Sift", lambda *_: self.dispatch(self.show), default=True),
            pystray.MenuItem(lambda _: f"Capture text ({self.hotkey.label})", lambda *_: self.dispatch(self.capture)),
            pystray.MenuItem("Settings", lambda *_: self.dispatch(self.show, "settings")),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit Sift", lambda *_: self.dispatch(self.exit)),
        )
        try:
            self.icon = pystray.Icon("sift", image, "Sift — screen text to clipboard", menu)
            self.icon.run_detached()
        except Exception:
            self.icon = None
            self.status.set("Tray unavailable. Keep this window minimized to use Sift.")

    def capture(self):
        if self._overlay or self._busy or self._recording:
            return
        self._busy = True
        self._capture_options = (MODES[self.reading_mode.get()], LANGUAGES[self.reading_language.get()])
        self.capture_button.configure(state="disabled")
        self._restore_window = self.root.state() == "normal"
        self.root.withdraw()
        if self._toast_window:
            self._toast_window.destroy()
            self._toast_window = None
        self.root.after(220, self._capture_screen)

    def _capture_screen(self):
        try:
            screenshot = ImageGrab.grab(all_screens=True)
            self._show_selector(screenshot)
        except Exception as exc:
            self._finish_capture()
            messagebox.showerror("Sift", f"Could not capture the screen.\n\n{exc}", parent=self.root)

    def _finish_capture(self):
        self._busy = False
        self.capture_button.configure(state="normal")
        if self._restore_window:
            self.root.deiconify()
            self.root.lift()

    def _show_selector(self, screenshot):
        overlay = tk.Toplevel(self.root)
        self._overlay = overlay
        overlay.withdraw()
        overlay.overrideredirect(True)
        overlay.attributes("-topmost", True)
        width, height = screenshot.size
        overlay.geometry(f"{width}x{height}+0+0")
        canvas = tk.Canvas(overlay, width=width, height=height, highlightthickness=0, cursor="crosshair", bg=BG)
        canvas.pack(fill="both", expand=True)
        photo = ImageTk.PhotoImage(screenshot)
        canvas.create_image(0, 0, image=photo, anchor="nw")
        canvas.image = photo
        canvas.create_rectangle(0, 0, width, height, fill="#000000", stipple="gray50", outline="")
        canvas.create_rectangle(16, 16, 385, 58, fill=BG, outline=LINE)
        canvas.create_text(30, 37, anchor="w", text="Drag around text   ·   Esc to cancel", fill=TEXT, font=("Segoe UI", 12))
        state = {"x": None, "y": None, "rect": None}

        def point(event):
            return max(0, min(width, event.x)), max(0, min(height, event.y))

        def begin(event):
            state["x"], state["y"] = point(event)
            if state["rect"]:
                canvas.delete(state["rect"])
            state["rect"] = canvas.create_rectangle(state["x"], state["y"], state["x"], state["y"], outline="white", width=2)

        def drag(event):
            if state["rect"]:
                canvas.coords(state["rect"], state["x"], state["y"], *point(event))

        def close_overlay():
            overlay.grab_release()
            overlay.destroy()
            self._overlay = None

        def finish(event):
            if state["x"] is None:
                return
            x, y = point(event)
            box = (min(state["x"], x), min(state["y"], y), max(state["x"], x), max(state["y"], y))
            close_overlay()
            if box[2] - box[0] < 4 or box[3] - box[1] < 4:
                self._finish_capture()
                return
            self.status.set("Reading your selection…")
            self._toast("Reading your selection…", duration=30000)
            threading.Thread(target=self._recognize_worker, args=(screenshot.crop(box), *self._capture_options), daemon=True).start()

        def cancel(_event=None):
            close_overlay()
            self._finish_capture()

        canvas.bind("<ButtonPress-1>", begin)
        canvas.bind("<B1-Motion>", drag)
        canvas.bind("<ButtonRelease-1>", finish)
        overlay.bind("<Escape>", cancel)
        overlay.update_idletasks()
        overlay.deiconify()
        # Negative Tk geometry offsets are distances from the right/bottom edge.
        # Win32 positioning instead matches ImageGrab's virtual-desktop origin.
        user32 = ctypes.windll.user32
        hwnd = user32.GetParent(overlay.winfo_id())
        user32.SetWindowPos(ctypes.c_void_p(hwnd), ctypes.c_void_p(-1), user32.GetSystemMetrics(76),
                            user32.GetSystemMetrics(77), width, height, 0x0040)
        overlay.grab_set()
        overlay.focus_force()

    def _recognize_worker(self, crop, mode="text", language="eng"):
        try:
            if mode == "math":
                from sift_math import recognize_math
                result = recognize_math(crop, resource_path("math-models"))
            else:
                executable = find_tesseract() or self._install_ocr_engine()
                result = recognize(crop, executable, language=language, symbols=mode == "code")
            self.dispatch(self._ocr_complete, result, None)
        except Exception as exc:
            self.dispatch(self._ocr_complete, None, str(exc))

    def _install_ocr_engine(self):
        installer = resource_path("Tesseract-5.5.3-Setup.exe")
        if not installer.is_file():
            raise RuntimeError("Tesseract was not found. Install Tesseract with English language data, then reopen Sift.")
        self.dispatch(self._toast, "Setting up OCR for first use…", 30000)
        directory = Path(os.environ.get("LOCALAPPDATA", tempfile.gettempdir())) / "Sift/tesseract"
        # This bundle is NSIS. /D must be last and unquoted, including spaces.
        command = subprocess.list2cmdline([str(installer), "/S", "/CurrentUser"]) + f" /D={directory}"
        result = subprocess.run(command, capture_output=True, timeout=180,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        executable = find_tesseract()
        if result.returncode or not executable:
            raise RuntimeError("OCR setup did not finish. Run the included Tesseract installer, then reopen Sift.")
        return executable

    def _ocr_complete(self, result, error):
        self._finish_capture()
        if error:
            self.status.set("Could not read this selection. Try again.")
            self._toast("Could not read the selection")
            messagebox.showerror("Sift", f"Could not recognize the selected text.\n\n{error}", parent=self.root)
            return
        if not result.text:
            self.status.set("No text found. Try a closer selection with clear text.")
            self._toast("No text found — clipboard unchanged")
            return
        self.result.delete("1.0", "end")
        self.result.insert("1.0", result.text)
        self.result.edit_reset()
        self._latex_result = result.latex
        self.latex_button.configure(state="normal" if result.latex else "disabled")
        self.copy_button.configure(state="normal")
        uncertain = result.review or result.confidence < 85 or result.low_confidence_words > 0
        hint = "Some words may need a check. Edit here, then copy again." if uncertain else "Copied to clipboard. You can edit the text here and copy again."
        self.result_hint.set(hint)
        if result.latex:
            self.result_hint.set("Review this equation. Copy LaTeX keeps the original formula structure; text edits do not change LaTeX.")
        if self.copy_result() and uncertain:
            self.status.set("Text copied  ·  Review uncertain words in Last capture")
            self._toast("Text copied — some words may need a check")

    def copy_latex(self):
        if not self._latex_result:
            return
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(self._latex_result)
            self.root.update_idletasks()
        except tk.TclError:
            self.status.set("Clipboard is busy. Try Copy LaTeX again.")
            return
        self.status.set("Original formula copied as LaTeX")
        self._toast("LaTeX copied to clipboard")

    def copy_result(self):
        text = self.result.get("1.0", "end-1c").strip()
        if not text:
            return False
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            self.root.update_idletasks()
        except tk.TclError:
            self.status.set("Clipboard is busy. Use Copy text to try again.")
            return False
        self.status.set("Text copied to clipboard")
        self._toast("Text copied to clipboard")
        return True

    def _toast(self, text, duration=2200):
        if self._toast_window:
            self._toast_window.destroy()
        toast = tk.Toplevel(self.root)
        self._toast_window = toast
        toast.overrideredirect(True)
        toast.attributes("-topmost", True)
        toast.configure(bg=LINE)
        self._label(toast, text, 10, padx=18, pady=12).pack(padx=1, pady=1)
        toast.update_idletasks()
        toast.geometry(f"+{max(0, toast.winfo_screenwidth() - toast.winfo_reqwidth() - 24)}+{max(0, toast.winfo_screenheight() - toast.winfo_reqheight() - 64)}")
        def dismiss():
            if self._toast_window is toast:
                toast.destroy()
                self._toast_window = None
        self.root.after(duration, dismiss)

    def exit(self):
        if self._closing:
            return
        self._closing = True
        if self.service:
            self.service.close()
        if self.icon:
            self.icon.stop()
        self.root.destroy()


if __name__ == "__main__":
    if len(sys.argv) == 5 and sys.argv[1] == "--math-worker":
        from sift_math import math_worker
        model_dir = resource_path("math-models") if sys.argv[4] == "@bundled" else sys.argv[4]
        math_worker(sys.argv[2], sys.argv[3], model_dir)
        raise SystemExit(0)
    if os.name != "nt":
        raise SystemExit("Sift currently requires Windows.")
    enable_dpi_awareness()
    Sift().start()
