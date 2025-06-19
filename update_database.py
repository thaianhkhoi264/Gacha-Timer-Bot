import sqlite3

DB_PATH = "kanami_data.db"

def add_listener_channels_table():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Create the listener_channels table if it doesn't exist
    c.execute('''
        CREATE TABLE IF NOT EXISTS listener_channels (
            server_id TEXT,
            profile TEXT,
            channel_id TEXT,
            required_keywords TEXT,
            ignored_keywords TEXT,
            PRIMARY KEY (server_id, profile)
        )
    ''')
    conn.commit()
    conn.close()
    print("listener_channels table ensured.")

def add_version_tracker_table():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS version_tracker (
            profile TEXT PRIMARY KEY,
            version TEXT,
            start_date TEXT
        )
    ''')
    conn.commit()
    conn.close()
    print("version_tracker table ensured.")

if __name__ == "__main__":
    add_listener_channels_table()
    add_version_tracker_table()