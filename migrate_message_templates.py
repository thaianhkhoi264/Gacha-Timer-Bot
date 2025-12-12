"""
Migration Script: Add Message Template Columns to pending_notifications

Adds columns for custom notification messages:
- message_template: Template key to use (e.g., "uma_champions_meeting_registration_start")
- custom_message: User-provided custom message override
- phase: Champions Meeting phase (e.g., "registration", "round1")
- character_name: Legend Race character name
"""

import asyncio
import aiosqlite

NOTIF_DB_PATH = "kanami_data.db"

async def migrate():
    print("Starting message template columns migration...")
    
    async with aiosqlite.connect(NOTIF_DB_PATH) as conn:
        # Check if columns already exist
        async with conn.execute("PRAGMA table_info(pending_notifications)") as cursor:
            columns = [row[1] async for row in cursor]
        
        print(f"Current columns: {columns}")
        
        # Add message_template column
        if "message_template" not in columns:
            await conn.execute("ALTER TABLE pending_notifications ADD COLUMN message_template TEXT")
            print("✓ Added message_template column")
        else:
            print("  message_template column already exists")
        
        # Add custom_message column
        if "custom_message" not in columns:
            await conn.execute("ALTER TABLE pending_notifications ADD COLUMN custom_message TEXT")
            print("✓ Added custom_message column")
        else:
            print("  custom_message column already exists")
        
        # Add phase column (for Champions Meeting)
        if "phase" not in columns:
            await conn.execute("ALTER TABLE pending_notifications ADD COLUMN phase TEXT")
            print("✓ Added phase column")
        else:
            print("  phase column already exists")
        
        # Add character_name column (for Legend Race)
        if "character_name" not in columns:
            await conn.execute("ALTER TABLE pending_notifications ADD COLUMN character_name TEXT")
            print("✓ Added character_name column")
        else:
            print("  character_name column already exists")
        
        await conn.commit()
        
        # Show final schema
        print("\nFinal schema:")
        async with conn.execute("PRAGMA table_info(pending_notifications)") as cursor:
            columns_info = await cursor.fetchall()
            for col in columns_info:
                print(f"  {col[1]} ({col[2]})")
    
    print("\n✓ Migration complete!")

if __name__ == "__main__":
    asyncio.run(migrate())
