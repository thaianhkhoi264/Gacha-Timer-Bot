import sqlite3

DB_PATH = "kanami_data.db"

def fix_hyv_region_fields():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Find all HSR/ZZZ events with missing region-specific fields
    c.execute("""
        SELECT id, title, profile, start_date, end_date,
               asia_start, america_start, europe_start,
               asia_end, america_end, europe_end
        FROM user_data
        WHERE (profile = 'HSR' OR profile = 'ZZZ')
    """)
    rows = c.fetchall()

    updated = 0
    for row in rows:
        (event_id, title, profile, start_date, end_date,
         asia_start, america_start, europe_start,
         asia_end, america_end, europe_end) = row

        updates = {}
        # Fill missing starts
        if not asia_start or asia_start == '':
            updates['asia_start'] = start_date
        if not america_start or america_start == '':
            updates['america_start'] = start_date
        if not europe_start or europe_start == '':
            updates['europe_start'] = start_date
        # Fill missing ends
        if not asia_end or asia_end == '':
            updates['asia_end'] = end_date
        if not america_end or america_end == '':
            updates['america_end'] = end_date
        if not europe_end or europe_end == '':
            updates['europe_end'] = end_date

        if updates:
            set_clause = ", ".join([f"{k}=?" for k in updates.keys()])
            values = list(updates.values())
            values.append(event_id)
            c.execute(f"UPDATE user_data SET {set_clause} WHERE id=?", values)
            print(f"Updated event '{title}' ({profile}) id={event_id}: {updates}")
            updated += 1

    conn.commit()
    conn.close()
    print(f"Done. {updated} event(s) updated.")

if __name__ == "__main__":
    fix_hyv_region_fields()