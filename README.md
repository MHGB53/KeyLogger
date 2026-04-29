# 🔑 Python KeyLogger

A lightweight, single-file Python keylogger using **pynput**.  
All logs are stored **locally** in the `/logs` folder — nothing is sent over the network.

---

## 📁 Project Structure

```
KeyLogger/
├── keylogger.py        ← Main script
├── requirements.txt    ← Python dependencies
├── logs/               ← Auto-created; contains timestamped log files
│   └── keylog_YYYY-MM-DD_HH-MM-SS.txt
└── README.md
```

---

## ⚙️ Setup

```bash
# 1. Install dependency
pip install -r requirements.txt
```

---

## ▶️ Usage

```bash
# Run with ESC key as the stop signal (default)
python gui.py

# Run without ESC stop (use Ctrl+C instead)
python gui.py --no-esc
```

---

## 📄 Log File Format

Each session creates a new timestamped file in `/logs`:

```
============================================================
  KeyLogger Session Started
  Tuesday, April 29 2026  09:00:00 PM
============================================================

Hello[SPACE]World[ENTER]
This[SPACE]is[SPACE]a[SPACE]test[ENTER]

============================================================
  Session Ended
  Tuesday, April 29 2026  09:05:00 PM
============================================================
```

### Special Key Labels

| Key          | Logged As     |
|--------------|---------------|
| Space        | ` ` (space)   |
| Enter        | `[ENTER]`     |
| Backspace    | `[BACKSPACE]` |
| Tab          | `[TAB]`       |
| Delete       | `[DELETE]`    |
| Escape       | `[ESC]`       |
| Ctrl         | `[CTRL]`      |
| Alt          | `[ALT]`       |
| Win          | `[WIN]`       |
| Arrow keys   | `[↑↓←→]`     |
| F1–F12       | `[F1]`–`[F12]`|

---

## 🛑 Stopping the Logger

| Method       | Condition                         |
|--------------|-----------------------------------|
| Press `ESC`  | Default mode                      |
| `Ctrl + C`   | In terminal / `--no-esc` mode     |

The session footer is always written before exit.

---

> ⚠️ **For educational and personal monitoring use only.**  
> Use responsibly and only on systems you own or have permission to monitor.
