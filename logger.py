import os
import datetime

# Global variable to hold the path of debug.log
_debug_log_path = None

def print_color(msg):
    """
    Colorizes terminal output alerts using ANSI escape codes:
    - [ERROR] or [ERROR ...] in Red
    - [INFO] in Orange/Brown (ANSI 256-color code 208)
    - [HTTP], [YTDLP], [FFMPEG], [DOWNLOAD], [WARNING] etc. in Yellow
    """
    msg_str = str(msg)
    if "[ERROR]" in msg_str or "[ERROR" in msg_str:
        print(f"\033[91m{msg_str}\033[0m")
    elif "[INFO]" in msg_str:
        print(f"\033[38;5;208m{msg_str}\033[0m")
    elif any(tag in msg_str for tag in ["[HTTP]", "[YTDLP]", "[FFMPEG]", "[DOWNLOAD]", "[WARNING]", "[AVISO]", "[REINTENTO]", "[TICKET", "[JWT", "[EMBED", "[HLS", "[DESCARGA VIDEO]"]):
        print(f"\033[33m{msg_str}\033[0m")
    else:
        print(msg_str)

def set_debug_log(curso):
    """Initializes the path of the debug log when processing a course."""
    global _debug_log_path
    if curso:
        if not os.path.exists(curso):
            os.makedirs(curso)
        _debug_log_path = os.path.join(curso, "debug.log")

def debug(msg):
    """Writes a debug message with timestamp to debug.log."""
    ts = datetime.datetime.today().replace(microsecond=0)
    line = f"[{ts}] DEBUG: {msg}\n"
    if _debug_log_path:
        try:
            with open(_debug_log_path, "a", encoding="utf-8") as f:
                f.write(line)
        except Exception:
            pass

def http_log(method, url, status_code, extra=None):
    """
    Logs an HTTP request/response to debug.log and prints non-200/201/204
    status codes in console.
    """
    msg = f"[HTTP {method}] {status_code} → {url}"
    if extra:
        msg += f"\n         ↳ {str(extra)[:300]}"
    debug(msg)
    if isinstance(status_code, int) and status_code not in (200, 201, 204):
        print_color(f"[HTTP {method}] {status_code} → {url[:90]}")
        if extra:
            print_color(f"         ↳ {str(extra)[:200]}")

def loga(curso, status, msg):
    """
    Logs events to log.txt (and also forwards them to debug.log).
    """
    ts = datetime.datetime.today().replace(microsecond=0)
    line = f"[{ts}] {status}: {msg}\n"
    try:
        if curso and not os.path.exists(curso):
            os.makedirs(curso)
        log_file = os.path.join(curso, "log.txt")
        with open(log_file, "a", encoding="utf-8") as logz:
            logz.write(line)
    except Exception:
        pass
    debug(f"[{status}] {msg}")
