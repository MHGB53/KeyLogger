"""
gui.py
------
KeyLogger — redesigned GUI with live key feed, animated header,
recording pulse, and a much more polished dark aesthetic.
"""

import os
import math
import time
import threading
import tkinter as tk
from tkinter import filedialog, messagebox
from datetime import datetime
from pynput import keyboard
from collections import deque

# ── Defaults ──────────────────────────────────────────────────────────────────

DEFAULT_LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
FLUSH_INTERVAL  = 5

# ── Modifier tracking ─────────────────────────────────────────────────────────

MODIFIER_LABELS = {
    keyboard.Key.ctrl_l:  "CTRL",
    keyboard.Key.ctrl_r:  "CTRL",
    keyboard.Key.alt_l:   "ALT",
    keyboard.Key.alt_r:   "ALT",
    keyboard.Key.shift:   "SHIFT",
    keyboard.Key.shift_r: "SHIFT",
    keyboard.Key.cmd:     "WIN",
}

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

# ── KeyLogger core ────────────────────────────────────────────────────────────

class KeyLogger:
    def __init__(self, log_dir: str, on_keystroke=None, on_char=None):
        self.log_dir         = log_dir
        self.on_keystroke    = on_keystroke   # callback(count)
        self.on_char         = on_char        # callback(display_token)
        self._buffer: list   = []
        self._lock           = threading.Lock()
        self._stop           = threading.Event()
        self._listener       = None
        self._log_path       = ""
        self.keystroke_count = 0
        self._held_modifiers: set = set()

    def _create_log_file(self) -> str:
        os.makedirs(self.log_dir, exist_ok=True)
        ts   = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        path = os.path.join(self.log_dir, f"keylog_{ts}.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"{'='*60}\n  KeyLogger Session Started\n")
            f.write(f"  {datetime.now().strftime('%A, %B %d %Y  %I:%M:%S %p')}\n")
            f.write(f"{'='*60}\n\n")
        return path

    def _get_base_label(self, key) -> str:
        if key in SPECIAL_KEY_MAP:
            return SPECIAL_KEY_MAP[key]
        try:
            ch = key.char
            if ch is None:
                return str(key)
            if ord(ch) < 32:
                return chr(ord(ch) + 64)
            return ch
        except AttributeError:
            return str(key)

    def _active_mods(self) -> list:
        seen, result = set(), []
        for mk in [keyboard.Key.ctrl_l, keyboard.Key.ctrl_r,
                   keyboard.Key.alt_l,  keyboard.Key.alt_r,
                   keyboard.Key.shift,  keyboard.Key.shift_r,
                   keyboard.Key.cmd]:
            if mk in self._held_modifiers:
                lbl = MODIFIER_LABELS.get(mk)
                if lbl and lbl not in seen:
                    seen.add(lbl); result.append(lbl)
        return result

    def _on_press(self, key):
        if key in MODIFIER_LABELS:
            self._held_modifiers.add(key)
            return
        base = self._get_base_label(key)
        mods = self._active_mods()
        if mods:
            combo = "+".join(mods + [base.upper() if len(base) == 1 else base])
            token = f"[{combo}]"
        else:
            if base == "\n[ENTER]\n":
                token = base
            elif len(base) > 1:
                token = f"[{base}]"
            else:
                token = base
        with self._lock:
            self._buffer.append(token)
            self.keystroke_count += 1
        if self.on_keystroke:
            self.on_keystroke(self.keystroke_count)
        if self.on_char:
            self.on_char(token)

    def _on_release(self, key):
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
            f.write(f"\n\n{'='*60}\n  Session Ended\n")
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
            on_press=self._on_press, on_release=self._on_release)
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

# ── Palette ───────────────────────────────────────────────────────────────────

BG       = "#0d0f18"
SURFACE  = "#13161f"
CARD     = "#181c28"
BORDER   = "#252a3a"
ACCENT   = "#7c3aed"      # vivid violet
ACCENT2  = "#a855f7"      # lighter purple
ACCENT3  = "#c084fc"      # lavender highlight
SUCCESS  = "#10b981"
DANGER   = "#f43f5e"
TEXT     = "#f1f5f9"
SUBTEXT  = "#64748b"
DIM      = "#334155"
ENTRY_BG = "#0f1420"

# ── Toggle Switch ─────────────────────────────────────────────────────────────

class ToggleSwitch(tk.Canvas):
    W, H, R = 68, 34, 14

    def __init__(self, parent, command=None, **kw):
        super().__init__(parent, width=self.W, height=self.H,
                         bg=CARD, highlightthickness=0, **kw)
        self._on = False
        self._command = command
        self._x = self.R + 5
        self._tx = self._x
        self._draw()
        self.bind("<Button-1>", lambda _: self._toggle())

    def _rr(self, x1, y1, x2, y2, r, **kw):
        pts = [x1+r,y1, x2-r,y1, x2,y1, x2,y1+r, x2,y2-r, x2,y2,
               x2-r,y2, x1+r,y2, x1,y2, x1,y2-r, x1,y1+r, x1,y1]
        self.create_polygon(pts, smooth=True, **kw)

    def _draw(self):
        self.delete("all")
        track = SUCCESS if self._on else BORDER
        self._rr(2, 2, self.W-2, self.H-2, self.H//2, fill=track, outline="")
        cx, cy = self._x, self.H // 2
        # glow ring when ON
        if self._on:
            self.create_oval(cx-self.R-3, cy-self.R-3,
                             cx+self.R+3, cy+self.R+3,
                             fill="#064e35", outline="")
        self.create_oval(cx-self.R, cy-self.R, cx+self.R, cy+self.R,
                         fill="white", outline="")

    def _toggle(self):
        self._on = not self._on
        self._tx = (self.W - self.R - 5) if self._on else (self.R + 5)
        self._animate()
        if self._command:
            self._command(self._on)

    def _animate(self):
        diff = self._tx - self._x
        if abs(diff) < 0.8:
            self._x = self._tx
            self._draw()
            return
        self._x += diff * 0.3
        self._draw()
        self.after(14, self._animate)

    def force_off(self):
        self._on = False
        self._tx = self.R + 5
        self._animate()

# ── Waveform bar (decorative recording indicator) ─────────────────────────────

class WaveBar(tk.Canvas):
    BARS = 12
    W, H = 100, 28

    def __init__(self, parent, **kw):
        super().__init__(parent, width=self.W, height=self.H,
                         bg=CARD, highlightthickness=0, **kw)
        self._active = False
        self._phase  = 0.0
        self._draw()

    def _draw(self):
        self.delete("all")
        bw   = self.W / (self.BARS * 1.8)
        gap  = self.W / self.BARS
        for i in range(self.BARS):
            cx = gap * i + gap / 2
            if self._active:
                h = 4 + 10 * abs(math.sin(self._phase + i * 0.55))
            else:
                h = 3
            color = ACCENT2 if self._active else DIM
            self.create_rectangle(cx - bw/2, self.H/2 - h,
                                  cx + bw/2, self.H/2 + h,
                                  fill=color, outline="", width=0)

    def start(self):
        self._active = True
        self._animate()

    def stop(self):
        self._active = False
        self._draw()

    def _animate(self):
        if not self._active:
            return
        self._phase += 0.18
        self._draw()
        self.after(50, self._animate)

# ── Main App ──────────────────────────────────────────────────────────────────

class App(tk.Tk):
    FEED_SIZE = 28   # max tokens shown in live feed

    def __init__(self):
        super().__init__()
        self.title("KeyLogger")
        self.resizable(False, False)
        self.configure(bg=BG)

        W, H = 520, 680
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{W}x{H}+{(sw-W)//2}+{(sh-H)//2}")

        self._logger: KeyLogger | None = None
        self._active  = False
        self._start_t = 0.0
        self._log_dir = tk.StringVar(value=DEFAULT_LOG_DIR)
        self._current_log = ""
        self._feed: deque = deque(maxlen=self.FEED_SIZE)

        self._build_ui()
        self._tick()

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build_ui(self):
        self._build_header()
        self._build_status_bar()
        self._build_toggle_card()
        self._build_dir_card()
        self._build_stats_card()
        self._build_feed_card()

    # Header ──────────────────────────────────────────────────────────────────
    def _build_header(self):
        hdr = tk.Frame(self, bg=BG)
        hdr.pack(fill="x", padx=26, pady=(22, 0))

        # icon + title
        left = tk.Frame(hdr, bg=BG)
        left.pack(side="left")
        tk.Label(left, text="⌨", font=("Segoe UI Emoji", 22), fg=ACCENT2,
                 bg=BG).pack(side="left", padx=(0, 8))
        tk.Label(left, text="KeyLogger", font=("Segoe UI", 20, "bold"),
                 fg=TEXT, bg=BG).pack(side="left")

        # recording dot (right side)
        self._dot_canvas = tk.Canvas(hdr, width=14, height=14, bg=BG,
                                     highlightthickness=0)
        self._dot_canvas.pack(side="right", pady=8)
        self._dot_item = self._dot_canvas.create_oval(2, 2, 12, 12, fill=DIM, outline="")

    # Status bar ──────────────────────────────────────────────────────────────
    def _build_status_bar(self):
        bar = tk.Frame(self, bg=SURFACE, height=36)
        bar.pack(fill="x", padx=26, pady=(12, 0))
        bar.pack_propagate(False)

        self._wave = WaveBar(bar)
        self._wave.pack(side="left", padx=(12, 8), pady=4)

        self._status_lbl = tk.Label(bar, text="Idle  —  ready to record",
                                    font=("Segoe UI", 10), fg=SUBTEXT, bg=SURFACE)
        self._status_lbl.pack(side="left")

        self._timer_lbl = tk.Label(bar, text="00:00", font=("Consolas", 11, "bold"),
                                   fg=DIM, bg=SURFACE)
        self._timer_lbl.pack(side="right", padx=14)

    # Toggle card ─────────────────────────────────────────────────────────────
    def _build_toggle_card(self):
        card = self._card(pady_top=14)
        left = tk.Frame(card, bg=CARD)
        left.pack(side="left", fill="x", expand=True)

        tk.Label(left, text="Capture Keystrokes",
                 font=("Segoe UI", 13, "bold"), fg=TEXT, bg=CARD).pack(anchor="w")
        tk.Label(left, text="System-wide  •  logs every key you press",
                 font=("Segoe UI", 9), fg=SUBTEXT, bg=CARD).pack(anchor="w", pady=(3, 0))

        self._toggle = ToggleSwitch(card, command=self._on_toggle)
        self._toggle.pack(side="right")

    # Directory card ──────────────────────────────────────────────────────────
    def _build_dir_card(self):
        card = self._card(pady_top=10)

        hdr = tk.Frame(card, bg=CARD)
        hdr.pack(fill="x")
        tk.Label(hdr, text="📁", font=("Segoe UI Emoji", 11), fg=ACCENT3,
                 bg=CARD).pack(side="left", padx=(0, 6))
        tk.Label(hdr, text="Log Directory", font=("Segoe UI", 11, "bold"),
                 fg=TEXT, bg=CARD).pack(side="left")

        row = tk.Frame(card, bg=CARD)
        row.pack(fill="x", pady=(10, 0))

        entry_wrap = tk.Frame(row, bg=BORDER)
        entry_wrap.pack(side="left", fill="x", expand=True, ipady=1, ipadx=1)
        self._path_entry = tk.Entry(entry_wrap, textvariable=self._log_dir,
                                    font=("Consolas", 9), fg=TEXT,
                                    bg=ENTRY_BG, insertbackground=ACCENT2,
                                    relief="flat", bd=7)
        self._path_entry.pack(fill="x")

        tk.Button(row, text="Browse", font=("Segoe UI", 10, "bold"),
                  bg=ACCENT, fg="white", activebackground=ACCENT2,
                  activeforeground="white", relief="flat", bd=0,
                  cursor="hand2", command=self._browse,
                  padx=14, pady=6).pack(side="left", padx=(8, 0))

    # Stats card ──────────────────────────────────────────────────────────────
    def _build_stats_card(self):
        card = self._card(pady_top=10)

        tk.Label(card, text="📊  Live Stats", font=("Segoe UI", 11, "bold"),
                 fg=TEXT, bg=CARD).pack(anchor="w", pady=(0, 10))

        row = tk.Frame(card, bg=CARD)
        row.pack(fill="x")

        self._stat_keys  = self._stat(row, "0",      "Keystrokes",  "⌨")
        self._stat_time  = self._stat(row, "00:00",  "Session Time","⏱")
        self._stat_file  = self._stat(row, "—",      "Log File",    "💾")

        # log path label below
        self._log_path_lbl = tk.Label(card, text="No active session",
                                      font=("Consolas", 8), fg=SUBTEXT,
                                      bg=CARD, wraplength=450, justify="left")
        self._log_path_lbl.pack(anchor="w", pady=(10, 0))

        tk.Button(card, text="📂  Open Folder",
                  font=("Segoe UI", 9), bg=CARD, fg=SUBTEXT,
                  activebackground=BORDER, activeforeground=TEXT,
                  relief="flat", bd=0, cursor="hand2",
                  command=self._open_folder).pack(anchor="w", pady=(6, 0))

    # Live feed card ──────────────────────────────────────────────────────────
    def _build_feed_card(self):
        card = self._card(pady_top=10)

        hdr = tk.Frame(card, bg=CARD)
        hdr.pack(fill="x", pady=(0, 8))
        tk.Label(hdr, text="🔴  Live Key Feed", font=("Segoe UI", 11, "bold"),
                 fg=TEXT, bg=CARD).pack(side="left")
        tk.Label(hdr, text="last 28 tokens", font=("Segoe UI", 9),
                 fg=SUBTEXT, bg=CARD).pack(side="right")

        feed_bg = tk.Frame(card, bg=ENTRY_BG)
        feed_bg.pack(fill="x", ipady=12, ipadx=10)

        self._feed_lbl = tk.Label(feed_bg, text="— waiting for input —",
                                  font=("Consolas", 10), fg=DIM,
                                  bg=ENTRY_BG, wraplength=440,
                                  justify="left", anchor="w")
        self._feed_lbl.pack(fill="x", padx=8)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _card(self, pady_top=14) -> tk.Frame:
        outer = tk.Frame(self, bg=BORDER)
        outer.pack(fill="x", padx=22, pady=(pady_top, 0), ipady=1, ipadx=1)
        inner = tk.Frame(outer, bg=CARD)
        inner.pack(fill="both", padx=1, pady=1)
        pad = tk.Frame(inner, bg=CARD)
        pad.pack(fill="both", padx=16, pady=14)
        return pad

    def _stat(self, parent, value, label, icon) -> tk.Label:
        box = tk.Frame(parent, bg=SURFACE)
        box.pack(side="left", fill="x", expand=True, padx=(0, 8))
        tk.Label(box, text=icon, font=("Segoe UI Emoji", 14),
                 fg=ACCENT3, bg=SURFACE).pack(pady=(10, 0))
        val = tk.Label(box, text=value, font=("Segoe UI", 16, "bold"),
                       fg=TEXT, bg=SURFACE)
        val.pack()
        tk.Label(box, text=label, font=("Segoe UI", 8),
                 fg=SUBTEXT, bg=SURFACE).pack(pady=(0, 10))
        return val

    # ── Events ────────────────────────────────────────────────────────────────

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
        self._feed.clear()
        self._logger = KeyLogger(log_dir=log_dir,
                                 on_keystroke=self._cb_count,
                                 on_char=self._cb_char)
        self._current_log = self._logger.start()
        self._active  = True
        self._start_t = time.time()

        self._wave.start()
        self._status_lbl.config(text="Recording  —  capturing all keystrokes", fg=SUCCESS)
        self._timer_lbl.config(fg=SUCCESS)
        self._log_path_lbl.config(text=self._current_log, fg=ACCENT3)
        self._stat_file.config(text="●", fg=SUCCESS)
        self._feed_lbl.config(text="", fg=TEXT)

    def _stop_logging(self):
        if self._logger:
            self._current_log = self._logger.stop()
            self._logger = None
        self._active = False

        self._wave.stop()
        self._status_lbl.config(text="Stopped  —  session saved", fg=SUBTEXT)
        self._timer_lbl.config(fg=DIM)
        self._log_path_lbl.config(text=self._current_log or "No active session", fg=SUBTEXT)
        self._stat_file.config(text="✓", fg=SUCCESS)
        self._dot_canvas.itemconfig(self._dot_item, fill=DIM)

    def _cb_count(self, count: int):
        self.after(0, lambda: self._stat_keys.config(text=str(count)))

    def _cb_char(self, token: str):
        self._feed.append(token)
        display = "".join(self._feed)
        # schedule on main thread
        self.after(0, lambda d=display: self._feed_lbl.config(text=d))

    def _open_folder(self):
        folder = self._log_dir.get() or DEFAULT_LOG_DIR
        if os.path.isdir(folder):
            os.startfile(folder)
        else:
            messagebox.showinfo("Info", f"Folder not found:\n{folder}")

    # ── Clock ─────────────────────────────────────────────────────────────────

    def _tick(self):
        if self._active:
            elapsed = int(time.time() - self._start_t)
            m, s = divmod(elapsed, 60)
            t = f"{m:02d}:{s:02d}"
            self._stat_time.config(text=t)
            self._timer_lbl.config(text=t)
            # pulse dot
            phase = int(elapsed * 2) % 2
            self._dot_canvas.itemconfig(
                self._dot_item, fill=SUCCESS if phase == 0 else CARD)
        self.after(500, self._tick)

    def destroy(self):
        if self._active and self._logger:
            self._logger.stop()
        super().destroy()


# ── Entry ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = App()
    app.mainloop()
