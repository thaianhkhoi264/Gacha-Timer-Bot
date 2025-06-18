import sqlite3

DB_PATH = "kanami_data.db"

def add_region_column():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Check if 'region' column exists
    c.execute("PRAGMA table_info(pending_notifications)")
    columns = [row[1] for row in c.fetchall()]
    if "region" not in columns:
        print("Adding 'region' column to pending_notifications...")
        c.execute("ALTER TABLE pending_notifications ADD COLUMN region TEXT")
        conn.commit()
    else:
        print("'region' column already exists.")
    conn.close()

def update_region_for_hyv():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Only update rows where region is NULL or empty and profile is HSR or ZZZ
    for profile in ("HSR", "ZZZ"):
        # Try to infer region from the title or other available data
        c.execute("""
            SELECT id, title FROM pending_notifications
            WHERE (region IS NULL OR region = '')
            AND profile=?
        """, (profile,))
        rows = c.fetchall()
        for notif_id, title in rows:
            # Try to infer region from the title (e.g., "NA", "EU", "ASIA" in title)
            region = None
            title_upper = title.upper()
            if "NA" in title_upper or "AMERICA" in title_upper:
                region = "NA"
            elif "EU" in title_upper or "EUROPE" in title_upper:
                region = "EU"
            elif "ASIA" in title_upper:
                region = "ASIA"
            # If not found, you may want to set a default or leave as None
            if region:
                print(f"Setting region for notification {notif_id} ({title}) to {region}")
                c.execute("UPDATE pending_notifications SET region=? WHERE id=?", (region, notif_id))
    conn.commit()
    conn.close()

if __name__ == "__main__":
    add_region_column()
    update_region_for_hyv()
    print("Database schema and region update complete.")