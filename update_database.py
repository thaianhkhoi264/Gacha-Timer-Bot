import sqlite3
conn = sqlite3.connect('shadowverse_data.db')
c = conn.cursor()
c.execute("DELETE FROM dashboard_messages WHERE server_id=? AND user_id=?", ("0", "streak_0"))
conn.commit()
conn.close()