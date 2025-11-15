import sqlite3
import re
import json

DB_FILE = "logs.db"

# Connect to DB
conn = sqlite3.connect(DB_FILE)
cursor = conn.cursor()

# --- Create tables for Logzip-style storage ---
cursor.execute("""
CREATE TABLE IF NOT EXISTS templates (
    id TEXT PRIMARY KEY,
    template TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS log_instances (
    log_id INTEGER PRIMARY KEY,
    template_id TEXT,
    parameters TEXT,
    FOREIGN KEY(template_id) REFERENCES templates(id)
)
""")
conn.commit()

# --- Find last processed log ID (INCREMENTAL) ---
cursor.execute("SELECT COALESCE(MAX(log_id), 0) FROM log_instances")
last_processed = cursor.fetchone()[0]

# --- Fetch only NEW raw logs ---
cursor.execute("SELECT id, message FROM journal_logs WHERE id > ?", (last_processed,))
rows = cursor.fetchall()

if not rows:
    print(f"No new logs to process (last processed: {last_processed})")
    conn.close()
    exit(0)

print(f"Processing {len(rows)} new logs (from ID {last_processed + 1})...")

# --- Load existing templates ---
cursor.execute("SELECT template, id FROM templates")
template_dict = {template: tid for template, tid in cursor.fetchall()}

template_counter = len(template_dict) + 1

# --- Template extraction ---
def extract_template(message):
    # Replace numbers with *
    msg = re.sub(r'\b\d+\b', '*', message)
    # Replace paths (basic)
    msg = re.sub(r'(/[^\s]+)+', '*', msg)
    return msg

# Start transaction for batch insert
cursor.execute("BEGIN TRANSACTION;")

new_templates = 0
for log_id, message in rows:
    template = extract_template(message)

    if template not in template_dict:
        template_id = f"T{template_counter}"
        template_dict[template] = template_id
        template_counter += 1
        new_templates += 1

        # Insert template into DB
        cursor.execute(
            "INSERT INTO templates (id, template) VALUES (?, ?)",
            (template_id, template)
        )
    else:
        template_id = template_dict[template]

    # Extract parameters (numbers, paths)
    numbers = re.findall(r'\b\d+\b', message)
    paths = re.findall(r'(/[^\s]+)+', message)
    params = numbers + paths

    # Store instance in DB
    cursor.execute(
        "INSERT INTO log_instances (log_id, template_id, parameters) VALUES (?, ?, ?)",
        (log_id, template_id, json.dumps(params))
    )

# Commit transaction
conn.commit()
conn.close()

print(f"✓ Processed {len(rows)} log instances")
print(f"✓ Found {new_templates} new templates")
print(f"✓ Total templates in DB: {len(template_dict)}")