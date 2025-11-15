#!/usr/bin/env python3
import sqlite3
import json
from collections import Counter

SOURCE_DB = "logs.db"
TEMPLATE_DB = "batches.db"

# --------- CONNECT DBs ----------
src = sqlite3.connect(SOURCE_DB)
src_cur = src.cursor()

tgt = sqlite3.connect(TEMPLATE_DB)
tgt_cur = tgt.cursor()

# --------- REBUILD FUNCTION ----------
def rebuild_log(template, params):
    rebuilt = template
    for p in params:
        rebuilt = rebuilt.replace("*", p, 1)
    return rebuilt

# --------- LOAD ALL LOGS ----------
src_cur.execute("""
SELECT 
    l.log_id,
    j.unit AS component,
    t.template,
    l.parameters
FROM log_instances l
JOIN journal_logs j ON l.log_id = j.id
JOIN templates t ON l.template_id = t.id
ORDER BY l.log_id
""")

logs = src_cur.fetchall()   # (id, component, template_text, params_json)

# --------- PROCESSING LOOP ----------
GROUP_SIZE = 20
current_group = 1

print("=== PROCESSING START ===")

for i in range(0, len(logs), GROUP_SIZE):
    group_new = []
    group_repeat = []

    for log_id, component, template_text, param_json in logs[i:i+GROUP_SIZE]:
        params = json.loads(param_json)
        full_log = rebuild_log(template_text, params)

        # Fetch stored templates for this component
        tgt_cur.execute("""
            SELECT templates FROM component_templates
            WHERE component = ?
        """, (component,))
        row = tgt_cur.fetchone()

        if row:
            stored_templates = row[0].split("\n")
        else:
            stored_templates = []

        if template_text in stored_templates:
            line_no = stored_templates.index(template_text) + 1
            group_repeat.append(
                f"this {component} gave same log as component_templates.{component} line {line_no}"
            )
        else:
            # new → add to DB
            group_new.append(full_log)
            stored_templates.append(template_text)
            templates_str = "\n".join(stored_templates)

            if row:
                tgt_cur.execute("""
                    UPDATE component_templates
                    SET templates = ?
                    WHERE component = ?
                """, (templates_str, component))
            else:
                tgt_cur.execute("""
                    INSERT INTO component_templates(component, templates)
                    VALUES (?, ?)
                """, (component, templates_str))
            tgt.commit()

    # --------- PRINT GROUP ----------
    print(f"\n=== GROUP {current_group} ===\n")

    print("new:")
    for item in group_new:
        print("    ", item)

    # Compress repeated lines
    repeat_counter = Counter(group_repeat)
    print("\nrepeated:")
    if repeat_counter:
        for msg, count in repeat_counter.items():
            if count > 1:
                print(f"    {msg} x{count}")
            else:
                print(f"    {msg}")
    else:
        print("    (none)")

    print("\n------------------------")
    current_group += 1

print("\n=== DONE ===")

src.close()
tgt.close()
