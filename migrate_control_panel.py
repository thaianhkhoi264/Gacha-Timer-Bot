"""
Migration script to initialize the control panel message tracking system.
Run this once to set up the database table.
"""

import asyncio
import aiosqlite

NOTIF_DB_PATH = "kanami_data.db"

async def migrate():
    print("Starting control panel database migration...")
    
    async with aiosqlite.connect(NOTIF_DB_PATH) as conn:
        # Create the control_panel_messages table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS control_panel_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                profile TEXT NOT NULL,
                panel_type TEXT NOT NULL,
                event_id INTEGER,
                message_id TEXT NOT NULL,
                UNIQUE(profile, panel_type, event_id)
            )
        """)
        await conn.commit()
        print("✓ Created control_panel_messages table")
        
        # Check if table exists and show schema
        async with conn.execute("PRAGMA table_info(control_panel_messages)") as cursor:
            columns = await cursor.fetchall()
            print("\nTable schema:")
            for col in columns:
                print(f"  - {col[1]} ({col[2]})")
        
        # Count existing records
        async with conn.execute("SELECT COUNT(*) FROM control_panel_messages") as cursor:
            count = (await cursor.fetchone())[0]
            print(f"\nCurrent records in table: {count}")
    
    print("\n✓ Migration complete!")
    print("\nNext steps:")
    print("1. Restart the bot")
    print("2. The bot will automatically reuse existing control panel messages")
    print("3. Check console logs for 'Edited [message type]' instead of 'Sent new'")

if __name__ == "__main__":
    asyncio.run(migrate())
