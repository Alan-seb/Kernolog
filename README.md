# Kernolog — Batch-Manager

## 🎯 Overview

This branch of Kernolog enhances live system log monitoring by implementing a **LogZip-inspired template-extraction and batching system**, enabling you to filter noise, highlight new patterns and rapidly summarise recurring log events.This can be connected to db.py to make semantic search smarter.

Rather than simply streaming and indexing logs, this pipeline:

* Collects logs from systemd via `journalctl`
* Extracts templates by replacing dynamic parts with wildcards
* Groups templates by component (unit)
* Distinguishes *new* versus *repeated* log patterns
* Stores metadata in SQLite for efficient querying and summarisation

## 🚀 Why this matters

System logs often contain massive repetitive noise. By extracting templates and batching recurring patterns:

* You can **focus on the unusual or new log types**
* **Reduce storage/use of resources** by deduplicating at the template level
* Gain **early detection of new anomalous log flows**
* Organise logs by component/unit for easier root-cause discovery

## 📋 System Requirements

* Linux with systemd (so `journalctl` is available)
* Python 3.6+
* SQLite3 (for business-logic storage)
* No external UI or service required (pure Python + SQLite)

## 🏗 Architecture & Pipeline

```
┌─────────────────┐
│ journalctl -f   │ (streams live logs)
└──────┬──────────┘
       │
       ▼
┌─────────────────┐
│ raw_logs.py     │ (collects raw logs → logs.db: journal_logs)
└──────┬───────────┘
       │
       ▼
┌─────────────────┐
│ clean.py        │ (template extraction → logs.db: templates + log_instances)
└──────┬───────────┘
       │
       ▼
┌─────────────────┐
│ batchgrper.py   │ (group templates by component → batches.db)
└──────┬───────────┘
       │
       ▼
┌─────────────────┐
│ batchmanager.py │ (analysis: new vs repeated logs)
└────────▲────────┘
         │
┌────────┴────────┐
│ sequencer.py     │ (orchestrates loop)
└──────────────────┘
```

## 📁 Files & Purpose

### `raw_logs.py`

* Streams logs via: `journalctl -f -o json`
* Parses JSON entries (timestamp, unit, PID, priority, message)
* Batches into `logs.db` in table `journal_logs` (raw logs)
* Buffering: e.g., batching every 50 entries, queue size up to 5000, restart logic

### `clean.py`

* Incrementally reads new entries in `journal_logs`
* Extracts **templates** by replacing dynamic parts:

  * Numbers (`\b\d+\b`) → `*`
  * Paths (`/…`) → `*`
* Inserts unique templates into `templates` table (`template_id`, `template`)
* Inserts each log instance into `log_instances` with `template_id` + JSON parameters

### `batchgrper.py`

* Reads from `templates` + `log_instances`
* Groups template IDs per “component” (e.g., `unit` from systemd)
* Stores mapping in `batches.db` in `component_templates` (component → list of template IDs)

### `batchmanager.py`

* Processes logs in groups (e.g., batches of 20)
* For each log:

  * Looks up component’s known templates
  * If template is **new**: marks as new, shows full message
  * If template is **known**: marks as repeated, shows compressed summary (“x 5” etc)
* Reports grouped results with clear “new” vs “repeated” sections

### `sequencer.py`

* Orchestrator: runs the other scripts in loop with configurable sleep interval (default ~2 s)
* Ensures incremental and continuous processing
* Handles orderly shutdown (Ctrl+C)

## 📊 Database Schemas

### `logs.db`

#### `journal_logs`

```sql
id         INTEGER PRIMARY KEY AUTOINCREMENT
timestamp  TEXT
unit       TEXT     -- e.g., "sshd.service"
pid        INTEGER
priority   INTEGER
message    TEXT
```

#### `templates`

```sql
id        TEXT PRIMARY KEY   -- e.g., "T1", "T2"
template  TEXT               -- pattern with wildcards: “Started session * for user *”
```

#### `log_instances`

```sql
log_id     INTEGER PRIMARY KEY
template_id TEXT             -- foreign key → templates.id
parameters  TEXT             -- JSON array of extracted values
```

### `batches.db`

#### `component_templates`

```sql
component  TEXT PRIMARY KEY    -- systemd unit, e.g., "sshd.service"
templates  TEXT              -- newline-separated list of template IDs or template strings
```

## 🎮 Usage

### 1. Launch Raw Log Collection

```bash
python3 raw_logs.py &
```

Keeps streaming logs into `logs.db`.

### 2. Launch Pipeline (live mode)

```bash
python3 sequencer.py
```

It will run continuously: clean → group → manage, updating every cycle (default ~2 s).

### 3. Manual Step-by-Step (optional)

```bash
python3 clean.py
python3 batchgrper.py
python3 batchmanager.py
```

### 4. Run with Custom Interval

```bash
python3 sequencer.py --interval 10
```

Sets 10 s between cycles.

## 📈 Example Output

```
[CYCLE 42] 14:32:15
  ✓ Extract templates → Processed 127 log instances
  ✓ Group by component → Components processed: 18

=== GROUP 1 ===

new:
     systemd-logind.service: New session 12 opened for user alice
     NetworkManager.service: Connected to WiFi network "Office-5G"

repeated:
    this sshd.service gave same log as component_templates.sshd.service line 3 x8
    this systemd.service gave same log as component_templates.systemd.service line 1 x15
```

## 🔧 Configuration

Adjust these constants inside the respective scripts:

**`raw_logs.py`**

```python
QUEUE_MAX_SIZE = 5000    # max logs in memory
BATCH_SIZE     = 50      # inserts per commit
RESTART_DELAY  = 5       # seconds before restarting journalctl
```

**`batchmanager.py`**

```python
GROUP_SIZE = 20          # number of logs processed per batch
```

**`sequencer.py`**

```python
time.sleep(2)             # seconds between pipeline cycles
```

## 🔮 Future Enhancements

* Connecting this architecture to db.py to reduce the noise and put whats actually neccessary.
