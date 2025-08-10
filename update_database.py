import sqlite3
conn = sqlite3.connect('shadowverse_data.db')
c = conn.cursor()
c.execute("DELETE FROM dashboard_messages WHERE server_id=? AND user_id=?", ("1374399849574961152", "streak_680653908259110914"))
conn.commit()
conn.close()