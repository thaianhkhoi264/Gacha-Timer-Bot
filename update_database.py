import sqlite3

DB_PATH = "kanami_data.db"

def remove_pending_duplicates():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Find duplicates (keep the lowest id)
    c.execute("""
        DELETE FROM pending_notifications
        WHERE id NOT IN (
            SELECT MIN(id)
            FROM pending_notifications
            GROUP BY server_id, category, profile, title, timing_type, notify_unix, region
        )
    """)
    conn.commit()
    conn.close()
    print("Duplicate pending_notifications removed.")

if __name__ == "__main__":
    remove_pending_duplicates()