import subprocess
import json
import threading
from datetime import datetime
import signal
import sys
from queue import Queue, Empty
import sqlite3
import time


DB_FILE = "logs.db"
QUEUE_MAX_SIZE = 5000      
RESTART_DELAY = 5          
BATCH_SIZE = 50             
QUEUE_RETRY = 3             


log_queue = Queue(maxsize=QUEUE_MAX_SIZE)
shutdown_flag = threading.Event()
process = None
batch = []


conn = sqlite3.connect(DB_FILE, check_same_thread=False)
cursor = conn.cursor()
cursor.execute("""
CREATE TABLE IF NOT EXISTS journal_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT,
    unit TEXT,
    pid INTEGER,
    priority INTEGER,
    message TEXT
)
""")
conn.commit()


def shutdown(*_):
    print("\nExiting... killing journalctl")
    shutdown_flag.set()
    if process and process.poll() is None:
        process.kill()
    flush_batch()  
    conn.close()
    sys.exit(0)

signal.signal(signal.SIGINT, shutdown)
signal.signal(signal.SIGTERM, shutdown)

def read_stderr(pipe, stop_event):
    """
    Reads stderr lines until stop_event is set or pipe closes.
    """
    for line in iter(pipe.readline, ''):
        if stop_event.is_set():
            break
        with open("script_error.log", "a") as f:
            f.write(f"{datetime.now().isoformat()} ERR: {line}")


def flush_batch():
    global batch
    if not batch:
        return
    try:
        cursor.executemany("""
            INSERT INTO journal_logs (timestamp, unit, pid, priority, message)
            VALUES (?, ?, ?, ?, ?)
        """, batch)
        conn.commit()
    except Exception as e:
        with open("script_error.log", "a") as f:
            f.write(f"{datetime.now().isoformat()} DB ERROR: {e}\n")
    finally:
        batch.clear()

def process_logs():
    global batch
    while not shutdown_flag.is_set():
        try:
            entry = log_queue.get(timeout=1)
        except Empty:
            if batch:
                flush_batch()
            continue

        ts = entry.get("__REALTIME_TIMESTAMP")
        if ts:
            ts = datetime.fromtimestamp(int(ts) / 1_000_000).isoformat()

        row = (
            ts,
            entry.get("_SYSTEMD_UNIT"),
            entry.get("_PID"),
            entry.get("PRIORITY"),
            entry.get("MESSAGE")
        )
        batch.append(row)

        if len(batch) >= BATCH_SIZE:
            flush_batch()

threading.Thread(target=process_logs, daemon=True).start()


def safe_queue_put(entry):
    for _ in range(QUEUE_RETRY):
        try:
            log_queue.put(entry, timeout=0.5)
            return True
        except:
            time.sleep(0.1)
    with open("script_error.log", "a") as f:
        f.write(f"{datetime.now().isoformat()} QUEUE FULL: Dropped log\n")
    return False

stderr_stop_event = threading.Event()
while not shutdown_flag.is_set():
    try:
        process = subprocess.Popen(
            ["journalctl", "-f", "-o", "json"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1
        )

        if process.poll() is not None:
            raise RuntimeError("journalctl feeder failed to start")

        stderr_stop_event.clear()
        stderr_thread = threading.Thread(target=read_stderr, args=(process.stderr, stderr_stop_event), daemon=True)
        stderr_thread.start()

        for line in process.stdout:
            if shutdown_flag.is_set():
                break
            if not line.strip() or line.startswith("--"):
                continue
            try:
                parsed_entry = json.loads(line)
                safe_queue_put(parsed_entry)
            except json.JSONDecodeError:
                continue

    except Exception as e:
        with open("script_error.log", "a") as f:
            f.write(f"{datetime.now().isoformat()} ERROR: {e}\n")
    
    finally:
        stderr_stop_event.set()
        if stderr_thread.is_alive():
            stderr_thread.join(timeout=1)
        if process and process.poll() is None:
            process.kill()

    if not shutdown_flag.is_set():
        with open("script_error.log", "a") as f:
            f.write(f"{datetime.now().isoformat()} journalctl stopped, restarting in {RESTART_DELAY}s...\n")
        time.sleep(RESTART_DELAY)
