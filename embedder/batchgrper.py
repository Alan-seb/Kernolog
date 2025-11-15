#!/usr/bin/env python3
import sqlite3
from collections import defaultdict, OrderedDict

SOURCE_DB = "logs.db"
TARGET_DB = "batches.db"

src = sqlite3.connect(SOURCE_DB)
src_cur = src.cursor()

tgt = sqlite3.connect(TARGET_DB)
tgt_cur = tgt.cursor()

# ---- Create combined table ----
tgt_cur.execute("""
CREATE TABLE IF NOT EXISTS component_templates (
    component TEXT PRIMARY KEY,
    templates TEXT
)
""")

# ---- Fetch component → template ----
src_cur.execute("""
SELECT j.unit AS component, t.template
FROM log_instances l
JOIN journal_logs j ON l.log_id = j.id
JOIN templates t ON l.template_id = t.id
ORDER BY j.unit;
""")

rows = src_cur.fetchall()

# ---- Group distinct templates per component ----
grouped = defaultdict(OrderedDict)

for component, template in rows:
    grouped[component][template] = True  # unique + ordered

# ---- Insert into batches.db ----
tgt_cur.execute("BEGIN TRANSACTION;")

for component, templates in grouped.items():
    blob = "\n".join(templates.keys())  # newline-separated templates

    tgt_cur.execute("""
        INSERT OR REPLACE INTO component_templates (component, templates)
        VALUES (?, ?)
    """, (component, blob))

tgt.commit()

print("[OK] batches.db created with component → newline-separated templates")
print(f"Components processed: {len(grouped)}")

src.close()
tgt.close()
